"""G1/G2/G3: remove one added E6-guided rule, exactly two rounds per condition."""
import argparse
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from statistics import mean, stdev

from dotenv import load_dotenv

from . import e6_guided as guided
from .evaluation import score, write_csv
from .instruction_repeats import read_csv, save_json
from .prompt import SYSTEM, parse_label
from .runner import run

ROOT = guided.ROOT
VERSION = 'e6-guided-ablation-v1'
CONDITIONS = ('G1', 'G2', 'G3')
ROUNDS = (1, 2)
SCHEDULE = [('G1', 1), ('G2', 1), ('G3', 1), ('G3', 2), ('G2', 2), ('G1', 2)]
DEFAULT_OUTPUT = ROOT/'results'/VERSION/'gpt-6-sol/2023-2025'
HISTORICAL = [guided.DEFAULT_OUTPUT/'live'/f'round-{n:02d}' for n in (1, 2, 3)]

# Preserve all original characters and numbering of the remaining paragraphs.
# These blocks intentionally include their following blank line.
BLOCKS = tuple(guided.ADDITION.split('\n\n')[n] + '\n\n' for n in (1, 2, 3))
REMOVED = dict(zip(CONDITIONS, BLOCKS))
PROMPTS = {c: guided.GUIDED_SYSTEM.replace(block, '', 1) for c, block in REMOVED.items()}


def child_config(config, condition, number):
    child = copy.deepcopy(config)
    child.update(ablation_version=VERSION, ablation_condition=condition, ablation_round=number)
    return child


def examples(folder):
    return sorted(tuple(r[k] for k in ('id', 'rank', 'example_id', 'example_year', 'example_label'))
                  for r in read_csv(folder/'examples.csv') if r['condition'] == 'E6')


def prepare():
    config, _, original_plan, _ = guided.prepare()
    historical, files = [], []
    old_inputs = None
    for folder in HISTORICAL:
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
        cfg = manifest['config']
        if (manifest['mode'] != 'live' or manifest['system_prompt'] != guided.GUIDED_SYSTEM
                or any(cfg[k] != config[k] for k in
                       (*guided.REQUEST_FIELDS, 'years', 'models', 'conditions', 'seeds'))
                or cfg.get('response_format', 'label') != 'label'
                or manifest['annotation_files'] != original_plan['annotation_files']):
            raise ValueError('Archived E6-guided manifest mismatch')
        rows = read_csv(folder/'predictions.csv')
        inputs = guided.prompts(folder)
        if (len(rows) != 210 or len({r['id'] for r in rows}) != 210 or len(inputs) != 210
                or any(r['status'] != 'success' or r['mode'] != 'live'
                       or r['condition'] != 'E6' or r['seed'] != '42'
                       or r['provider'] != 'openai' or r['model'] != guided.MODEL
                       or r['prediction'] not in ('Yes', 'No') for r in rows)):
            raise ValueError('Archived E6-guided needs 210 valid unique predictions')
        if old_inputs is not None and inputs != old_inputs:
            raise ValueError('Archived E6-guided user inputs differ')
        old_inputs = inputs
        historical.append(rows)
        for name in ('manifest.json', 'predictions.csv', 'prompts.jsonl', 'examples.csv'):
            files.append(dict(file=str((folder/name).relative_to(ROOT)), sha256=guided.sha(folder/name)))
    expected = {}
    for condition in CONDITIONS:
        with tempfile.TemporaryDirectory(prefix='e6-ablation-preflight-') as temp:
            folder = Path(temp)
            info = run(child_config(config, condition, 1), folder, 'dry-run',
                       system_prompt=PROMPTS[condition])
            rows = read_csv(folder/'predictions.csv')
            if (info != {'cases': 210, 'calls': 0}
                    or any(r['status'] != 'planned' for r in rows)
                    or guided.prompts(folder) != old_inputs):
                raise ValueError('Ablation plan has exclusions or changed user inputs')
            for archived, old_rows in zip(HISTORICAL, historical):
                if examples(folder) != examples(archived):
                    raise ValueError('Ablation examples/order differ from E6-guided')
                old = {r['id']: r for r in old_rows}
                if any(r['id'] not in old or r['actual'] != old[r['id']]['actual']
                       or r['year'] != old[r['id']]['year'] for r in rows):
                    raise ValueError('Ablation labels/years differ from E6-guided')
            expected[condition] = {r['id']: r for r in rows}
    plan = dict(version=VERSION, config=config, rounds=list(ROUNDS),
                conditions=list(CONDITIONS), cases_per_run=210, total_cases=1260,
                schedule=[dict(condition=c, round=n) for c, n in SCHEDULE],
                historical_rounds=3, historical_calls=0,
                system_prompts=PROMPTS, removed_blocks=REMOVED,
                historical_files=files, original_e6_files=original_plan['baseline_files'],
                data_files=original_plan['data_files'], annotation_files=original_plan['annotation_files'],
                implementation={p.name: guided.sha(p) for p in sorted((ROOT/'residue_experiment').glob('*.py'))},
                preflight=dict(calls=0, examples_and_inputs_match=True),
                comparison_note='Historical full-guided baseline has 3 rounds; each ablation has 2. '
                                'Different execution dates; exploratory, not a contemporaneous control.')
    return config, historical, plan, expected


