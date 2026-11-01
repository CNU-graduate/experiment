"""One-shot P0/B/C error-complementarity experiment; no ensemble or test evaluation."""
import argparse
import itertools
import json
import re
from pathlib import Path

from .data import inputs, FIELDS
from .evaluation import write_csv
from .prompt_search import Calls, GUARD, OPTIMIZER, hash_value, load_plan as load_source, parse_candidates, read, save

VERSION = 'error-diversity-v1'
GENERATOR = OPTIMIZER + '''
Revise the supplied P0 once using only supplied development evidence.
Improve the target error without simply favoring Yes or No. Preserve correct
decisions illustrated by the counterexamples. These are automatically retrieved
examples, not verified semantic equivalents. Flag unsupported explanations.
Return JSON only: {"candidates":[{"prompt":"complete replacement instructions",
"change":"change and applicability boundary", "risk":"possible regressions"}]}.
Do not include examples, IDs, or substance-specific answer lists in the prompt.'''


def prepare(source, config, output):
    original = load_source(source)
    cfg = dict(original['config'])
    cfg.update(config)
    cfg['candidates'] = 1
    if not isinstance(cfg['examples_per_direction'], int) or cfg['examples_per_direction'] < 1:
        raise ValueError('examples_per_direction must be a positive integer')
    dev, selection = original['development'], original['selection']
    for rows in (dev, selection):
        if not rows or len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Empty data or duplicate IDs')
        if any(int(r['year']) >= 2023 or r['EFSA'] not in ('Yes', 'No') for r in rows):
            raise ValueError('Only labeled pre-2023 data is allowed')
    if {r['id'] for r in dev} & {r['id'] for r in selection}:
        raise ValueError('Development/selection ID overlap')
    if {tuple(r[f] for f in FIELDS) for r in dev} & {tuple(r[f] for f in FIELDS) for r in selection}:
        raise ValueError('Development/selection input overlap')
    plan = dict(version=VERSION, config=cfg, source_plan_hash=original['plan_hash'],
                p0=original['p0'], generator_system=GENERATOR, candidate_guard=GUARD,
                development=dev, selection=selection,
                expected_calls=len(dev) + 2 + 3 * len(selection))
    plan['plan_hash'] = hash_value(plan)
    path = Path(output) / 'plan.json'
    if path.exists() and read(path) != plan:
        raise ValueError('Plan changed; use a new output directory')
    save(path, plan)
    return plan


def load_plan(output):
    plan = read(Path(output) / 'plan.json')
    expected = plan.pop('plan_hash')
    if plan['version'] != VERSION or hash_value(plan) != expected:
        raise ValueError('Frozen plan changed')
    plan['plan_hash'] = expected
    return plan


def build_evidence(rows, predictions, cap):
    """Balanced errors and opposite-label correct cases; deterministic lexical retrieval."""
    by_id = {p['id']: p for p in predictions}
    if len(by_id) != len(rows) or set(by_id) != {r['id'] for r in rows}:
        raise ValueError('Incomplete development predictions')
    if any(by_id[r['id']]['actual'] != r['EFSA'] for r in rows):
        raise ValueError('Development label mismatch')
    errors = {label: sorted([r for r in rows if r['EFSA'] == label and
                             by_id[r['id']]['prediction'] != label], key=lambda r: r['id'])
              for label in ('No', 'Yes')}
    correct = {label: [r for r in rows if r['EFSA'] == label and
                       by_id[r['id']]['prediction'] == label] for label in ('No', 'Yes')}
    k = min(cap, *(len(x) for x in errors.values()), *(len(x) for x in correct.values()))
    if k == 0:
        raise ValueError('Both error directions and both correct-label groups are required; inspect development predictions')

    def similarity(a, b):
        tokens = lambda r: set(re.findall(r'\w+', (r['JMPR'] + ' ' + r['EU']).casefold()))
        x, y = tokens(a), tokens(b)
        return (a['purpose'] == b['purpose'], a['commodity'] == b['commodity'],
                len(x & y) / max(1, len(x | y)))

    def pack(r):
        return {'id': r['id'], **inputs(r), 'actual': r['EFSA'],
                'p0_prediction': by_id[r['id']]['prediction']}

    result = {'examples_per_group': k, 'available_errors': {s: len(v) for s, v in errors.items()}}
    for name, label, opposite in [('B', 'No', 'Yes'), ('C', 'Yes', 'No')]:
        chosen = errors[label][:k]
        remaining = sorted(correct[opposite], key=lambda r: r['id'])
        pairs = []
        for row in chosen:
            counter = max(remaining, key=lambda r: similarity(row, r))
            remaining.remove(counter)
            pairs.append({'target_error': pack(row), 'correct_counterexample': pack(counter)})
        result[name] = {'target': f'actual {label}, P0 predicted {opposite}', 'pairs': pairs}
    return result


