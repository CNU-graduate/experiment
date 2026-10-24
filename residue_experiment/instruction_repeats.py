"""P1/P2 instruction-only experiments: 210 cases x 2 variants x 3 rounds."""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean, stdev

from dotenv import load_dotenv

from .cli import validate_config
from .data import Dataset, inputs, LABELS
from .evaluation import write_csv, score
from .instruction_prompts import VERSION, VARIANTS, system_for
from .prompt import SYSTEM, build_prompt
from .providers import KEYS
from .runner import run

ROOT = Path(__file__).resolve().parents[1]
YEARS = [2023, 2024, 2025]
ROUNDS = (1, 2, 3)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def slug(config):
    return next(iter(config['models'].values())).split('/')[-1]


def prepare(config, baseline):
    if config['conditions'] != list(VARIANTS) or config['years'] != YEARS:
        raise ValueError('Instruction experiment requires P1/P2 only and years 2023, 2024, 2025')
    if len(config['models']) != 1 or not all(config['models'].values()) or config.get('model_env'):
        raise ValueError('Select one explicit frozen model ID; model_env overrides are not allowed')
    check = dict(config, conditions=['E0'])
    validate_config(check)
    provider, model = next(iter(config['models'].items()))
    data = Dataset(config['data_dir'])
    if any(len(data.tests.get(y, [])) != 70 for y in YEARS):
        raise ValueError('Exactly 70 test cases per year are required')
    tests = {r['id']: r for y in YEARS for r in data.tests[y]}
    if len(tests) != 210:
        raise ValueError('Exactly 210 distinct test IDs are required')
    baseline = Path(baseline)
    path = baseline / 'analysis' / 'all_210_error_frequency.csv'
    original = read_csv(path)
    by_id = {r['id']: r for r in original}
    if len(original) != 210 or len(by_id) != 210 or set(by_id) != set(tests):
        raise ValueError('Baseline must contain the same 210 unique test IDs')
    for ident, row in by_id.items():
        predictions = [row.get(f'round_{n}_prediction') for n in ROUNDS]
        statuses = [row.get(f'round_{n}_status') for n in ROUNDS]
        if (row.get('complete') != 'True' or row.get('valid_runs') != '3'
                or statuses != ['success'] * 3 or any(p not in LABELS for p in predictions)
                or row['actual'] != tests[ident]['EFSA']
                or int(row['wrong_count']) != sum(p != row['actual'] for p in predictions)):
            raise ValueError(f'Invalid or incomplete baseline: {ident}')
    baseline_files = [{'file': 'analysis/all_210_error_frequency.csv', 'sha256': digest(path)}]
    for number in (2, 3):
        name = f'live/round-{number:02d}/manifest.json'
        p = baseline / name
        manifest = json.loads(p.read_text(encoding='utf-8'))
        old = manifest['config']
        if (manifest['mode'] != 'live' or manifest['system_prompt'] != SYSTEM
                or old['models'] != {provider: model} or old['years'] != YEARS
                or old['conditions'] != ['E0']
                or old.get('api_backend', 'official') != config.get('api_backend', 'official')):
            raise ValueError('Baseline model, years, backend or system prompt differs')
        for field in ('max_output_tokens', 'timeout_seconds', 'max_attempts', 'retry_delay_seconds'):
            if old[field] != config[field]:
                raise ValueError(f'Baseline generation/request setting differs: {field}')
        baseline_files.append({'file': name, 'sha256': digest(p)})
        prediction_name = f'live/round-{number:02d}/predictions.csv'
        prediction_path = baseline / prediction_name
        previous = read_csv(prediction_path)
        if len(previous) != 210 or {r['id'] for r in previous} != set(tests):
            raise ValueError('Baseline round needs 210 unique predictions')
        for row in previous:
            ident = row['id']
            prompt = build_prompt(tests[ident], []).replace('\\r\\n', '\\n')
            accepted = {hashlib.sha256((SYSTEM + text).encode()).hexdigest()
                        for text in (prompt, prompt.replace('\\n', '\\r\\n'))}
            if (row['mode'] != 'live' or row['condition'] != 'E0'
                    or row['provider'] != provider or row['model'] != model
                    or row['status'] != 'success' or row['actual'] != tests[ident]['EFSA']
                    or row['prediction'] != by_id[ident][f'round_{number}_prediction']
                    or row['prompt_sha256'] not in accepted):
                raise ValueError('Baseline input, model, prediction or prompt differs')
        baseline_files.append({'file': prediction_name, 'sha256': digest(prediction_path)})
    prompts = {v: system_for(provider, v) for v in VARIANTS}
    plan = {
        'version': VERSION, 'conditions': list(VARIANTS), 'rounds': list(ROUNDS),
        'P0_is_not_executed': True, 'examples_per_case': 0,
        'cases_per_round': 210, 'total_cases': 1260, 'config': config,
        'data_files': data.files, 'baseline_files': baseline_files,
        'system_prompts': prompts,
        'system_prompt_sha256': {v: hashlib.sha256(s.encode()).hexdigest() for v, s in prompts.items()},
        'note': 'Repeated independent calls, not random-example seeds. Previously inspected data are development evidence.'
    }
    return data, by_id, plan