def aggregate(output, mode, config, historical, expected):
    dest = output/mode/'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    metrics, summaries, resources, frequencies = [], [], [], []
    targets = expected['G1']
    historical_by_id = [{r['id']: r for r in rows} for rows in historical]
    for condition in ('E6-guided-historical', *CONDITIONS):
        is_old = condition == 'E6-guided-historical'
        planned = 3 if is_old else 2
        rounds = historical if is_old else []
        if not is_old:
            for n in ROUNDS:
                folder = output/mode/condition/f'round-{n:02d}'
                rows = read_csv(folder/'predictions.csv') if (folder/'predictions.csv').exists() else []
                calls = read_csv(folder/'api_calls.csv') if (folder/'api_calls.csv').exists() else []
                if rows:
                    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
                    if (manifest['mode'] != mode or manifest['system_prompt'] != PROMPTS[condition]
                            or manifest['config'] != child_config(config, condition, n)):
                        raise ValueError('Ablation result manifest mismatch')
                if len({r['id'] for r in rows}) != len(rows):
                    raise ValueError('Duplicate ablation prediction')
                successful_calls = {}
                for call in calls:
                    if call['status'] == 'success':
                        successful_calls[json.loads(call['case_key'])[3]] = call
                for r in rows:
                    target = expected[condition].get(r['id'])
                    fields = ('actual', 'year', 'condition', 'seed', 'provider', 'model', 'prompt_sha256')
                    if target is None or r['mode'] != mode or any(r[k] != target[k] for k in fields):
                        raise ValueError('Ablation prediction differs from frozen plan')
                    if r['status'] == 'success':
                        call = successful_calls.get(r['id'])
                        if call is None or parse_label(call['response']) != r['prediction']:
                            raise ValueError('Prediction differs from saved successful API response')
                resources.append(dict(condition=condition, round=n, api_attempts=len(calls),
                                      failed_attempts=sum(c['status'] == 'error' for c in calls),
                                      unfinished_attempts=sum(c['status'] not in ('success', 'error') for c in calls)))
                rounds.append(rows)
        for n, rows in enumerate(rounds, 1):
            for year in (2023, 2024, 2025, 'all'):
                denominator = sum(year == 'all' or int(t['year']) == year for t in targets.values())
                valid = [r for r in rows if r['status'] == 'success'
                         and (year == 'all' or int(r['year']) == year)]
                values = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {
                    k: '' for k in ('accuracy', 'precision', 'recall', 'macro_f1', 'tn', 'fp', 'fn', 'tp')}
                metrics.append(dict(condition=condition, historical=is_old, round=n, year=year,
                                    n_total=denominator, n_evaluated=len(valid), coverage=len(valid)/denominator,
                                    complete=len(valid) == denominator, **values))
        for year in (2023, 2024, 2025, 'all'):
            reps = [r for r in metrics if r['condition'] == condition and r['year'] == year and r['complete']]
            row = dict(condition=condition, historical=is_old, year=year,
                       repeats_complete=len(reps), repeats_planned=planned)
            for field in ('accuracy', 'macro_f1'):
                values = [r[field] for r in reps]
                row[field+'_mean'] = mean(values) if values else ''
                row[field+'_std'] = stdev(values) if len(values) > 1 else (0.0 if values else '')
            summaries.append(row)
        if is_old:
            continue
        by_id = [{r['id']: r for r in rows} for rows in rounds]
        for ident, t in sorted(targets.items()):
            old_wrong = sum(rows[ident]['prediction'] != t['actual'] for rows in historical_by_id)
            observed = [rows.get(ident) for rows in by_id]
            valid = [r for r in observed if r and r['status'] == 'success']
            wrong = sum(r['prediction'] != t['actual'] for r in valid)
            complete = len(valid) == 2
            frequencies.append(dict(condition=condition, id=ident, year=t['year'], actual=t['actual'],
                                    historical_wrong_count=old_wrong, historical_valid_runs=3,
                                    valid_runs=len(valid), repeats_planned=2, wrong_count=wrong,
                                    complete=complete,
                                    historical_wrong_rate=old_wrong/3,
                                    wrong_rate=wrong/len(valid) if valid else '',
                                    recovered_repeat_error=(old_wrong >= 2 and wrong == 0) if complete else '',
                                    damaged_stable_correct=(old_wrong == 0 and wrong > 0) if complete else '',
                                    **{f'round_{n}_prediction': r['prediction'] if r and r['status'] == 'success' else ''
                                       for n, r in enumerate(observed, 1)}))
    write_csv(dest/'round_metrics.csv', metrics)
    write_csv(dest/'condition_summary.csv', summaries)
    write_csv(dest/'error_frequency.csv', frequencies)
    write_csv(dest/'resources.csv', resources)
    comparisons = []
    for condition in CONDITIONS:
        rows = [r for r in frequencies if r['condition'] == condition]
        comparisons.append(dict(condition=condition, n_total=210, n_complete=sum(r['complete'] for r in rows),
                                historical_repeats=3, new_repeats=2,
                                recovered_repeat_errors=sum(r['recovered_repeat_error'] is True for r in rows),
                                damaged_stable_correct=sum(r['damaged_stable_correct'] is True for r in rows)))
    write_csv(dest/'baseline_comparison.csv', comparisons)
    return summaries


