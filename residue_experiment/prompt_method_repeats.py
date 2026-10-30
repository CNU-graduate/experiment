"""GPT-only independent P3/P4/P5, three rounds; historical P0/P1/P2 are read-only."""
import argparse
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from dotenv import load_dotenv

from .evaluation import score, write_csv
from .instruction_prompts import system_for
from .instruction_repeats import prepare as prepare_p0, read_csv, save_json
from .prompt import build_prompt
from .prompt_methods import CONDITIONS, MODEL, PROMPTS, VERSION, parser_for
from .runner import run

ROOT = Path(__file__).resolve().parents[1]
YEARS = [2023, 2024, 2025]
ROUNDS = (1, 2, 3)
SCHEDULE = [(c, n) for n, order in enumerate(
    (('P3', 'P4', 'P5'), ('P4', 'P5', 'P3'), ('P5', 'P3', 'P4')), 1) for c in order]
METRICS = ('accuracy', 'precision', 'recall', 'macro_f1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def user_prompt(row):
    return build_prompt(row, []).replace('\\r\\n', '\\n')


def child_config(config, condition, number):
    child = copy.deepcopy(config)
    child.update(conditions=[condition], instruction_round=number,
                 prompt_methods_version=VERSION, response_format=condition,
                 prompt_newlines='lf')
    return child


def prepare(config, baseline0, baseline12):
    if (config.get('conditions') != list(CONDITIONS) or config.get('years') != YEARS
            or config.get('models') != {'openai': MODEL} or config.get('model_env')
            or config.get('api_backend') != 'openrouter'):
        raise ValueError('Requires P3/P4/P5, years 2023-2025, and frozen GPT OpenRouter model')
    data, p0, previous = prepare_p0(dict(config, conditions=['P1', 'P2']), baseline0)
    tests = {r['id']: r for y in YEARS for r in data.tests[y]}
    historical = {'P0': p0}
    files = [dict(root='P0', **r) for r in previous['baseline_files']]
    for condition in ('P1', 'P2'):
        collected = {ident: dict(id=ident, actual=t['EFSA'], year=t['year'])
                     for ident, t in tests.items()}
        for number in ROUNDS:
            rel = f'live/{condition}/round-{number:02d}'
            folder = Path(baseline12)/rel
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            old = manifest['config']
            if (manifest['mode'] != 'live' or manifest['system_prompt'] != system_for('openai', condition)
                    or old['models'] != config['models'] or old['conditions'] != [condition]
                    or old['years'] != YEARS or old.get('instruction_round') != number
                    or old.get('api_backend') != config['api_backend']):
                raise ValueError('Historical P1/P2 manifest mismatch')
            for field in ('max_output_tokens', 'timeout_seconds', 'max_attempts', 'retry_delay_seconds'):
                if old[field] != config[field]:
                    raise ValueError(f'Historical request setting mismatch: {field}')
            rows = read_csv(folder/'predictions.csv')
            if len(rows) != 210 or {r['id'] for r in rows} != set(tests):
                raise ValueError('Historical P1/P2 needs 210 unique predictions per round')
            for r in rows:
                prompt = user_prompt(tests[r['id']])
                hashes = {hashlib.sha256((manifest['system_prompt']+p).encode()).hexdigest()
                          for p in (prompt, prompt.replace('\\n', '\\r\\n'))}
                if (r['mode'] != 'live' or r['condition'] != condition
                        or r['provider'] != 'openai' or r['model'] != MODEL
                        or r['status'] != 'success' or r['prediction'] not in ('Yes', 'No')
                        or r['actual'] != tests[r['id']]['EFSA']
                        or int(r['year']) != int(tests[r['id']]['year'])
                        or r['prompt_sha256'] not in hashes):
                    raise ValueError('Historical P1/P2 input, label or prediction mismatch')
                collected[r['id']][f'round_{number}_prediction'] = r['prediction']
            for name in ('manifest.json', 'predictions.csv'):
                files.append(dict(root='P1/P2', file=f'{rel}/{name}', sha256=sha(folder/name)))
        for r in collected.values():
            r['wrong_count'] = sum(r[f'round_{n}_prediction'] != r['actual'] for n in ROUNDS)
        historical[condition] = collected
    implementation = {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    plan = dict(version=VERSION, config=config, conditions=list(CONDITIONS), rounds=list(ROUNDS),
                schedule=[dict(condition=c, round=n) for c, n in SCHEDULE],
                historical_conditions=['P0', 'P1', 'P2'], historical_calls=0,
                examples_per_case=0, cases_per_round=210, total_cases=1890,
                data_files=data.files, baseline_files=files, implementation=implementation,
                system_prompts=PROMPTS,
                system_prompt_sha256={c: hashlib.sha256(s.encode()).hexdigest() for c, s in PROMPTS.items()},
                note='Each request has one independent system prompt and one current problem; no history.')
    return data, historical, plan


def summarize(condition, number, rows, expected):
    result = []
    for year in (*YEARS, 'all'):
        ids = [i for i, t in expected.items() if year == 'all' or int(t['year']) == year]
        valid = [rows[i] for i in ids if i in rows and rows[i]['status'] == 'success']
        metrics = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {
            k: '' for k in (*METRICS, 'tn', 'fp', 'fn', 'tp')}
        result.append(dict(condition=condition, round=number, year=year, n_total=len(ids),
                           n_evaluated=len(valid), coverage=len(valid)/len(ids),
                           complete=len(valid) == len(ids), **metrics))
    return result


def aggregate(output, mode, config, data, historical):
    expected = {r['id']: r for y in YEARS for r in data.tests[y]}
    dest = Path(output)/mode/'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    metrics, comparisons, resources = [], [], []
    for condition, cases in historical.items():
        for number in ROUNDS:
            rows = {i: dict(actual=r['actual'], prediction=r[f'round_{number}_prediction'],
                            status='success') for i, r in cases.items()}
            metrics.extend(summarize(condition, number, rows, expected))
    for condition in CONDITIONS:
        rounds = {}
        for number in ROUNDS:
            folder = Path(output)/mode/condition/f'round-{number:02d}'
            rows = read_csv(folder/'predictions.csv') if (folder/'predictions.csv').exists() else []
            if rows:
                manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                if (manifest['config'] != child_config(config, condition, number)
                        or manifest['mode'] != mode or manifest['system_prompt'] != PROMPTS[condition]):
                    raise ValueError('Result manifest differs from frozen plan')
            checked = {}
            for r in rows:
                if (r['id'] not in expected or r['id'] in checked or r['condition'] != condition
                        or r['provider'] != 'openai' or r['model'] != MODEL or r['mode'] != mode
                        or r['actual'] != expected[r['id']]['EFSA'] or r.get('seed') != ''
                        or int(r['year']) != int(expected[r['id']]['year'])):
                    raise ValueError('Unexpected or mixed prompt-method result')
                wanted = hashlib.sha256((PROMPTS[condition]+user_prompt(expected[r['id']])).encode()).hexdigest()
                if r['prompt_sha256'] != wanted:
                    raise ValueError('Result prompt hash differs')
                if r['status'] == 'success' and parser_for(condition)(r['response']) != r['prediction']:
                    raise ValueError('Parsed final label differs from saved response')
                checked[r['id']] = r
            rounds[number] = checked
            metrics.extend(summarize(condition, number, checked, expected))
            calls = read_csv(folder/'api_calls.csv') if (folder/'api_calls.csv').exists() else []
            usage = [json.loads(c['usage']) for c in calls if c.get('usage')]
            resources.append(dict(condition=condition, round=number, api_attempts=len(calls),
                                  failed_attempts=sum(c['status'] != 'success' for c in calls),
                                  usage_records=len(usage),
                                  input_tokens=sum(u.get('prompt_tokens', u.get('input_tokens', 0)) or 0 for u in usage),
                                  output_tokens=sum(u.get('completion_tokens', u.get('output_tokens', 0)) or 0 for u in usage),
                                  call_seconds=sum(float(c['seconds']) for c in calls if c.get('seconds')),
                                  response_characters=sum(len(r.get('response', '')) for r in checked.values())))
        frequency = []
        for ident, t in sorted(expected.items()):
            old = historical['P0'][ident]
            p2 = historical['P2'][ident]
            observed = [rounds[n].get(ident) for n in ROUNDS]
            valid = [r for r in observed if r and r['status'] == 'success']
            complete = len(valid) == 3
            wrong = sum(r['prediction'] != t['EFSA'] for r in valid)
            n0, n2 = int(old['wrong_count']), int(p2['wrong_count'])
            p2_new = n0 == 0 and n2 > 0
            p2_fix = n0 == 3 and n2 == 0
            common_stable = n0 == 0 and n2 == 0
            r = dict(id=ident, year=t['year'], actual=t['EFSA'], p0_wrong_count=n0,
                     p2_wrong_count=n2, valid_runs=len(valid), complete=complete, wrong_count=wrong,
                     p2_new_error=p2_new, p2_core_fix=p2_fix, common_stable=common_stable,
                     p2_new_error_recovered=(p2_new and wrong == 0) if complete else '',
                     p2_fix_retained=(p2_fix and wrong == 0) if complete else '',
                     p2_fix_lost=(p2_fix and wrong > 0) if complete else '',
                     additional_new_error=(common_stable and wrong > 0) if complete else '',
                     p0_stable_damaged=(n0 == 0 and wrong > 0) if complete else '',
                     p0_core_fixed=(n0 == 3 and wrong == 0) if complete else '')
            for n, row in enumerate(observed, 1):
                r[f'round_{n}_prediction'] = row['prediction'] if row and row['status'] == 'success' else ''
                r[f'round_{n}_status'] = row['status'] if row else 'missing'
            frequency.append(r)
        write_csv(dest/f'{condition}_error_frequency.csv', frequency)
        for filename, key in (('recovered_p2_errors', 'p2_new_error_recovered'),
                              ('lost_p2_fixes', 'p2_fix_lost'), ('additional_new_errors', 'additional_new_error')):
            write_csv(dest/f'{condition}_{filename}.csv', [r for r in frequency if r[key] is True],
                      list(frequency[0]))
        fields = ('p2_new_error_recovered', 'p2_fix_retained', 'p2_fix_lost',
                  'additional_new_error', 'p0_stable_damaged', 'p0_core_fixed')
        comparisons.append(dict(
            condition=condition, n_total=210, n_complete=sum(r['complete'] for r in frequency),
            p2_new_error_total=sum(r['p2_new_error'] for r in frequency),
            p2_core_fix_total=sum(r['p2_core_fix'] for r in frequency),
            common_stable_total=sum(r['common_stable'] for r in frequency),
            **{k: sum(r[k] is True for r in frequency) for k in fields}))
    write_csv(dest/'round_metrics.csv', metrics)
    averages = []
    for condition in ('P0', 'P1', 'P2', *CONDITIONS):
        for year in (*YEARS, 'all'):
            reps = [r for r in metrics if r['condition'] == condition and r['year'] == year and r['complete']]
            row = dict(condition=condition, year=year, historical=condition in ('P0', 'P1', 'P2'),
                       repeats_complete=len(reps), repeats_planned=3)
            for field in METRICS:
                values = [r[field] for r in reps]
                row[field+'_mean'] = mean(values) if values else ''
                row[field+'_std'] = stdev(values) if len(values) > 1 else (0.0 if values else '')
            averages.append(row)
    write_csv(dest/'condition_summary.csv', averages)
    write_csv(dest/'baseline_comparison.csv', comparisons)
    write_csv(dest/'resources.csv', resources)
    return comparisons


def execute(config, output, baseline0, baseline12, mode='dry-run', approved=False,
            condition=None, only_round=None):
    if mode not in ('dry-run', 'mock', 'live', 'analyze'):
        raise ValueError('Invalid mode')
    if mode == 'live' and not approved:
        raise ValueError('Live requires --approve-paid-api')
    if condition is not None and condition not in CONDITIONS:
        raise ValueError('Only P3/P4/P5 are executable')
    if only_round is not None and only_round not in ROUNDS:
        raise ValueError('Round must be 1, 2 or 3')
    output = Path(output).resolve()
    protected = [
        ROOT/'data', *[ROOT/'results'/p for p in
            ('baseline', 'remain-v2', 'zero-shot-repeats', 'instruction-v1',
             'instruction-only', 'error-informed', 'error-informed-personalized')],
        Path(baseline0).resolve(), Path(baseline12).resolve()]
    if (output in (ROOT, ROOT/'results') or any(output == p.resolve() or p.resolve() in output.parents
                                               for p in protected)):
        raise ValueError('Use a separate new output directory; historical results are read-only')
    data, historical, plan = prepare(config, baseline0, baseline12)
    if mode == 'analyze' and not (output/'plan.json').exists():
        raise ValueError('No existing prompt-method plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty new output directory')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.run.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError('This output is locked by another process; do not run concurrently') from exc
    os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text(encoding='utf-8')) != plan:
                raise ValueError('Code/config/data/baseline/prompts changed; use a new output directory')
        else:
            save_json(output/'plan.json', plan)
            save_json(output/'system_prompts.json', PROMPTS)
        if mode == 'analyze':
            return dict(calls=0, output=str(output),
                        analysis=aggregate(output, 'live', config, data, historical))
        results = []
        try:
            for c, n in SCHEDULE:
                if condition is not None and c != condition or only_round is not None and n != only_round:
                    continue
                print(f'{c} round {n}: 210 cases; {mode}; independent request history', flush=True)
                info = run(child_config(config, c, n), output/mode/c/f'round-{n:02d}',
                           mode, approved=approved, system_prompt=PROMPTS[c],
                           response_parser=parser_for(c))
                results.append(dict(condition=c, round=n, **info))
        finally:
            aggregate(output, mode, config, data, historical)
        return dict(mode=mode, cases=sum(r['cases'] for r in results),
                    calls=sum(r['calls'] for r in results), runs=results, output=str(output))
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config.openrouter.prompt-methods.json')
    parser.add_argument('--provider', choices=['openai'], default='openai')
    parser.add_argument('--condition', choices=CONDITIONS)
    parser.add_argument('--round', type=int, choices=ROUNDS, dest='only_round')
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live', 'analyze'], default='dry-run')
    parser.add_argument('--output', type=Path, default=ROOT/'results/prompt-methods-v1/gpt-6-sol/2023-2025')
    parser.add_argument('--fresh', action='store_true', help='New empty timestamped experiment, not resume')
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        config['data_dir'] = str((args.config.resolve().parent/config['data_dir']).resolve())
        if args.fresh and args.mode == 'analyze':
            raise ValueError('--fresh cannot analyze a new empty run')
        output = args.output
        if args.fresh:
            output /= datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        if args.mode == 'live':
            load_dotenv(args.config.resolve().parent/'.env', override=False)
        info = execute(config, output,
                       ROOT/'results/zero-shot-repeats/gpt-6-sol/2023-2025',
                       ROOT/'results/instruction-v1/gpt-6-sol/2023-2025',
                       args.mode, args.approve_paid_api, args.condition, args.only_round)
        print(json.dumps(info, ensure_ascii=False))
    except (ValueError, KeyError, ImportError, OSError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