def aggregate(output, mode, config, data, baseline):
    output = Path(output)
    provider, model = next(iter(config['models'].items()))
    expected = {r['id']: r for y in YEARS for r in data.tests[y]}
    dest = output / mode / 'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    round_metrics, summaries = [], []
    for variant in VARIANTS:
        rounds = {}
        for number in ROUNDS:
            folder = output / mode / variant / f'round-{number:02d}'
            path = folder / 'predictions.csv'
            rows = read_csv(path) if path.exists() else []
            if rows:
                manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                child = manifest['config']
                if (manifest['mode'] != mode or manifest['system_prompt'] != system_for(provider, variant)
                        or child['models'] != {provider: model} or child['conditions'] != [variant]
                        or child.get('instruction_round') != number):
                    raise ValueError('Instruction child manifest differs from frozen plan')
            by_id = {}
            for r in rows:
                if (r['id'] not in expected or r['id'] in by_id or r['condition'] != variant
                        or r['mode'] != mode or r['provider'] != provider or r['model'] != model
                        or r['actual'] != expected[r['id']]['EFSA']
                        or int(r['year']) != int(expected[r['id']]['year'])
                        or (r['status'] == 'success' and r['prediction'] not in LABELS)):
                    raise ValueError('Unexpected instruction result; do not mix result folders')
                prompt = build_prompt(expected[r['id']], []).replace('\\r\\n', '\\n')
                expected_hash = hashlib.sha256((system_for(provider, variant)+prompt).encode()).hexdigest()
                if r['prompt_sha256'] != expected_hash:
                    raise ValueError('Result prompt hash differs from the approved instruction variant')
                by_id[r['id']] = r
            rounds[number] = by_id
            for year in (*YEARS, 'all'):
                ids = [i for i, r in expected.items() if year == 'all' or int(r['year']) == year]
                valid = [by_id[i] for i in ids if i in by_id and by_id[i]['status'] == 'success']
                metrics = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {
                    k: '' for k in ('accuracy', 'precision', 'recall', 'macro_f1', 'tn', 'fp', 'fn', 'tp')}
                round_metrics.append(dict(provider=provider, model=model, condition=variant,
                                          round=number, year=year, n_total=len(ids), n_evaluated=len(valid),
                                          coverage=len(valid)/len(ids), complete=len(valid) == len(ids), **metrics))
        frequencies = []
        for ident, test in sorted(expected.items()):
            old = baseline[ident]
            observed = [rounds[n].get(ident) for n in ROUNDS]
            good = [r for r in observed if r and r['status'] == 'success']
            wrong = sum(r['prediction'] != old['actual'] for r in good)
            complete = len(good) == 3
            base_wrong = int(old['wrong_count'])
            group = ('core' if wrong == 3 else 'secondary' if wrong == 2 else
                     'one_off' if wrong == 1 else 'stable_correct') if complete else 'incomplete'
            row = dict(id=ident, year=test['year'], actual=old['actual'],
                       baseline_wrong_count=base_wrong, valid_runs=len(good), wrong_count=wrong,
                       complete=complete, analysis_group=group,
                       core_fully_fixed=(base_wrong == 3 and wrong == 0) if complete else '',
                       core_partly_fixed=(base_wrong == 3 and wrong in (1, 2)) if complete else '',
                       stable_correct_damaged=(base_wrong == 0 and wrong > 0) if complete else '')
            for n, r in enumerate(observed, 1):
                row[f'round_{n}_prediction'] = r['prediction'] if r and r['status'] == 'success' else ''
                row[f'round_{n}_status'] = r['status'] if r else 'missing'
            frequencies.append(row)
        write_csv(dest / f'{variant}_error_frequency.csv', frequencies)
        write_csv(dest / f'{variant}_core_errors.csv', [r for r in frequencies if r['complete'] and r['wrong_count'] == 3],
                  list(frequencies[0]))
        write_csv(dest / f'{variant}_new_errors.csv', [r for r in frequencies if r['stable_correct_damaged'] is True],
                  list(frequencies[0]))
        summaries.append(dict(
            condition=variant, n_total=210, n_complete=sum(r['complete'] for r in frequencies),
            baseline_core=sum(int(r['wrong_count']) == 3 for r in baseline.values()),
            core_fully_fixed=sum(r['core_fully_fixed'] is True for r in frequencies),
            core_partly_fixed=sum(r['core_partly_fixed'] is True for r in frequencies),
            baseline_stable_correct=sum(int(r['wrong_count']) == 0 for r in baseline.values()),
            stable_correct_damaged=sum(r['stable_correct_damaged'] is True for r in frequencies),
            current_core=sum(r['complete'] and r['wrong_count'] == 3 for r in frequencies),
            note='Incomplete cases are not counted as fixes or new errors'))
    write_csv(dest / 'round_metrics.csv', round_metrics)
    write_csv(dest / 'baseline_comparison.csv', summaries)
    averages = []
    for variant in VARIANTS:
        for year in (*YEARS, 'all'):
            rows = [r for r in round_metrics if r['condition'] == variant and r['year'] == year]
            complete = [r for r in rows if r['complete']]
            out = dict(condition=variant, year=year, repeats_planned=3, repeats_complete=len(complete))
            for metric in ('accuracy', 'precision', 'recall', 'macro_f1'):
                values = [r[metric] for r in complete]
                out[metric + '_mean'] = mean(values) if values else ''
                out[metric + '_std'] = stdev(values) if len(values) > 1 else (0.0 if values else '')
            averages.append(out)
    write_csv(dest / 'condition_summary.csv', averages)
    return summaries


