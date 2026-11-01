"""Evaluate a frozen search winner on later years, without further optimization."""
import argparse
from pathlib import Path
from statistics import mean

from .data import Dataset, FIELDS
from .evaluation import write_csv
from .prompt_search import Calls, hash_value, load_plan as load_search, read, save

VERSION = 'prompt-transfer-v1'


def prepare(source, output, years=(2024, 2025), repeats=3):
    years = sorted(set(years))
    if not years or any(y not in (2024, 2025) for y in years) or repeats < 1:
        raise ValueError('Use years 2024/2025 and positive repeats')
    search = load_search(source)
    live = Path(source) / 'live'
    best = read(live / 'final_prompt.json')
    if best['plan_hash'] != search['plan_hash']:
        raise ValueError('Winner belongs to another plan')
    completed = best.get('completed_rounds', search['config']['rounds'])
    if not 1 <= completed <= search['config']['rounds']:
        raise ValueError('Invalid completed rounds')
    winner = read(live / f'round-{completed:02d}' / 'selection.json')['winner']
    if (winner['name'], winner['prompt']) != (best['name'], best['prompt']):
        raise ValueError('Final prompt differs from search winner')
    dataset = Dataset(search['config']['data_dir'])
    tests = {str(y): dataset.tests[y] for y in years}
    past = {tuple(r[f] for f in FIELDS) for r in search['development'] + search['selection']}
    plan = {'version': VERSION, 'source_plan_hash': search['plan_hash'],
            'source': str(Path(source).resolve()), 'config': search['config'],
            'p0': search['p0'], 'final_prompt': best['prompt'], 'final_name': best['name'],
            'years': years, 'repeats': repeats, 'tests': tests,
            'past_input_overlap': {y: [r['id'] for r in rows if tuple(r[f] for f in FIELDS) in past]
                                   for y, rows in tests.items()},
            'expected_calls': 2 * repeats * sum(len(rows) for rows in tests.values())}
    plan['plan_hash'] = hash_value(plan)
    path = Path(output) / 'plan.json'
    if path.exists() and read(path) != plan:
        raise ValueError('Frozen plan differs; use a new --output directory')
    save(path, plan)
    return plan


def load_plan(output):
    plan = read(Path(output) / 'plan.json')
    expected = plan.pop('plan_hash')
    if plan['version'] != VERSION or hash_value(plan) != expected:
        raise ValueError('Frozen transfer plan changed')
    plan['plan_hash'] = expected
    return plan


def run(plan, output, mode, max_calls=None):
    calls = Calls(plan, output, mode, max_calls)
    summaries = {}
    for year in plan['years']:
        rows = plan['tests'][str(year)]
        folder = calls.folder / str(year)
        folder.mkdir(exist_ok=True)
        predictions, metrics = [], []
        for repeat in range(1, plan['repeats'] + 1):
            for condition, prompt in [('P0', plan['p0']), ('final', plan['final_prompt'])]:
                ps, ms = calls.evaluate(prompt, rows, f'test/{year}/{condition}/{repeat}')
                predictions.extend(dict(p, condition=condition, repeat=repeat) for p in ps)
                metrics.append(dict(condition=condition, repeat=repeat, **ms))
        write_csv(folder / 'test_predictions.csv', predictions)
        write_csv(folder / 'test_metrics.csv', metrics)
        changes = []
        for row in rows:
            wrong = {c: sum(not p['correct'] for p in predictions
                            if p['id'] == row['id'] and p['condition'] == c) for c in ('P0', 'final')}
            changes.append({'id': row['id'], 'actual': row['EFSA'], 'P0_wrong': wrong['P0'],
                            'final_wrong': wrong['final'],
                            'fully_corrected': wrong['P0'] == plan['repeats'] and wrong['final'] == 0,
                            'new_error': wrong['P0'] == 0 and wrong['final'] > 0})
        write_csv(folder / 'test_changes.csv', changes)
        summaries[str(year)] = {c: {
            'accuracy_mean': mean(m['accuracy'] for m in metrics if m['condition'] == c),
            'macro_f1_mean': mean(m['macro_f1'] for m in metrics if m['condition'] == c),
            'fp_total': sum(m['fp'] for m in metrics if m['condition'] == c),
            'fn_total': sum(m['fn'] for m in metrics if m['condition'] == c)} for c in ('P0', 'final')}
        save(folder / 'test_summary.json', summaries[str(year)])
        print(f'{year}: completed {len(rows)} cases x 2 prompts x {plan["repeats"]} repeats')
    result = {'mode': mode, 'final_name': plan['final_name'], 'repeats': plan['repeats'],
              'metrics': summaries, 'calls': calls.count,
              'note': 'Frozen prompt transfer; no optimization. Prior use of these years in other experiments must be disclosed.'}
    save(calls.folder / 'summary.json', result)
    return result


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'run'])
    parser.add_argument('--source', default='results/prompt-search-2023-v2')
    parser.add_argument('--output', default='results/prompt-search-v2-transfer-2024-2025')
    parser.add_argument('--years', nargs='+', type=int, default=[2024, 2025])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--mode', choices=['mock', 'live'], default='mock')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    if args.stage == 'prepare':
        plan = prepare(args.source, args.output, args.years, args.repeats)
        print(json.dumps({k: plan[k] for k in ('final_name', 'years', 'repeats', 'expected_calls', 'past_input_overlap')}))
        return
    plan = load_plan(args.output)
    if args.years != [2024, 2025] or args.repeats != 3 or args.source != 'results/prompt-search-2023-v2':
        parser.error('--years, --repeats, --source are prepare-only; run uses the frozen plan')
    if args.mode == 'live':
        from dotenv import load_dotenv
        load_dotenv()
    lock = Path(args.output) / f'{args.mode}.lock'
    with lock.open('x'):
        pass
    try:
        print(json.dumps(run(plan, args.output, args.mode, args.max_calls), ensure_ascii=True))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
