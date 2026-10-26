"""Isolated model-specific E7 entry point; original Claude modules stay unchanged.

Run from repository root: python -m scripts.run_model_specific_e7 --provider openai
"""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv
from residue_experiment import runner
from residue_experiment.cli import validate_config
from residue_experiment.data import Dataset, inputs
from residue_experiment.prompt import build_prompt
from residue_experiment.selection import Selector

ROOT = Path(__file__).resolve().parents[1]


def analyze(name):
    base = ROOT / 'results' / 'zero-shot-repeats' / name / '2023-2025'
    sources = ([ROOT / 'results/baseline' / name / '2023-2025'] +
               [base / 'live' / f'round-{n:02d}' for n in (2, 3)] if name == 'gpt-6-sol'
               else [base / 'live' / f'round-{n:02d}' for n in (1, 2, 3)])
    rounds, evidence = [], []
    for source in sources:
        import csv
        path = source / 'predictions.csv'
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = [r for r in csv.DictReader(f) if r['condition'] == 'E0']
        if (len(rows) != 210 or len({r['id'] for r in rows}) != 210 or
                any(r['status'] != 'success' or r['prediction'] not in ('Yes', 'No') for r in rows)):
            raise ValueError(f'Incomplete zero-shot source: {path}')
        rounds.append({r['id']: r for r in rows})
        evidence.append(dict(path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    first = rounds[0]
    if any(set(r) != set(first) for r in rounds):
        raise ValueError('Zero-shot rounds have different IDs')
    errors = []
    for ident, r in sorted(first.items()):
        if any(a[ident]['actual'] != r['actual'] for a in rounds):
            raise ValueError('Zero-shot labels differ')
        predictions = [a[ident]['prediction'] for a in rounds]
        wrong = sum(p != r['actual'] for p in predictions)
        if wrong:
            errors.append(dict(id=ident, actual=r['actual'], wrong_count=wrong, predictions=predictions))
    return dict(sources=evidence, core_count=sum(r['wrong_count'] == 3 for r in errors),
                core_actual_labels=dict(Counter(r['actual'] for r in errors if r['wrong_count'] == 3)),
                errors=errors)


def execute(provider, mode='dry-run', approved=False, output=None):
    if mode not in ('dry-run', 'live') or (mode == 'live' and not approved):
        raise ValueError('Live execution requires --approve-paid-api')
    specification = json.loads((ROOT / 'scripts/model_specific_e7.json').read_text(encoding='utf-8'))
    spec = specification['models'][provider]
    data = Dataset(ROOT / 'data')
    audit, frozen = analyze(spec['name']), {}
    export = []
    for year in (2023, 2024, 2025):
        rows = []
        entries = spec['years'][str(year)]
        if [e[0] for e in entries] != specification['order']:
            raise ValueError('Unexpected role order')
        for rank, (role, ident, label, reason) in enumerate(entries, 1):
            matches = [r for r in data.pools[year - 1] if r['id'] == ident]
            if len(matches) != 1 or matches[0]['EFSA'] != label or int(matches[0]['year']) != year - 1:
                raise ValueError(f'Candidate mismatch: {ident}')
            row = matches[0]
            rows.append(dict(row, role=role, selection_reason=reason))
            export.append(dict(test_year=year, rank=rank, role=role, id=ident,
                               **inputs(row), EFSA=label, reason=reason))
        if len({r['id'] for r in rows}) != 4 or Counter(r['EFSA'] for r in rows) != {'Yes': 2, 'No': 2}:
            raise ValueError('Expected four unique balanced examples')
        frozen[year] = rows

    class ModelSpecificSelector(Selector):
        def choose(self, condition, year, seed, test):
            if condition != 'E7':
                return super().choose(condition, year, seed, test)
            self.audit[f'{year}:E7'] = dict(version=specification['version'], provider=provider,
                                          selected=[dict(id=r['id'], role=r['role'], label=r['EFSA'],
                                                         reason=r['selection_reason']) for r in frozen[year]])
            return [dict(r) for r in frozen[year]]

    config = json.loads((ROOT / 'config.openrouter.e7.json').read_text(encoding='utf-8'))
    config.update(data_dir=str(ROOT / 'data'), models={provider: spec['model']},
                  model_specific_selection=export, zero_shot_evidence=audit['sources'],
                  model_specific_launcher_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    validate_config(config)
    output = Path(output) if output else ROOT / 'results/error-informed-personalized' / spec['name'] / '2023-2025'
    output.mkdir(parents=True, exist_ok=True)
    allowed = {'plan.json', 'zero_shot_analysis.json', 'selected_examples.json', 'dry-run', 'live'}
    if any(p.name not in allowed for p in output.iterdir()):
        raise ValueError('Use a separate personalized E7 output')
    plan = dict(config=config, selection_version=specification['version'], total_cases=630,
                order=specification['order'], rounds=3, mode_independent=True)
    path = output / 'plan.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8')) != plan:
        raise ValueError('Existing plan differs; use new output')
    for name, content in [('plan.json', plan), ('zero_shot_analysis.json', audit), ('selected_examples.json', export)]:
        (output / name).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    # Process-local adapter avoids changes to shared source/fingerprints or Claude checkpoints.
    original = runner.Selector
    runner.Selector = ModelSpecificSelector
    summaries = []
    try:
        for number in (1, 2, 3):
            folder = output / mode / f'round-{number:02d}'
            info = runner.run(config, folder, mode, approved=approved)
            with closing(sqlite3.connect((folder / 'checkpoint.sqlite').resolve().as_uri() + '?mode=ro', uri=True)) as db:
                rows = [json.loads(s) for s, in db.execute('SELECT payload FROM cases')]
            status = 'planned' if mode == 'dry-run' else 'success'
            if len(rows) != 210 or len({r['id'] for r in rows}) != 210 or any(r['status'] != status for r in rows):
                raise ValueError('Incomplete E7 round')
            for row in rows:
                test = next(t for t in data.tests[row['year']] if t['id'] == row['id'])
                if row['prompt'] != build_prompt(test, frozen[row['year']]):
                    raise ValueError('Unexpected model-specific prompt')
            if mode == 'dry-run' and info['calls'] != 0:
                raise ValueError('Unexpected calls')
            summaries.append(info)
    finally:
        runner.Selector = original
    return dict(provider=provider, core_errors=audit['core_count'], total_cases=sum(s['cases'] for s in summaries),
                calls=sum(s['calls'] for s in summaries), output=str(output))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider', choices=['openai', 'gemini'], required=True)
    p.add_argument('--mode', choices=['dry-run', 'live'], default='dry-run')
    p.add_argument('--approve-paid-api', action='store_true')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.mode == 'live' and not args.approve_paid_api:
        p.error('Live execution requires --approve-paid-api')
    load_dotenv(ROOT / '.env', override=False)
    print(json.dumps(execute(args.provider, args.mode, args.approve_paid_api, args.output)))


if __name__ == '__main__':
    main()
