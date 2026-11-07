"""Contemporaneous three-round comparison of full E6-guided (C0) and H1."""
import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from statistics import mean, stdev

from dotenv import load_dotenv

from . import e6_ablation as ablation
from . import e6_guided as guided
from .evaluation import score, write_csv
from .instruction_repeats import read_csv, save_json
from .prompt import parse_label
from .runner import run

ROOT = guided.ROOT
VERSION = 'e6-h1-v1'
CONDITIONS = ('C0', 'H1')
ROUNDS = (1, 2, 3)
SCHEDULE = [('C0', 1), ('H1', 1), ('H1', 2), ('C0', 2), ('C0', 3), ('H1', 3)]
DEFAULT_OUTPUT = ROOT/'results'/VERSION/'gpt-6-sol/2023-2025'
REPLACEMENT = """1. Separate component correspondence from assessment structure.
First identify the independently defined residue relevant to the named
substance when the text explicitly says substances are assessed separately;
do not automatically combine separate definitions or discard another
applicable definition. Then compare how the corresponding components are
assessed: a combined sum and independent assessments can differ even when
the named components correspond. Do not erase a stated structural difference
merely because the same substances occur on both sides. Preserve differences
in expression basis, conversion, or toxicity weighting when stated.
Numbering alone does not establish independent assessment. Do not invent
an assessment structure or equivalence that the supplied text does not support.

"""
PROMPTS = {'C0': guided.GUIDED_SYSTEM,
           'H1': guided.GUIDED_SYSTEM.replace(ablation.REMOVED['G1'], REPLACEMENT, 1)}


def child_config(config, condition, number):
    result = copy.deepcopy(config)
    result.update(h1_version=VERSION, h1_condition=condition, h1_round=number)
    return result


def prepare():
    # Reuse archive-only validation; none of its execute/live functions are called.
    config, _, old_plan, _ = ablation.prepare()
    expected = {}
    for c in CONDITIONS:
        with tempfile.TemporaryDirectory(prefix='e6-h1-check-') as temp:
            folder = Path(temp)
            info = run(child_config(config, c, 1), folder, 'dry-run', system_prompt=PROMPTS[c])
            rows = read_csv(folder/'predictions.csv')
            if info != {'cases': 210, 'calls': 0} or any(r['status'] != 'planned' for r in rows):
                raise ValueError('Expected 210 planned H1 comparison cases and zero calls')
            if (guided.prompts(folder) != guided.prompts(ablation.HISTORICAL[0])
                    or ablation.examples(folder) != ablation.examples(ablation.HISTORICAL[0])):
                raise ValueError('H1 comparison inputs/examples differ from archived E6-guided')
            expected[c] = {r['id']: r for r in rows}
    plan = dict(version=VERSION, config=config, conditions=list(CONDITIONS), rounds=list(ROUNDS),
                cases_per_run=210, total_cases=1260,
                schedule=[dict(condition=c, round=n) for c, n in SCHEDULE],
                system_prompts=PROMPTS, replaced_block=ablation.REMOVED['G1'], replacement=REPLACEMENT,
                reference_validation=old_plan,
                preflight=dict(calls=0, inputs_and_examples_match=True),
                note='C0 and H1 each run three times; block order alternates by round. '
                     'Known 210-case development benchmark, not an unseen independent test.')
    return config, plan, expected


