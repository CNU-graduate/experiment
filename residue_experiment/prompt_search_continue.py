"""Explicitly approve one continuation round of the completed v2 search."""
import argparse
import json
import uuid
from pathlib import Path

from .prompt_search import Calls, hash_value, load_plan, read, save, stratified_order
from .prompt_search_guarded import search_guarded


def fingerprint(request):
    return hash_value({k: request[k] for k in ('model', 'system', 'user', 'settings', 'kind')})


def repair_empty(plan, output, mode):
    """Archive completed empty predictions, preserving attempts for budget accounting.

    Caller must hold the run lock. No API calls are made here.
    """
    folder = Path(output) / mode
    repaired = []
    for path in sorted((folder / 'calls').glob('*.json')):
        record = read(path)
        if record['request']['plan_hash'] != plan['plan_hash']:
            raise ValueError('Continuation call plan mismatch')
        if (record['status'] == 'success'
                and record['request']['kind'] == 'prediction'
                and isinstance(record.get('response'), str)
                and not record['response'].strip()):
            archive = folder / 'empty_response_attempts'
            archive.mkdir(exist_ok=True)
            path.rename(archive / f'{path.stem}-{uuid.uuid4().hex}.json')
            repaired.append(record['request']['key'])
    return {'archived_empty_predictions': repaired, 'api_calls': 0}


def prepare(source, output):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('Continuation requires a separate output folder')
    old = load_plan(source)
    if not old['config'].get('cumulative_validation') or old['config'].get('development_feedback'):
        raise ValueError('Expected a v2 cumulative-validation source')
    best = read(source / 'live/final_prompt.json')
    state = read(source / 'live/round-05/selection.json')
    memory = read(source / 'live/round-05/memory.json')['ids']
    if best['plan_hash'] != old['plan_hash'] or best.get('completed_rounds') != 5:
        raise ValueError('Source must have completed exactly five rounds')
    if any(best[k] != state['winner'][k] for k in ('name', 'prompt', 'metrics')):
        raise ValueError('Source winner mismatch')
    dev = old['development']
    if len(dev) != 326 or len({r['id'] for r in dev}) != 326 or len(memory) != len(set(memory)):
        raise ValueError('Invalid development or memory IDs')
    if old['batches'] != [dev[i:i + 50] for i in range(0, 250, 50)]:
        raise ValueError('Source batches differ from the expected first 250 rows')
    # First epoch uses 300 cases; carry its excluded 26 into epoch two first.
    omitted = dev[300:]
    second = (stratified_order(omitted, old['config']['seed'] + 2) +
              stratified_order(dev[:300], old['config']['seed'] + 2))
    batches = old['batches'] + [dev[250:300]] + [second[i:i + 50] for i in range(0, 200, 50)]
    seed_records = {}
    for path in sorted((source / 'live/calls').glob('*.json')):
        record = read(path)
        req = record['request']
        if req['kind'] != 'prediction' or not req['key'].startswith(('development-cache/', 'selection/')):
            continue
        if req['plan_hash'] != old['plan_hash'] or record['status'] != 'success':
            raise ValueError(f'Invalid source cache: {path}')
        seed_records.setdefault(fingerprint(req), record)
    if not seed_records:
        raise ValueError('Source prediction cache unavailable; refusing paid reconstruction')
    seed_state = {'winner': state['winner'], 'memory_ids': memory,
                  'stale': 0, 'completed_rounds': 5}
    plan = {k: v for k, v in old.items() if k not in ('plan_hash', 'test', 'exact_test_input_overlap')}
    plan['config'] = dict(old['config'], rounds=10, manual_round_approval=True,
                          continuation_early_stop=True, patience=2)
    plan.update(batches=batches, seed_state=seed_state,
                continuation={'source': str(source.resolve()), 'source_plan_hash': old['plan_hash'],
                              'seed_cache_hash': hash_value(seed_records),
                              'source_stale': state['no_improvement_streak'],
                              'stale_reset_at_round': 6,
                              'epoch1_omitted_ids': [r['id'] for r in omitted],
                              'epoch2_order_ids': [r['id'] for r in second],
                              'note': 'R6 finishes 300 cases; R7-R10 use first 200 of the shuffled second epoch. No final evaluation.'},
                expected_calls=sum(50 + (50 + 10 * i) + 2 + 3 * 140 + 3 * (50 + 10 * i)
                                   for i in range(1, 6)))
    plan['plan_hash'] = hash_value(plan)
    target = output / 'plan.json'
    if target.exists() and read(target) != plan:
        raise ValueError('Continuation plan changed; use a new output folder')
    save(output / 'seed_cache.json', seed_records)
    save(target, plan)
    return plan


class ContinuationCalls(Calls):
    def __init__(self, plan, output, mode, max_calls=None):
        super().__init__(plan, output, mode, max_calls)
        self.count += len(list((self.folder / 'empty_response_attempts').glob('*.json')))
        self.count += len(list((self.folder / 'connection_error_attempts').glob('*.json')))
        seed = read(Path(output) / 'seed_cache.json')
        if hash_value(seed) != plan['continuation']['seed_cache_hash']:
            raise ValueError('Source cache snapshot changed')
        # Mock must never use real responses as mock predictions.
        self.cache = seed if mode == 'live' else {}
        self.cache_hits = 0
        for path in sorted(self.attempts.glob('*.json')):
            record = read(path)
            if record['request']['plan_hash'] != plan['plan_hash']:
                raise ValueError('Continuation call plan mismatch')
            if record['status'] != 'success':
                raise RuntimeError(f'Unresolved call {path}; inspect before any paid retry')
            if record['request']['kind'] == 'prediction':
                self.cache[fingerprint(record['request'])] = record

    def call(self, key, system, user, kind):
        cfg = self.plan['config']
        req = {'model': cfg['model'], 'system': system, 'user': user, 'kind': kind,
               'settings': {'api_backend': cfg['api_backend'], 'timeout_seconds': cfg['timeout_seconds'],
                            'max_output_tokens': cfg['prediction_tokens'] if kind == 'prediction' else cfg['optimizer_tokens']}}
        fp = fingerprint(req)
        if kind == 'prediction' and fp in self.cache:
            self.cache_hits += 1
            return self.cache[fp]['response']
        response = super().call(key, system, user, kind)
        if kind == 'prediction':
            self.cache[fp] = {'request': req, 'response': response}
        return response


