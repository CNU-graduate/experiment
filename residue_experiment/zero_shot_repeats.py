"""Two resumable E0 rounds using a completed live run's exact settings."""
import argparse
import copy
import json
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from .data import Dataset
from .prompt import SYSTEM, build_prompt
from .runner import run
from .evaluation import write_csv

ROOT = Path(__file__).resolve().parents[1]
YEARS = [2023, 2024, 2025]


def read_cases(directory):
    path = Path(directory) / 'checkpoint.sqlite'
    if not path.exists():
        return []
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        return [json.loads(p) for (p,) in db.execute('SELECT payload FROM cases')]


def prepare(baseline):
    baseline = Path(baseline)
    manifest = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['mode'] != 'live' or manifest['system_prompt'] != SYSTEM:
        raise ValueError('Baseline must be live and use the current system prompt')
    config = copy.deepcopy(manifest['config'])
    # Freeze the resolved model ID, rather than resolving a possibly changed env value.
    config.pop('model_env', None)
    config.update(years=YEARS, conditions=['E0'])
    if len(config['models']) != 1:
        raise ValueError('Expected one baseline model')
    data = Dataset(config['data_dir'])
    if {x['file']: x['sha256'] for x in data.files} != {x['file']: x['sha256'] for x in manifest['data_files']}:
        raise ValueError('Dataset differs from the completed baseline')
    rows = [r for r in read_cases(baseline) if r['condition'] == 'E0' and r['year'] in YEARS]
    expected = {r['id']: r for y in YEARS for r in data.tests[y]}
    if len(rows) != 210 or {r['id'] for r in rows} != set(expected):
        raise ValueError('Baseline needs exactly 210 unique E0 cases')
    for r in rows:
        if (r['status'] != 'success' or r['mode'] != 'live' or r['seed'] is not None
                or r['prediction'] not in ('Yes', 'No')
                or config['models'].get(r['provider']) != r['model']
                or r['actual'] != expected[r['id']]['EFSA']
                or r['prompt'] != build_prompt(expected[r['id']], [])):
            raise ValueError('Baseline settings, labels, prompt or completion mismatch')
    return config, {r['id']: r for r in rows}


def aggregate(baseline_rows, output, expected_config=None):
    output = Path(output)
    rounds = {1: baseline_rows}
    for number in (2, 3):
        manifest_path = output / 'live' / f'round_{number}' / 'manifest.json'
        if expected_config is not None and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest['config'] != expected_config or manifest['system_prompt'] != SYSTEM or manifest['mode'] != 'live':
                raise ValueError('Repeat manifest differs from baseline settings')
        found = read_cases(output / 'live' / f'round_{number}')
        actual = {}
        for r in found:
            b = baseline_rows.get(r['id'])
            if not b or r['id'] in actual:
                raise ValueError('Unexpected or duplicate repeat case')
            for key in ('mode', 'provider', 'model', 'year', 'condition', 'seed', 'actual', 'prompt', 'prompt_sha256'):
                if r[key] != b[key]:
                    raise ValueError(f'Repeat differs from baseline: {key}')
            actual[r['id']] = r
        rounds[number] = actual
    result = []
    for ident, b in sorted(baseline_rows.items()):
        valid = [rounds[n].get(ident) for n in (1, 2, 3)]
        good = [r for r in valid if r and r['status'] == 'success' and r['prediction'] in ('Yes', 'No')]
        errors = sum(r['prediction'] != b['actual'] for r in good)
        complete = len(good) == 3
        category = ('핵심 분석' if errors == 3 else '보조 분석' if errors == 2 else '단발 오답' if errors == 1 else '안정적 정답') if complete else '미완료'
        row = dict(id=ident, year=b['year'], actual=b['actual'], valid_runs=len(good), wrong_count=errors,
                   complete=complete, analysis_group=category)
        for n, r in enumerate(valid, 1):
            row[f'round_{n}_prediction'] = r['prediction'] if r and r['status'] == 'success' else ''
            row[f'round_{n}_status'] = r['status'] if r else 'missing'
        result.append(row)
    dest = output / 'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    write_csv(dest / 'all_210_error_frequency.csv', result)
    write_csv(dest / 'core_errors_3_of_3.csv', [r for r in result if r['analysis_group'] == '핵심 분석'], list(result[0]))
    write_csv(dest / 'secondary_errors_2_of_3.csv', [r for r in result if r['analysis_group'] == '보조 분석'], list(result[0]))
    summary = []
    for y in YEARS:
        a = [r for r in result if r['year'] == y]
        summary.append(dict(year=y, total=len(a), complete=sum(r['complete'] for r in a),
                            core=sum(r['analysis_group'] == '핵심 분석' for r in a),
                            secondary=sum(r['analysis_group'] == '보조 분석' for r in a),
                            incomplete=sum(not r['complete'] for r in a)))
    write_csv(dest / 'summary_by_year.csv', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT / 'results/claude-opus-5.5__baseline__2023-2025')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/claude-opus-5.5__zero-shot-3-runs__2023-2025')
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live', 'analyze'], default='dry-run')
    parser.add_argument('--round', type=int, choices=[2, 3], dest='only_round')
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    if args.mode == 'live' and not args.approve_paid_api:
        parser.error('Live execution requires --approve-paid-api')
    try:
        config, original = prepare(args.baseline)
        if args.baseline.resolve() == args.output.resolve() or args.baseline.resolve() in args.output.resolve().parents:
            raise ValueError('Use an output directory separate from the original baseline')
        if args.mode != 'analyze':
            load_dotenv(ROOT / '.env', override=False)
            numbers = [args.only_round] if args.only_round else [2, 3]
            for number in numbers:
                folder = args.output / args.mode / f'round_{number}'
                print(f'Round {number}: 210 E0 cases; {args.mode}; {folder}', flush=True)
                try:
                    info = run(config, folder, args.mode, approved=args.approve_paid_api)
                    print(json.dumps(info), flush=True)
                finally:
                    if args.mode == 'live':
                        aggregate(original, args.output, config)
        print(json.dumps(aggregate(original, args.output, config), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, ImportError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
