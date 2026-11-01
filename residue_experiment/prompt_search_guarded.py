"""Opt-in cumulative development validation; existing v1 runs stay unchanged."""
import json
import difflib
from pathlib import Path

from .data import inputs
from .evaluation import write_csv
from .prompt_search import Calls, hash_value, parse_candidates, read, save


def choose_memory(batch, predictions, limit):
    """Deterministic heuristic, not expert-reviewed semantic counterexample selection.

    Prefer up to six current errors, then label-balanced correct safeguards;
    fill unused slots with remaining errors. Never uses selection or test labels.
    """
    by_id = {p['id']: p for p in predictions}
    wrong = [r for r in batch if not by_id[r['id']]['correct']]
    correct = [r for r in batch if by_id[r['id']]['correct']]
    chosen = wrong[:min(6, limit)]
    groups = {label: [r for r in correct if r['EFSA'] == label] for label in ('No', 'Yes')}
    while len(chosen) < limit and any(groups.values()):
        for label in ('No', 'Yes'):
            if groups[label] and len(chosen) < limit:
                chosen.append(groups[label].pop(0))
    for row in wrong:
        if len(chosen) == limit:
            break
        if row['id'] not in {r['id'] for r in chosen}:
            chosen.append(row)
    return chosen


def eligibility(before, after, target_ids):
    old, new = {r['id']: r for r in before}, {r['id']: r for r in after}
    if set(old) != set(new):
        raise ValueError('Memory predictions have different IDs')
    fixed = [i for i in old if not old[i]['correct'] and new[i]['correct']]
    broken = [i for i in old if old[i]['correct'] and not new[i]['correct']]
    target_fixed = sorted(set(fixed) & set(target_ids))
    return {'eligible': bool(target_fixed) and len(fixed) >= len(broken),
            'target_fixed': target_fixed, 'fixed': fixed, 'broken': broken,
            'net_correct': len(fixed) - len(broken)}


def pick_winner(incumbent, candidates, require_memory_gate=True):
    eligible = [c for c in candidates if not require_memory_gate or c['gate']['eligible']]
    if not eligible:
        return incumbent, False
    winner = max(eligible, key=lambda c: (c['metrics']['accuracy'], c['metrics']['macro_f1'], -len(c['prompt'])))
    if winner['metrics']['accuracy'] <= incumbent['metrics']['accuracy']:
        return incumbent, False
    return winner, True


def development_feedback(number, parent, name, prompt, edit, memory, before, after):
    """Observed paired development changes, not causal claims or selection feedback."""
    old = {p['id']: p for p in before}
    new = {p['id']: p for p in after}
    if set(old) != set(new) or set(old) != {r['id'] for r in memory}:
        raise ValueError('Feedback must cover the same development memory IDs')
    changes = []
    for row in memory:
        a, b = old[row['id']], new[row['id']]
        if a['prediction'] != b['prediction']:
            changes.append(dict(inputs(row), id=row['id'], actual=row['EFSA'],
                                before=a['prediction'], after=b['prediction'],
                                outcome='corrected' if b['correct'] else 'regressed'))
    return {'round': number, 'parent_name': parent['name'], 'candidate_name': name,
            'declared_change': edit.get('change', ''), 'declared_risk': edit.get('risk', ''),
            'instruction_diff': '\n'.join(difflib.unified_diff(
                parent['prompt'].splitlines(), prompt.splitlines(),
                fromfile=parent['name'], tofile=name, lineterm='')),
            'evaluated_development_ids': [r['id'] for r in memory],
            'corrected_count': sum(c['outcome'] == 'corrected' for c in changes),
            'regressed_count': sum(c['outcome'] == 'regressed' for c in changes),
            'changed_cases': changes,
            'interpretation': 'Observed response changes only; no clause-level causality established.'}