def progress(plan, output, mode):
    state = plan['seed_state']
    for n in range(6, 11):
        folder = Path(output) / mode / f'round-{n:02d}'
        if not (folder / 'selection.json').exists():
            break
        selected = read(folder / 'selection.json')
        state = {'winner': selected['winner'], 'memory_ids': read(folder / 'memory.json')['ids'],
                 'stale': selected['no_improvement_streak'], 'completed_rounds': n}
    return state


def run_round(plan, output, mode, number, approved=False, max_calls=None):
    if not approved:
        raise ValueError('Explicit --approve-round is required for each round')
    if number not in range(6, 11):
        raise ValueError('Only rounds 6 through 10 are supported')
    state = progress(plan, output, mode)
    if number != state['completed_rounds'] + 1:
        raise ValueError(f'Next round is {state["completed_rounds"] + 1}; refusing repeated or skipped rounds')
    if (Path(output) / mode / 'final_prompt.json').exists():
        raise ValueError('Search already stopped; no further rounds are allowed')
    calls = ContinuationCalls(plan, output, mode, max_calls)
    before = calls.count
    save(calls.folder / f'approval-round-{number:02d}.json',
         {'plan_hash': plan['plan_hash'], 'approved_round': number,
          'call_cap': calls.limit, 'starting_calls': before, 'prior_no_improvement': state['stale']})
    result = search_guarded(plan, output, mode, max_calls, through_round=number,
                            calls_override=calls, resume_state=state)
    selected = read(calls.folder / f'round-{number:02d}/selection.json')
    return {'completed_round': number, 'winner': result['name'], 'metrics': result['metrics'],
            'new_calls': calls.count - before, 'continuation_calls': calls.count,
            'cache_hits': calls.cache_hits, 'no_improvement_streak': selected['no_improvement_streak'],
            'stagnation_warning': selected['stagnation_warning'],
            'stop_reason': selected['stop_reason'],
            'next_round_requires_approval': number + 1 if number < 10 and not selected['stop_reason'] else None}


def run_through(plan, output, mode, target, max_calls=None):
    """The explicit target authorizes all remaining rounds through that target."""
    if target not in range(6, 11):
        raise ValueError('Target must be between rounds 6 and 10')
    state = progress(plan, output, mode)
    folder = Path(output) / mode
    save(folder / f'approval-through-{target:02d}.json',
         {'plan_hash': plan['plan_hash'], 'approved_through_round': target,
          'completed_before_request': state['completed_rounds'],
          'call_cap': max_calls if max_calls is not None else plan['expected_calls']})
    results = []
    for number in range(state['completed_rounds'] + 1, target + 1):
        if (folder / 'final_prompt.json').exists():
            break
        result = run_round(plan, output, mode, number, True, max_calls)
        result['next_round_requires_approval'] = None if number < target else result['next_round_requires_approval']
        print(json.dumps(result, ensure_ascii=True), flush=True)
        results.append(result)
        if result.get('stop_reason'):
            break
    return {'completed_rounds': progress(plan, output, mode)['completed_rounds'],
            'rounds_run': [r['completed_round'] for r in results],
            'approved_through_round': target}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'status', 'run', 'repair-empty'])
    parser.add_argument('--source', default='results/prompt-search-2023-v2')
    parser.add_argument('--output', default='results/prompt-search-v2-continued-patience2')
    parser.add_argument('--mode', choices=['mock', 'live'], default='mock')
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument('--round', type=int)
    execution.add_argument('--through-round', type=int)
    parser.add_argument('--approve-round', action='store_true')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    if args.stage == 'prepare':
        plan = prepare(args.source, args.output)
        print(json.dumps({'start': plan['seed_state']['winner']['name'], 'next_round': 6,
                          'max_round': 10, 'additional_call_cap': plan['expected_calls']}))
        return
    plan = load_plan(args.output)
    if args.stage == 'status':
        state = progress(plan, args.output, args.mode)
        print(json.dumps({'completed_rounds': state['completed_rounds'],
                          'winner': state['winner']['name'], 'memory_size': len(state['memory_ids']),
                          'no_improvement_streak': state['stale'],
                          'additional_attempts': sum(len(list((Path(args.output) / args.mode / d).glob('*.json')))
                                                     for d in ('calls', 'empty_response_attempts'))}))
        return
    if args.stage == 'run' and args.through_round is None and (args.round is None or not args.approve_round):
        parser.error('Specify --through-round N, or --round N --approve-round')
    if args.mode == 'live':
        from dotenv import load_dotenv
        load_dotenv()
    lock = Path(args.output) / f'{args.mode}.lock'
    with lock.open('x'):
        pass
    try:
        if args.stage == 'repair-empty':
            result = repair_empty(plan, args.output, args.mode)
        elif args.through_round is not None:
            result = run_through(plan, args.output, args.mode, args.through_round, args.max_calls)
        else:
            result = run_round(plan, args.output, args.mode, args.round, args.approve_round, args.max_calls)
        print(json.dumps(result, ensure_ascii=True))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