def aggregate(output, mode, config, expected):
    dest = output/mode/'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    metrics, summaries, resources, by_condition = [], [], [], {}
    for c in CONDITIONS:
        rounds = []
        for n in ROUNDS:
            folder = output/mode/c/f'round-{n:02d}'
            rows = read_csv(folder/'predictions.csv') if (folder/'predictions.csv').exists() else []
            calls = read_csv(folder/'api_calls.csv') if (folder/'api_calls.csv').exists() else []
            if rows:
                manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
                if (manifest['mode'] != mode or manifest['system_prompt'] != PROMPTS[c]
                        or manifest['config'] != child_config(config, c, n)):
                    raise ValueError('H1 comparison manifest mismatch')
            if len({r['id'] for r in rows}) != len(rows):
                raise ValueError('Duplicate prediction ID')
            successful = {json.loads(r['case_key'])[3]: r for r in calls if r['status'] == 'success'}
            for r in rows:
                target = expected[c].get(r['id'])
                if (target is None or r['mode'] != mode or any(r[k] != target[k] for k in
                        ('year', 'actual', 'condition', 'seed', 'provider', 'model', 'prompt_sha256'))):
                    raise ValueError('H1 prediction differs from frozen plan')
                if r['status'] == 'success':
                    call = successful.get(r['id'])
                    if call is None or parse_label(call['response']) != r['prediction']:
                        raise ValueError('Prediction differs from saved response')
            rounds.append({r['id']: r for r in rows})
            resources.append(dict(condition=c, round=n, api_attempts=len(calls),
                                  failed_attempts=sum(r['status'] == 'error' for r in calls),
                                  unfinished_attempts=sum(r['status'] not in ('success', 'error') for r in calls)))
            for year in (2023, 2024, 2025, 'all'):
                total = sum(year == 'all' or int(t['year']) == year for t in expected[c].values())
                valid = [r for r in rows if r['status'] == 'success'
                         and (year == 'all' or int(r['year']) == year)]
                values = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {
                    k: '' for k in ('accuracy', 'precision', 'recall', 'macro_f1', 'tn', 'fp', 'fn', 'tp')}
                metrics.append(dict(condition=c, round=n, year=year, n_total=total,
                                    n_evaluated=len(valid), coverage=len(valid)/total,
                                    complete=len(valid) == total, **values))
        by_condition[c] = rounds
        for year in (2023, 2024, 2025, 'all'):
            reps = [r for r in metrics if r['condition'] == c and r['year'] == year and r['complete']]
            row = dict(condition=c, year=year, repeats_complete=len(reps), repeats_planned=3)
            for field in ('accuracy', 'macro_f1'):
                vals = [r[field] for r in reps]
                row[field+'_mean'] = mean(vals) if vals else ''
                row[field+'_std'] = stdev(vals) if len(vals) > 1 else (0.0 if vals else '')
            summaries.append(row)
    frequency = []
    for ident, target in sorted(expected['C0'].items()):
        row = dict(id=ident, year=target['year'], actual=target['actual'])
        for c in CONDITIONS:
            observed = [rs.get(ident) for rs in by_condition[c]]
            valid = [r for r in observed if r and r['status'] == 'success']
            row[c+'_valid_runs'] = len(valid)
            row[c+'_wrong_count'] = sum(r['prediction'] != target['actual'] for r in valid)
            for n, r in enumerate(observed, 1):
                row[f'{c}_round_{n}'] = r['prediction'] if r and r['status'] == 'success' else ''
        complete = row['C0_valid_runs'] == row['H1_valid_runs'] == 3
        row.update(complete=complete,
                   recovered_repeat_error=(row['C0_wrong_count'] >= 2 and row['H1_wrong_count'] == 0) if complete else '',
                   damaged_stable_correct=(row['C0_wrong_count'] == 0 and row['H1_wrong_count'] > 0) if complete else '')
        frequency.append(row)
    write_csv(dest/'round_metrics.csv', metrics)
    write_csv(dest/'condition_summary.csv', summaries)
    write_csv(dest/'error_frequency.csv', frequency)
    write_csv(dest/'resources.csv', resources)
    write_csv(dest/'comparison.csv', [dict(n_total=210, n_complete=sum(r['complete'] for r in frequency),
                                         recovered_repeat_errors=sum(r['recovered_repeat_error'] is True for r in frequency),
                                         damaged_stable_correct=sum(r['damaged_stable_correct'] is True for r in frequency))])
    return summaries


def execute(output=DEFAULT_OUTPUT, mode='dry-run', approved=False, condition=None, only_round=None):
    if mode not in ('dry-run', 'mock', 'live', 'analyze'):
        raise ValueError('Invalid mode')
    if mode == 'live' and not approved:
        raise ValueError('Live requires --approve-paid-api')
    if condition not in (None, *CONDITIONS) or only_round not in (None, *ROUNDS):
        raise ValueError('Use C0/H1 and rounds 1/2/3')
    output = Path(output).resolve()
    allowed = DEFAULT_OUTPUT.resolve()
    if (output == ROOT or ROOT in output.parents) and output != allowed and allowed not in output.parents:
        raise ValueError('Use dedicated H1 output tree or a directory outside the repository')
    config, plan, expected = prepare()
    if mode == 'analyze' and not (output/'plan.json').exists():
        raise ValueError('No existing H1 plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty new output directory')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.run.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text(encoding='utf-8-sig')) != plan:
                raise ValueError('Code/data/baseline changed; use a new version/output')
        else:
            save_json(output/'plan.json', plan)
            save_json(output/'system_prompts.json', PROMPTS)
        if mode == 'analyze':
            return dict(calls=0, analysis=aggregate(output, 'live', config, expected))
        results = []
        try:
            for c, n in SCHEDULE:
                if (condition is not None and c != condition) or (only_round is not None and n != only_round):
                    continue
                print(f'{c} round {n}/3: 210 cases; {mode}', flush=True)
                results.append(run(child_config(config, c, n), output/mode/c/f'round-{n:02d}', mode,
                                   approved=approved, system_prompt=PROMPTS[c]))
        finally:
            aggregate(output, mode, config, expected)
        return dict(mode=mode, cases=sum(r['cases'] for r in results),
                    calls=sum(r['calls'] for r in results), runs=len(results), output=str(output))
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['dry-run', 'mock', 'live', 'analyze'], default='dry-run')
    parser.add_argument('--condition', choices=CONDITIONS)
    parser.add_argument('--round', type=int, choices=ROUNDS, dest='only_round')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--approve-paid-api', action='store_true')
    args = parser.parse_args()
    try:
        if args.mode == 'live':
            load_dotenv(ROOT/'.env', override=False)
        print(json.dumps(execute(args.output, args.mode, args.approve_paid_api,
                                 args.condition, args.only_round), ensure_ascii=False))
    except (ValueError, KeyError, ImportError, OSError) as exc:
        parser.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
