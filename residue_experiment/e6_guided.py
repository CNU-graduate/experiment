"""Frozen E6 examples plus three limited comparison rules; GPT only."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from statistics import mean, stdev

from dotenv import load_dotenv

from .evaluation import score, write_csv
from .instruction_repeats import read_csv, save_json
from .prompt import SYSTEM, parse_label
from .runner import run

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'e6-guided-v1'
MODEL = 'openai/gpt-6-sol'
DEFAULT_OUTPUT = ROOT/'results'/VERSION/'gpt-6-sol/2023-2025'
BASELINES = [ROOT/'results/remain-v2/gpt-6-sol/2023-2025'] + [
    ROOT/f'results/e6-repeats/gpt-6-sol/2023-2025/live/round-{n:02d}' for n in (2, 3)]
ADDITION = """Additional comparison checks:

1. When compounds are explicitly assessed separately, do not turn them
into a combined sum. Compare the independently defined residue relevant
to the named substance, without discarding another applicable definition
merely because it is separate. Numbering alone does not establish
independent assessment.

2. Apply each exception only to the purpose, commodity, species, source,
or other scope it explicitly describes. In particular, do not transfer
a risk-assessment exception to an enforcement comparison.

3. A provisional, pending, not-proposed, or not-required statement, or a
difference in analytical description, does not by itself establish a
substantive difference in residue scope. It does not establish equivalence
either. Preserve genuine differences in included metabolites, conjugates,
assessment structure, expression basis, and supported chemical scope.