def execute(config, output, baseline, mode='dry-run', approved=False, condition=None, only_round=None):
    if mode not in ('dry-run', 'mock', 'live', 'analyze'):
        raise ValueError('Invalid mode')
    if mode == 'live' and not approved:
        raise ValueError('Live calls require --approve-paid-api')
    if condition is not None and condition not in VARIANTS:
        raise ValueError('Only P1/P2 can be executed; P0 is baseline-only')
    if only_round is not None and only_round not in ROUNDS:
        raise ValueError('Round must be 1, 2 or 3')
    data, original, plan = prepare(config, baseline)
    output = Path(output)
    if output.resolve() == Path(baseline).resolve() or Path(baseline).resolve() in output.resolve().parents:
        raise ValueError('Use a new instruction-experiment directory, separate from baseline')
    path = output / 'plan.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != plan:
            raise ValueError('Plan/config/data/baseline/prompts changed; use a new output directory')
    else:
        if mode == 'analyze':
            raise ValueError('No existing instruction plan')
        if output.exists() and any(output.iterdir()):
            raise ValueError('Use an empty new instruction-experiment directory')
        output.mkdir(parents=True, exist_ok=True)
        save_json(path, plan)
        save_json(output / 'system_prompts.json', plan['system_prompts'])
    if mode == 'analyze':
        return {'analysis': aggregate(output, 'live', config, data, original),
                'calls': 0, 'output': str(output.resolve())}
    executed = []
    try:
        for variant in ((condition,) if condition else VARIANTS):
            for number in ((only_round,) if only_round else ROUNDS):
                child = copy.deepcopy(config)
                child.update(conditions=[variant], instruction_version=VERSION, instruction_round=number,
                             prompt_newlines='lf')
                folder = output / mode / variant / f'round-{number:02d}'
                print(f'{variant} round {number}: 210 cases; {mode}; {folder}', flush=True)
                info = run(child, folder, mode, approved=approved, system_prompt=plan['system_prompts'][variant])
                executed.append(dict(condition=variant, round=number, **info))
    finally:
        aggregate(output, mode, config, data, original)
    return dict(mode=mode, runs=executed, cases=sum(r['cases'] for r in executed),
                calls=sum(r['calls'] for r in executed), output=str(output.resolve()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config.openrouter.instructions.json')
    parser.add_argument('--provider', required=True, choices=list(KEYS))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline', type=Path, help='Existing zero-shot-repeats model directory, read-only')
    parser.add_argument('--condition', choices=VARIANTS, help='Optional: execute one variant only')
    parser.add_argument('--round', type=int, choices=ROUNDS, dest='only_round')
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live', 'analyze'], default='dry-run')
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        config['data_dir'] = str((args.config.resolve().parent/config['data_dir']).resolve())
        if args.provider not in config['models']:
            raise ValueError('Provider is absent from config')
        config['models'] = {args.provider: config['models'][args.provider]}
        name = slug(config)
        baseline = args.baseline or ROOT/'results'/'zero-shot-repeats'/name/'2023-2025'
        output = args.output or ROOT/'results'/'instruction-v1'/name/'2023-2025'
        if args.mode == 'live':
            load_dotenv(args.config.resolve().parent/'.env', override=False)
        info = execute(config, output, baseline, args.mode, args.approve_paid_api,
                       args.condition, args.only_round)
        print(json.dumps(info, ensure_ascii=False))
    except (ValueError, KeyError, ImportError, OSError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
