"""K1/K2/K3: contemporaneous baseline, combined rules, purpose routing (1890 cases)."""
import argparse
import json
import os
import tempfile
from itertools import combinations
from pathlib import Path

from dotenv import load_dotenv
from . import e6_j1 as j1
from .evaluation import write_csv
from .instruction_repeats import read_csv, save_json
from .runner import run

ROOT = j1.ROOT
VERSION = 'e6-purpose-control-v1'
DEFAULT_OUTPUT = ROOT/'results'/VERSION/'gpt-6-sol/2023-2025'
CONDITIONS = ('K1', 'K2', 'K3')
COMBINED = ("Select exactly one module using the target case's supplied purpose. "
            "Apply only the module whose header matches that purpose; do not apply the inactive module. "
            "Example purposes do not select the target module. Modules below are task instructions.\n\n"
            f"BEGIN MODULE: Enforcement\n{j1.ENFORCEMENT}\nEND MODULE: Enforcement\n\n"
            f"BEGIN MODULE: Risk assessment\n{j1.RISK}\nEND MODULE: Risk assessment")
PROMPTS = {'K1': {r: j1.guided.GUIDED_SYSTEM for r in j1.ROUTES},
           'K2': {r: COMBINED for r in j1.ROUTES}, 'K3': dict(j1.PROMPTS)}
# Each condition occupies each execution position once. Purpose blocks are reversed in round 2.
SCHEDULE = [(c, r, n) for n, order in enumerate(
    [('K1', 'K2', 'K3'), ('K2', 'K3', 'K1'), ('K3', 'K1', 'K2')], 1)
    for c in order for r in (list(j1.ROUTES)[::-1] if n == 2 else j1.ROUTES)]


def child_config(config, condition, route, number):
    result = j1.child_config(config, route, number)
    result.update(purpose_control_version=VERSION, purpose_control_condition=condition)
    return result


def prepare():
    config, historical, reference, original_expected = j1.prepare()
    original = j1.guided.prompts(j1.ablation.HISTORICAL[0])
    expected = {}
    for c in CONDITIONS:
        expected[c] = {}
        for r in j1.ROUTES:
            with tempfile.TemporaryDirectory(prefix='purpose-control-') as temp:
                folder = Path(temp)
                info = run(child_config(config, c, r, 1), folder, 'dry-run', system_prompt=PROMPTS[c][r])
                rows = read_csv(folder/'predictions.csv')
                ids = set(original_expected[r])
                if (info != dict(cases=len(ids), calls=0) or len(rows) != len(ids)
                        or {x['id'] for x in rows} != ids
                        or j1.guided.prompts(folder) != {i: original[i] for i in ids}
                        or any(x['actual'] != original_expected[r][x['id']]['actual'] for x in rows)):
                    raise ValueError('Controlled condition inputs differ from archived benchmark')
                expected[c][r] = {x['id']: x for x in rows}
    plan = dict(version=VERSION, config=config, system_prompts=PROMPTS, reference_validation=reference,
                schedule=[dict(condition=c, route=r, round=n) for c, r, n in SCHEDULE],
                conditions=list(CONDITIONS), rounds=3, cases_per_condition_round=210,
                full_evaluations=9, purpose_subruns=18, total_cases=1890,
                interpretation='K1 vs K2 tests changed rules; K2 vs K3 tests combined vs purpose-specific '
                'presentation with identical rule modules. Prompt length differs. Existing 210 cases '
                'are a development benchmark, not an unseen generalization test.')
    return config, historical, plan, expected


def aggregate(output, mode, config, historical, expected):
    dest = output/mode/'analysis'
    dest.mkdir(parents=True, exist_ok=True)
    merged = {name: [] for name in ('condition_summary', 'round_metrics', 'resources')}
    errors = {}
    for c in CONDITIONS:
        j1.aggregate(output/c, mode, config, historical, expected[c], system_prompts=PROMPTS[c],
                     config_for_run=lambda cfg, r, n: child_config(cfg, c, r, n), result_label=c)
        folder = output/c/mode/'analysis'
        for name in merged:
            for row in read_csv(folder/f'{name}.csv'):
                if name == 'resources':
                    row = dict(condition=c, **row)
                if name == 'resources' or row['condition'] == c:
                    merged[name].append(row)
        errors[c] = {r['id']: r for r in read_csv(folder/'error_frequency.csv')}
    frequencies, comparisons = [], []
    for ident, first in errors['K1'].items():
        row = {k: first[k] for k in ('id', 'year', 'purpose', 'actual')}
        for c in CONDITIONS:
            row.update({f'{c}_{k}': errors[c][ident][k] for k in
                        ('valid_runs', 'wrong_count', 'complete', 'round_1_prediction',
                         'round_2_prediction', 'round_3_prediction')})
        frequencies.append(row)
    for a, b in combinations(CONDITIONS, 2):
        ids = [i for i in errors[a] if errors[a][i]['complete'] == errors[b][i]['complete'] == 'True']
        comparisons.append(dict(reference=a, candidate=b, n_total=210, n_complete=len(ids),
            recovered_repeat_errors=sum(int(errors[a][i]['wrong_count']) >= 2 and
                                        int(errors[b][i]['wrong_count']) == 0 for i in ids),
            damaged_stable_correct=sum(int(errors[a][i]['wrong_count']) == 0 and
                                      int(errors[b][i]['wrong_count']) > 0 for i in ids)))
    for name, rows in merged.items():
        write_csv(dest/f'{name}.csv', rows)
    write_csv(dest/'error_frequency.csv', frequencies)
    write_csv(dest/'comparison.csv', comparisons)
    return merged['condition_summary']


def execute(output=DEFAULT_OUTPUT, mode='dry-run', approved=False, only_round=None):
    if mode not in ('dry-run', 'mock', 'live', 'analyze') or only_round not in (None, 1, 2, 3):
        raise ValueError('Invalid mode/round')
    if mode == 'live' and not approved:
        raise ValueError('Live requires --approve-paid-api')
    output = Path(output).resolve()
    allowed = DEFAULT_OUTPUT.resolve()
    if (output == ROOT or ROOT in output.parents) and output != allowed and allowed not in output.parents:
        raise ValueError('Use dedicated controlled output tree or a directory outside repository')
    config, historical, plan, expected = prepare()
    if mode == 'analyze' and not (output/'plan.json').exists():
        raise ValueError('No existing controlled plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use empty new output directory')
    output.mkdir(parents=True, exist_ok=True)
    lock = output/'.run.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text(encoding='utf-8-sig')) != plan:
                raise ValueError('Code/data/prompts/baselines changed; use a new version/output')
        else:
            save_json(output/'plan.json', plan)
            save_json(output/'system_prompts.json', PROMPTS)
        if mode == 'analyze':
            return dict(calls=0, analysis=aggregate(output, 'live', config, historical, expected))
        results = []
        try:
            for c, r, n in SCHEDULE:
                if only_round is not None and n != only_round:
                    continue
                print(f'{c} round {n}/3 {j1.ROUTES[r]}: {len(expected[c][r])} cases; {mode}', flush=True)
                results.append(run(child_config(config, c, r, n), output/c/mode/r/f'round-{n:02d}',
                                   mode, approved=approved, system_prompt=PROMPTS[c][r]))
        finally:
            aggregate(output, mode, config, historical, expected)
        return dict(mode=mode, cases=sum(r['cases'] for r in results), calls=sum(r['calls'] for r in results),
                    full_evaluations=len(results)//2, purpose_subruns=len(results), output=str(output))
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