These checks do not establish a new source-precedence policy. Do not
select an EU source solely because it matches JMPR. Do not automatically
favor Yes or No. Return exactly Yes or No."""
GUIDED_SYSTEM = SYSTEM.rstrip() + '\n\n' + ADDITION
REQUEST_FIELDS = ('max_output_tokens', 'timeout_seconds', 'max_attempts',
                  'retry_delay_seconds', 'api_backend')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized(value):
    if isinstance(value, str):
        return value.replace('\r\n', '\n')
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def prompts(folder):
    result = {}
    for line in (folder/'prompts.jsonl').read_text(encoding='utf-8-sig').splitlines():
        row = json.loads(line)
        if row['condition'] != 'E6':
            continue
        if row['id'] in result:
            raise ValueError('Duplicate E6 prompt ID')
        result[row['id']] = normalized(json.loads(row['prompt']))
    return result


def prepare():
    """Check regenerated plans against all three archives before any SDK creation."""
    first = json.loads((BASELINES[0]/'manifest.json').read_text(encoding='utf-8-sig'))
    config = {k: first['config'][k] for k in REQUEST_FIELDS}
    config.update(data_dir=str(ROOT/'data'), priority_annotations=str(ROOT/'priority_annotations.json'),
                  years=[2023, 2024, 2025], seeds=[42], conditions=['E6'],
                  models={'openai': MODEL}, model_env={})
    historical, files = [], []
    for folder in BASELINES:
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
        cfg = manifest['config']
        if (manifest['mode'] != 'live' or manifest['system_prompt'] != SYSTEM
                or cfg['models'] != {'openai': MODEL} or cfg['years'] != config['years']
                or cfg['seeds'] != [42] or 'E6' not in cfg['conditions']
                or any(cfg[k] != config[k] for k in REQUEST_FIELDS)
                or manifest['annotation_files'] != first['annotation_files']):
            raise ValueError('Historical E6 manifest mismatch')
        rows = [r for r in read_csv(folder/'predictions.csv') if r['condition'] == 'E6']
        if (len(rows) != 210 or len({r['id'] for r in rows}) != 210
                or any(r['status'] != 'success' or r['mode'] != 'live'
                       or r['seed'] != '42' or r['provider'] != 'openai'
                       or r['model'] != MODEL or r['prediction'] not in ('Yes', 'No') for r in rows)):
            raise ValueError('Historical E6 needs 210 valid unique predictions')
        if historical and {r['id']: r['actual'] for r in rows} != {
                r['id']: r['actual'] for r in historical[0]}:
            raise ValueError('Historical E6 IDs/labels differ')
        historical.append(rows)
        for name in ('manifest.json', 'predictions.csv', 'prompts.jsonl', 'examples.csv'):
            p = folder/name
            files.append(dict(file=str(p.relative_to(ROOT)), sha256=sha(p)))
    with tempfile.TemporaryDirectory(prefix='e6-guided-preflight-') as temp:
        folder = Path(temp)
        info = run(config, folder, 'dry-run', system_prompt=GUIDED_SYSTEM)
        if info != {'cases': 210, 'calls': 0}:
            raise ValueError('Preflight expected 210 cases and zero calls')
        planned = read_csv(folder/'predictions.csv')
        if any(r['status'] != 'planned' for r in planned):
            raise ValueError('E6 preflight contains exclusions or incomplete cases')
        generated = prompts(folder)
        new_manifest = json.loads((folder/'manifest.json').read_text())
        if new_manifest['annotation_files'] != first['annotation_files']:
            raise ValueError('Priority annotations differ from archived E6')
        def examples(path):
            return sorted(tuple(r[k] for k in ('id', 'rank', 'example_id', 'example_year', 'example_label'))
                          for r in read_csv(path/'examples.csv') if r['condition'] == 'E6')
        for old_folder, old_rows in zip(BASELINES, historical):
            if generated != prompts(old_folder) or examples(folder) != examples(old_folder):
                raise ValueError('Examples, order, or user inputs differ from archived E6')
            old = {r['id']: r for r in old_rows}
            for r in planned:
                if r['actual'] != old[r['id']]['actual'] or r['year'] != old[r['id']]['year']:
                    raise ValueError('Archived E6 year or label differs')
        plan = dict(version=VERSION, config=config, system_prompt=GUIDED_SYSTEM,
                    baseline_files=files, data_files=new_manifest['data_files'],
                    annotation_files=new_manifest['annotation_files'],
                    implementation={p.name: sha(p) for p in sorted((ROOT/'residue_experiment').glob('*.py'))},
                    cases_per_round=210, rounds=3, total_cases=630,
                    preflight=dict(calls=0, user_inputs_and_examples_match_all_archives=True))
        expected = {r['id']: r for r in planned}
    return config, historical, plan, expected


def aggregate(output, mode, config, historical, expected):
    dest = output/mode/'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    metrics, summaries, new_rounds = [], [], []
    for condition, rounds in (('E6-historical', historical), (VERSION, None)):
        if rounds is None:
            rounds = []
            for n in (1, 2, 3):
                folder = output/mode/f'round-{n:02d}'
                rows = read_csv(folder/'predictions.csv') if (folder/'predictions.csv').exists() else []
                if rows:
                    m = json.loads((folder/'manifest.json').read_text())
                    if m['mode'] != mode or m['system_prompt'] != GUIDED_SYSTEM or m['config'] != config:
                        raise ValueError('Guided result manifest mismatch')
                if len({r['id'] for r in rows}) != len(rows):
                    raise ValueError('Duplicate guided prediction')
                for r in rows:
                    t = expected.get(r['id'])
                    if (t is None or any(r[k] != t[k] for k in
                            ('actual', 'year', 'condition', 'seed', 'provider', 'model', 'prompt_sha256'))
                            or r['mode'] != mode):
                        raise ValueError('Guided result differs from frozen plan')
                    if r['status'] == 'success':
                        parse_label(r['prediction'])
                rounds.append(rows)
            new_rounds = rounds
        for n, rows in enumerate(rounds, 1):
            for year in (2023, 2024, 2025, 'all'):
                targets = [r for r in expected.values() if year == 'all' or int(r['year']) == year]
                valid = [r for r in rows if r['status'] == 'success'
                         and (year == 'all' or int(r['year']) == year)]
                values = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {}
                metrics.append(dict(condition=condition, historical=condition == 'E6-historical',
                                    round=n, year=year, n_total=len(targets), n_evaluated=len(valid),
                                    complete=len(valid) == len(targets), coverage=len(valid)/len(targets), **values))
        for year in (2023, 2024, 2025, 'all'):
            reps = [r for r in metrics if r['condition'] == condition and r['year'] == year and r['complete']]
            row = dict(condition=condition, year=year, repeats_complete=len(reps), repeats_planned=3)
            for field in ('accuracy', 'macro_f1'):
                vals = [r[field] for r in reps]
                row[field+'_mean'] = mean(vals) if vals else ''
                row[field+'_std'] = stdev(vals) if len(vals) > 1 else (0.0 if vals else '')
            summaries.append(row)
    frequency = []
    for ident, t in sorted(expected.items()):
        old_wrong = sum(next(r for r in rows if r['id'] == ident)['prediction'] != t['actual'] for rows in historical)
        observed = [next((r for r in rows if r['id'] == ident and r['status'] == 'success'), None)
                    for rows in new_rounds]
        valid = [r for r in observed if r]
        wrong = sum(r['prediction'] != t['actual'] for r in valid)
        complete = len(valid) == 3
        frequency.append(dict(id=ident, year=t['year'], actual=t['actual'], e6_wrong_count=old_wrong,
                              valid_runs=len(valid), complete=complete, guided_wrong_count=wrong,
                              recovered_repeat_error=(old_wrong >= 2 and wrong == 0) if complete else '',
                              damaged_stable_correct=(old_wrong == 0 and wrong > 0) if complete else '',
                              **{f'round_{n}_prediction': r['prediction'] if r else ''
                                 for n, r in enumerate(observed, 1)}))
    write_csv(dest/'round_metrics.csv', metrics)
    write_csv(dest/'condition_summary.csv', summaries)
    write_csv(dest/'error_frequency.csv', frequency)
    return summaries


def execute(output=DEFAULT_OUTPUT, mode='dry-run', approved=False, only_round=None):
    if mode not in ('dry-run', 'mock', 'live', 'analyze') or only_round not in (None, 1, 2, 3):
        raise ValueError('Invalid mode or round')
    if mode == 'live' and not approved:
        raise ValueError('Live requires --approve-paid-api')
    output = Path(output).resolve()
    # Custom roots may be outside the repository, or within this version's subtree only.
    if ((output == ROOT or ROOT in output.parents)
            and output != DEFAULT_OUTPUT.resolve() and DEFAULT_OUTPUT.resolve() not in output.parents):
        raise ValueError('Use the dedicated e6-guided-v1 output tree or a directory outside the repository')
    config, historical, plan, expected = prepare()
    if mode == 'analyze' and not (output/'plan.json').exists():
        raise ValueError('No existing guided plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty new output directory')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.run.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text()) != plan:
                raise ValueError('Code/data/config/baseline changed; use a new output directory')
        else:
            save_json(output/'plan.json', plan)
        if mode == 'analyze':
            return dict(calls=0, analysis=aggregate(output, 'live', config, historical, expected))
        results = []
        try:
            for n in (1, 2, 3):
                if only_round is not None and n != only_round:
                    continue
                print(f'{VERSION} round {n}: 210 cases; {mode}', flush=True)
                results.append(run(config, output/mode/f'round-{n:02d}', mode,
                                   approved=approved, system_prompt=GUIDED_SYSTEM))
        finally:
            aggregate(output, mode, config, historical, expected)
        return dict(mode=mode, cases=sum(r['cases'] for r in results),
                    calls=sum(r['calls'] for r in results), output=str(output))
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live', 'analyze'], default='dry-run')
    parser.add_argument('--round', type=int, choices=[1, 2, 3], dest='only_round')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    try:
        if args.mode == 'live':
            load_dotenv(ROOT/'.env', override=False)
        print(json.dumps(execute(args.output, args.mode, args.approve_paid_api, args.only_round), ensure_ascii=False))
    except (ValueError, KeyError, ImportError, OSError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