def execute(output=DEFAULT_OUTPUT, mode='dry-run', approved=False, condition=None, only_round=None):
    if mode not in ('dry-run', 'mock', 'live', 'analyze'):
        raise ValueError('Invalid mode')
    if mode == 'live' and not approved:
        raise ValueError('Live requires --approve-paid-api')
    if condition not in (None, *CONDITIONS) or only_round not in (None, *ROUNDS):
        raise ValueError('Use G1/G2/G3 and round 1/2 only')
    output = Path(output).resolve()
    allowed = DEFAULT_OUTPUT.resolve()
    if (output == ROOT or ROOT in output.parents) and output != allowed and allowed not in output.parents:
        raise ValueError('Use dedicated ablation output tree or a directory outside the repository')
    config, historical, plan, expected = prepare()
    if mode == 'analyze' and not (output/'plan.json').exists():
        raise ValueError('No existing ablation plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty new output directory')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.run.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text(encoding='utf-8-sig')) != plan:
                raise ValueError('Code/data/config/baseline changed; use a new version/output')
        else:
            save_json(output/'plan.json', plan)
            save_json(output/'system_prompts.json', PROMPTS)
        if mode == 'analyze':
            return dict(calls=0, analysis=aggregate(output, 'live', config, historical, expected))
        results = []
        try:
            for c, n in SCHEDULE:
                if (condition is not None and c != condition) or (only_round is not None and n != only_round):
                    continue
                print(f'{c} round {n}/2: 210 cases; {mode}', flush=True)
                results.append(run(child_config(config, c, n), output/mode/c/f'round-{n:02d}',
                                   mode, approved=approved, system_prompt=PROMPTS[c]))
        finally:
            aggregate(output, mode, config, historical, expected)
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