def search_guarded(plan, output, mode, max_calls=None, through_round=None):
    calls = Calls(plan, output, mode, max_calls)
    final_path = calls.folder / 'final_prompt.json'
    if final_path.exists():
        result = read(final_path)
        if result['plan_hash'] != plan['plan_hash']:
            raise ValueError('Final prompt plan mismatch')
        return result
    cfg = plan['config']
    if through_round is not None and not 1 <= through_round <= cfg['rounds']:
        raise ValueError('through-round must be within configured rounds')
    stop = through_round or cfg['rounds']
    # Replay reuses identical per-prompt/per-item development requests, including
    # previous candidates that later become incumbents. Test repeats stay independent.
    memo = {}
    def development_eval(prompt, rows):
        ph = hash_value(prompt)
        missing = [r for r in rows if (ph, r['id']) not in memo]
        if missing:
            predicted, _ = calls.evaluate(prompt, missing, f'development-cache/{ph}')
            for p in predicted:
                memo[ph, p['id']] = p
        return [memo[ph, r['id']] for r in rows]

    baseline, metrics = calls.evaluate(plan['p0'], plan['selection'], 'selection/P0')
    write_csv(calls.folder / 'P0_selection_predictions.csv', baseline)
    best = {'name': 'P0', 'prompt': plan['p0'], 'metrics': metrics}
    memory, stale, history = [], 0, []
    feedback_enabled = cfg.get('development_feedback', False)
    require_gate = cfg.get('require_memory_gate', True)
    for number in range(1, stop + 1):
        folder = calls.folder / f'round-{number:02d}'
        folder.mkdir(exist_ok=True)
        batch = plan['batches'][number - 1]
        current = development_eval(best['prompt'], batch)
        write_csv(folder / 'development_predictions.csv', current)
        additions = choose_memory(batch, current, cfg['memory_per_round'])
        memory.extend(additions)
        incumbent_predictions = development_eval(best['prompt'], memory)
        write_csv(folder / 'incumbent_memory_predictions.csv', incumbent_predictions)
        target_ids = [p['id'] for p in current if not p['correct'] and p['id'] in {r['id'] for r in additions}]
        save(folder / 'memory.json', {'ids': [r['id'] for r in memory],
                                     'added_ids': [r['id'] for r in additions], 'target_ids': target_ids,
                                     'selection_method': 'errors first, then label-balanced correct safeguards'})
        def annotated(rows, predictions):
            return [dict(inputs(r), id=r['id'], actual=r['EFSA'], prediction=p['prediction'], correct=p['correct'])
                    for r, p in zip(rows, predictions)]
        scored, accepted, round_feedback = [], False, []
        if target_ids:
            analysis_input = {
                'current_instruction': best['prompt'], 'development_cases': annotated(batch, current),
                'accumulated_development_cases': annotated(memory, incumbent_predictions),
                'target_ids': target_ids,
                'task': 'Select one evidence-supported decision-rule defect to address. Explain its evidence, '
                        'exceptions, and counterexamples. Flag missing evidence instead of inventing equivalence. '
                        'Do not broaden a rule merely to reproduce a label. Preserve unrelated correct decisions.'
            }
            if feedback_enabled:
                analysis_input['previous_development_feedback'] = history
                analysis_input['task'] += (' Compare superficially similar cases with different labels and '
                    'past corrected/regressed cases. Infer applicability boundaries only from supplied evidence. '
                    'Past edits and response changes are observations, not proven causes. '
                    'Identify missing information rather than forcing a universal rule.')
                save(folder / 'optimizer_feedback_input.json', analysis_input)
            analysis = calls.call(f'analysis/{number}', plan['optimizer_system'],
                                  json.dumps(analysis_input, ensure_ascii=False), 'analysis')
            generation_input = {
                'current_instruction': best['prompt'], 'analysis': analysis,
                'development_evidence': annotated(memory, incumbent_predictions),
                'task': f'Produce {cfg["candidates"]} complete candidate instructions, each changing only the '
                        'identified rule. Try minimal amendment, explicit applicability/exception limits, and '
                        'deletion/rewrite. Preserve all unrelated rules. Give evidence IDs in the change description '
                        'only, not the instruction. Keep Yes/No-only output; no examples or answer lists. '
                        'Return JSON only: {"candidates":[{"prompt":"...","change":"...","risk":"..."}]}.'
            }
            if feedback_enabled:
                generation_input['previous_development_feedback'] = history
                generation_input['task'] += (' Use past development tradeoffs as evidence for revision, '
                    'not as hard constraints favoring either Yes or No. Explain unsupported distinctions '
                    'in the risk field rather than inventing facts.')
            raw = calls.call(f'generation/{number}', plan['optimizer_system'],
                             json.dumps(generation_input, ensure_ascii=False), 'generation')
            prompts = parse_candidates(raw, cfg['candidates'], plan['candidate_guard'])
            save(folder / 'candidates.json', {'analysis': analysis, 'raw': json.loads(raw), 'prompts': prompts})
            for index, prompt in enumerate(prompts, 1):
                name = f'R{number}C{index}'
                validation, metrics = calls.evaluate(prompt, plan['selection'], f'selection/{name}')
                write_csv(folder / f'{name}_predictions.csv', validation)
                replay = development_eval(prompt, memory)
                write_csv(folder / f'{name}_memory_predictions.csv', replay)
                gate = eligibility(incumbent_predictions, replay, target_ids)
                scored.append({'name': name, 'prompt': prompt, 'metrics': metrics, 'gate': gate})
                if feedback_enabled:
                    round_feedback.append(development_feedback(number, best, name, prompt,
                        json.loads(raw)['candidates'][index - 1], memory, incumbent_predictions, replay))
            best, accepted = pick_winner(best, scored, require_memory_gate=require_gate)
        if feedback_enabled:
            save(folder / 'development_feedback.json', round_feedback)
            history.extend(round_feedback)
        stale = 0 if accepted else stale + 1
        reason = 'patience' if stale >= cfg['patience'] else ('max_rounds' if number == cfg['rounds'] else None)
        save(folder / 'selection.json', {'candidates': scored, 'winner': best, 'accepted': accepted,
             'no_improvement_streak': stale, 'stop_reason': reason,
             'memory_gate_applied': require_gate,
             'skipped': None if target_ids else 'No current development errors'})
        print(f'Round {number}: winner={best["name"]}; memory={len(memory)}; no-improvement={stale}', flush=True)
        if reason:
            final = {'plan_hash': plan['plan_hash'], **best, 'completed_rounds': number, 'stop_reason': reason}
            save(final_path, final)
            return final
    return best
