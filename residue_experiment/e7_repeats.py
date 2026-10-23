"""Three independent E7 rounds with identical examples and prompts."""
import argparse
import json
from collections import Counter
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from .cli import validate_config
from .data import Dataset, inputs
from .e7_examples import VERSION, select
from .evaluation import write_csv
from .runner import run

ROOT = Path(__file__).resolve().parents[1]


def prepare(config):
    """Fail before running if any selected example is unavailable or changed."""
    validate_config(config)
    if config['conditions'] != ['E7'] or config['years'] != [2023, 2024, 2025]:
        raise ValueError('E7 repeats requires E7 only and years 2023, 2024, 2025')
    if len(config['models']) != 1 or not all(config['models'].values()) or config.get('model_env'):
        raise ValueError('E7 repeats requires exactly one explicit frozen model ID')
    data = Dataset(config['data_dir'])
    examples = []
    for year in config['years']:
        if len(data.tests.get(year, [])) != 70:
            raise ValueError(f'E7 requires 70 tests for {year}')
        rows = select(data.pools[year - 1], year)
        for rank, r in enumerate(rows, 1):
            examples.append(dict(test_year=year, rank=rank, role=r['role'],
                                 example_id=r['id'], example_year=year - 1,
                                 **inputs(r), EFSA=r['EFSA'], reason=r['selection_reason']))
    return examples


def execute(config, output, mode='dry-run', approved=False):
    if mode not in ('dry-run', 'mock', 'live'):
        raise ValueError('Invalid mode')
    if mode == 'live' and not approved:
        raise ValueError('Live execution requires --approve-paid-api')
    examples = prepare(config)
    output = Path(output)
    # Never run over a directory containing other experiment artifacts.
    output.mkdir(parents=True, exist_ok=True)
    allowed = {'dry-run', 'mock', 'live', 'plan.json', 'selected_examples.json',
               'selected_examples.csv', 'plan_by_year.csv'}
    if any(p.name not in allowed for p in output.iterdir()):
        raise ValueError('Use a separate E7 output directory')
    plan = dict(condition='E7', selection_version=VERSION, config=config,
                rounds=3, cases_per_round=210, total_cases=630,
                order=['N1', 'Y1', 'N2', 'Y2'],
                note='Fixed examples; round repetition is not random-example seeds.')
    plan_path = output / 'plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text(encoding='utf-8')) != plan:
        raise ValueError('E7 plan differs; use a new output directory')
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'selected_examples.json').write_text(
        json.dumps(examples, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(output / 'selected_examples.csv', examples)
    write_csv(output / 'plan_by_year.csv', [dict(year=y, tests=70, rounds=3, total_cases=210)
                                           for y in config['years']])
    summaries = []
    for number in (1, 2, 3):
        folder = output / mode / f'round-{number:02d}'
        info = run(config, folder, mode, approved=approved)
        summaries.append(dict(round=number, **info))
    result = dict(mode=mode, rounds=summaries, total_cases=sum(r['cases'] for r in summaries),
                  calls=sum(r['calls'] for r in summaries), output=str(output.resolve()))
    # Read-only verification of actual checkpoints, not just declared totals.
    import sqlite3
    for number in (1, 2, 3):
        checkpoint = output / mode / f'round-{number:02d}' / 'checkpoint.sqlite'
        with closing(sqlite3.connect(checkpoint.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            rows = [json.loads(s) for s, in db.execute('SELECT payload FROM cases')]
        expected_status = 'planned' if mode == 'dry-run' else 'success'
        if (len(rows) != 210 or Counter(r['year'] for r in rows) != {2023: 70, 2024: 70, 2025: 70}
                or any(r['status'] != expected_status for r in rows)):
            raise ValueError(f'E7 round {number} is not complete; inspect exclusions/errors')
    if mode == 'dry-run' and result['calls'] != 0:
        raise ValueError('Dry-run unexpectedly contains calls')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.openrouter.e7.json')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'results/error-informed/claude-opus-5.5/2023-2025')
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live'], default='dry-run')
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    if args.mode == 'live' and not args.approve_paid_api:
        parser.error('Live execution requires --approve-paid-api')
    try:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        config['data_dir'] = str((args.config.resolve().parent / config['data_dir']).resolve())
        load_dotenv(ROOT / '.env', override=False)
        print(json.dumps(execute(config, args.output, args.mode, args.approve_paid_api)))
    except (ValueError, KeyError, ImportError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