def comparisons(predictions):
    maps = {n: {r['id']: r for r in rows} for n, rows in predictions.items()}
    ids = set(maps['P0'])
    if any(set(m) != ids for m in maps.values()):
        raise ValueError('Selection IDs differ')
    errors = {n: {i for i, r in m.items() if r['actual'] != r['prediction']} for n, m in maps.items()}
    return [{'a': a, 'b': b, 'shared_error_ids': sorted(errors[a] & errors[b]),
             'a_wrong_b_correct_ids': sorted(errors[a] - errors[b]),
             'a_correct_b_wrong_ids': sorted(errors[b] - errors[a]),
             'disagreement_count': sum(maps[a][i]['prediction'] != maps[b][i]['prediction'] for i in ids)}
            for a, b in itertools.combinations(maps, 2)]


def run(plan, output, mode, max_calls=None, baseline_only=False):
    calls = Calls(plan, output, mode, max_calls)
    folder = calls.folder
    dev, metrics = calls.evaluate(plan['p0'], plan['development'], 'development/P0')
    write_csv(folder / 'development_P0.csv', dev)
    save(folder / 'development_metrics.json', metrics)
    if baseline_only:
        return {'stage': 'baseline', 'metrics': metrics, 'calls': calls.count}
    evidence = build_evidence(plan['development'], dev, plan['config']['examples_per_direction'])
    save(folder / 'evidence.json', evidence)
    prompts = {'P0': plan['p0']}
    for name in ('B', 'C'):
        payload = {'p0': plan['p0'], 'development_feedback': evidence[name]}
        save(folder / f'{name}_optimizer_input.json', payload)
        raw = calls.call(f'generation/{name}', plan['generator_system'],
                         json.dumps(payload, ensure_ascii=False), 'generation')
        prompts[name] = parse_candidates(raw, 1, plan['candidate_guard'])[0]
        save(folder / f'{name}_candidate.json', {'raw': raw, 'prompt': prompts[name]})
    if len({p.strip() for p in prompts.values()}) != 3:
        raise ValueError('Identical prompts generated; inspect outputs, no automatic paid regeneration')
    save(folder / 'prompts.json', prompts)
    predictions, metrics = {}, {}
    for name, prompt in prompts.items():
        predictions[name], metrics[name] = calls.evaluate(prompt, plan['selection'], f'selection/{name}')
        write_csv(folder / f'selection_{name}.csv', predictions[name])
    pairs = comparisons(predictions)
    result = {'mode': mode, 'n': len(plan['selection']), 'metrics': metrics, 'pairs': pairs,
              'calls': calls.count, 'evidence_per_group': evidence['examples_per_group'],
              'note': 'Exploratory reused selection set; single draw per prompt. No voting or 2023 evaluation.'}
    save(folder / 'summary.json', result)
    write_csv(folder / 'metrics.csv', [{'condition': n, **m} for n, m in metrics.items()])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'baseline', 'run'])
    parser.add_argument('--source', default='results/prompt-search-2023')
    parser.add_argument('--config', default='config.error-diversity.json')
    parser.add_argument('--output', default='results/error-diversity-2023')
    parser.add_argument('--mode', choices=['mock', 'live'], default='mock')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    if args.stage == 'prepare':
        plan = prepare(args.source, read(args.config), args.output)
        print(json.dumps({'expected_calls': plan['expected_calls'], 'plan_hash': plan['plan_hash']}))
        return
    plan = load_plan(args.output)
    if args.mode == 'live':
        from dotenv import load_dotenv
        load_dotenv()
    lock = Path(args.output) / f'{args.mode}.lock'
    with lock.open('x'):
        pass
    try:
        result = run(plan, args.output, args.mode, args.max_calls, args.stage == 'baseline')
        print(json.dumps(result, ensure_ascii=True))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
