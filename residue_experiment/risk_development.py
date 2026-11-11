"""Complete the frozen winner's risk-assessment development predictions only."""
import argparse
import json
from pathlib import Path

from .data import FIELDS
from .evaluation import score, write_csv
from .prompt import build_prompt, parse_label
from .prompt_search import Calls, hash_value, load_plan as load_search, read, save

SOURCE = 'results/prompt-search-v2-continued-patience2'
OUTPUT = 'results/r6c1-risk-development'
VERSION = 'risk-development-v1'


def prepare(source, output):
    if Path(source).resolve() == Path(output).resolve():
        raise ValueError('Use a separate output folder')
    search = load_search(source)
    best = read(Path(source) / 'live/final_prompt.json')
    if best['plan_hash'] != search['plan_hash'] or best['name'] != 'R6C1':
        raise ValueError('Expected the frozen R6C1 winner')
    winner = read(Path(source) / 'live' / f'round-{best["completed_rounds"]:02d}' / 'selection.json')['winner']
    if winner['prompt'] != best['prompt'] or winner['name'] != best['name']:
        raise ValueError('Winner mismatch')
    rows = [r for r in search['development'] if r['purpose'] == 'Risk assessment']
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate development IDs')
    cfg = search['config']
    settings = {'api_backend': cfg['api_backend'], 'timeout_seconds': cfg['timeout_seconds'],
                'max_output_tokens': cfg['prediction_tokens']}
    users = {build_prompt(r, []): r['id'] for r in rows}
    reused = {}
    for path in sorted((Path(source) / 'live/calls').glob('*.json')):
        record = read(path)
        req = record['request']
        if (record['status'] != 'success' or req.get('kind') != 'prediction'
                or req.get('plan_hash') != search['plan_hash']
                or req.get('system') != best['prompt'] or req.get('model') != cfg['model']
                or req.get('settings') != settings or req.get('user') not in users):
            continue
        try:
            label = parse_label(record['response'])
        except ValueError:
            continue
        ident = users[req['user']]
        if ident in reused and reused[ident]['prediction'] != label:
            raise ValueError(f'Conflicting source responses for {ident}')
        reused.setdefault(ident, {'prediction': label, 'source_path': str(path.resolve()),
                                  'record_hash': hash_value(record)})
    plan = {'version': VERSION, 'source': str(Path(source).resolve()),
            'source_plan_hash': search['plan_hash'], 'config': cfg,
            'prompt': best['prompt'], 'name': best['name'], 'rows': rows, 'reused': reused,
            'expected_calls': len(rows) - len(reused)}
    plan['plan_hash'] = hash_value(plan)
    target = Path(output) / 'plan.json'
    if target.exists() and read(target) != plan:
        raise ValueError('Frozen plan differs; use a new output folder')
    save(target, plan)
    return plan


def load_plan(output):
    plan = read(Path(output) / 'plan.json')
    digest = plan.pop('plan_hash')
    if plan['version'] != VERSION or hash_value(plan) != digest:
        raise ValueError('Frozen plan changed')
    plan['plan_hash'] = digest
    return plan


def run(plan, output, mode, max_calls=None):
    calls = Calls(plan, output, mode, max_calls)
    results = []
    for row in plan['rows']:
        ident = row['id']
        cached = plan['reused'].get(ident)
        if cached:
            # Mock output never presents a historical live prediction as mock inference.
            label = cached['prediction'] if mode == 'live' else row['EFSA']
        else:
            label = parse_label(calls.call(f'risk-development/{ident}', plan['prompt'],
                                           build_prompt(row, []), 'prediction'))
        results.append(dict(id=ident, year=row['year'], **{k: row[k] for k in FIELDS},
                            actual=row['EFSA'], prediction=label, correct=label == row['EFSA'],
                            origin='reused' if cached else 'additional',
                            source_path=cached['source_path'] if cached else ''))
        print(f'{len(results)}/{len(plan["rows"])}: {ident}; '
              f'{"reused" if cached else "additional"}; calls={calls.count}', flush=True)
    write_csv(calls.folder / 'predictions.csv', results)
    write_csv(calls.folder / 'errors.csv', [r for r in results if not r['correct']],
              fields=list(results[0]))
    summary = {'mode': mode, 'name': plan['name'], 'cases': len(results),
               'reused': len(plan['reused']), 'additional_cases': plan['expected_calls'],
               'calls': calls.count, 'metrics': score([r['actual'] for r in results],
                                                    [r['prediction'] for r in results]),
               'note': 'Development audit only, not held-out performance; no prompt optimization.'}
    save(calls.folder / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'run'])
    parser.add_argument('--source', default=SOURCE)
    parser.add_argument('--output', default=OUTPUT)
    parser.add_argument('--mode', choices=['mock', 'live'], default='mock')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    if args.stage == 'prepare':
        plan = prepare(args.source, args.output)
        print(json.dumps({'cases': len(plan['rows']), 'reused': len(plan['reused']),
                          'additional_calls': plan['expected_calls']}))
        return
    plan = load_plan(args.output)
    if args.mode == 'live':
        from dotenv import load_dotenv
        load_dotenv()
    lock = Path(args.output) / f'{args.mode}.lock'
    with lock.open('x'):
        pass
    try:
        print(json.dumps(run(plan, args.output, args.mode, args.max_calls)))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
