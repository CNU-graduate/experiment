"""Frozen E6 + original guidance, all 86 supplied 2026 cases, three repeats."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from statistics import mean, stdev

from dotenv import load_dotenv
from . import e6_guided as guided
from .data import Dataset, FIELDS
from .evaluation import score, write_csv
from .instruction_repeats import read_csv, save_json
from .runner import run
from .prompt import parse_label

ROOT = guided.ROOT
VERSION = 'e6-guided-final-2026-v1'
DEFAULT_OUTPUT = ROOT/'results'/VERSION/'gpt-6-sol'


def prepare():
    baseline = json.loads((guided.BASELINES[0]/'manifest.json').read_text(encoding='utf-8-sig'))
    config = {k: baseline['config'][k] for k in guided.REQUEST_FIELDS}
    config.update(data_dir=str(ROOT/'data'), years=[2026], seeds=[42], conditions=['E6'],
                  models={'openai': guided.MODEL}, model_env={}, include_2026=True,
                  priority_annotations=str(ROOT/'priority_annotations.2025-final.json'))
    data = Dataset(ROOT/'data', include_2026=True)
    tests = data.tests[2026]
    with tempfile.TemporaryDirectory(prefix='e6-final-preflight-') as temp:
        folder = Path(temp)
        info = run(config, folder, 'dry-run', system_prompt=guided.GUIDED_SYSTEM)
        predictions = read_csv(folder/'predictions.csv')
        prompts = guided.prompts(folder)
        if info != dict(cases=86, calls=0) or len(predictions) != 86 or any(r['status'] != 'planned' for r in predictions):
            raise ValueError('Expected all 86 planned cases, no exclusions or API calls')
        sources = {r['id']: r for r in tests}
        example_sets = set()
        for ident, payload in prompts.items():
            if set(payload) != {'test', 'examples'} or payload['test'] != {k: sources[ident][k] for k in FIELDS}:
                raise ValueError('Target payload must contain exactly five input fields, no answer or comments')
            if len(payload['examples']) != 4 or any(set(e) != {*FIELDS, 'EFSA'} for e in payload['examples']):
                raise ValueError('Expected four labeled past-year examples only')
            example_sets.add(json.dumps(payload['examples'], sort_keys=True, ensure_ascii=False))
        examples = read_csv(folder/'examples.csv')
        if len(example_sets) != 1 or any(r['example_year'] != '2025' for r in examples):
            raise ValueError('All targets must use the same four 2025 examples')
        selected = [r for r in examples if r['id'] == predictions[0]['id']]
        expected = {r['id']: r for r in predictions}
    prior = {tuple(' '.join(r[f].split()) for f in FIELDS) for (y, _), rows in data.tables.items()
             if y < 2026 for r in rows}
    overlap = [r['id'] for r in tests if tuple(' '.join(r[f].split()) for f in FIELDS) in prior]
    plan = dict(version=VERSION, config=config, system_prompt=guided.GUIDED_SYSTEM,
                repeats=3, cases_per_repeat=86, total_cases=258, all_cases_included=True,
                data_files=data.files, annotations_sha256=guided.sha(ROOT/'priority_annotations.2025-final.json'),
                implementation={p.name: guided.sha(p) for p in sorted((ROOT/'residue_experiment').glob('*.py'))},
                selected_examples=selected, prior_input_overlap=overlap,
                leakage_check='Target has exactly five fields; no target EFSA, comments, URL or answerkey text. '
                'Only four labeled 2025 examples are sent. No tools or browsing supplied to model.',
                note='2025 example annotations newly frozen from 2025 inputs; original guidance unchanged. '
                'All 86 cases retained including prior-input overlaps. No prompt tuning after final evaluation.')
    return config, plan, expected


def aggregate(output, mode, expected, config, *, system_prompt=guided.GUIDED_SYSTEM):
    metrics, errors = [], {i: dict(id=i, actual=r['actual'], valid_runs=0, wrong_count=0) for i,r in expected.items()}
    for n in (1, 2, 3):
        folder = output/mode/f'round-{n:02d}'
        rows = read_csv(folder/'predictions.csv') if (folder/'predictions.csv').exists() else []
        if rows:
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
            if manifest['config'] != config or manifest['system_prompt'] != system_prompt or manifest['mode'] != mode:
                raise ValueError('Mixed final-test manifest')
            if len({r['id'] for r in rows}) != len(rows):
                raise ValueError('Duplicate final-test result')
        calls = read_csv(folder/'api_calls.csv') if (folder/'api_calls.csv').exists() else []
        successful = {json.loads(r['case_key'])[3]: r for r in calls if r['status']=='success'}
        valid = []
        for r in rows:
            t = expected.get(r['id'])
            if t is None or any(r[k] != t[k] for k in ('actual','year','condition','seed','provider','model','prompt_sha256')):
                raise ValueError('Mixed final-test input/result')
            if r['status'] == 'success':
                call = successful.get(r['id'])
                if call is None or parse_label(call['response']) != r['prediction']:
                    raise ValueError('Prediction differs from saved API response')
                valid.append(r)
                errors[r['id']]['valid_runs'] += 1
                errors[r['id']]['wrong_count'] += r['prediction'] != r['actual']
        values = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {}
        metrics.append(dict(round=n, n_total=86, n_evaluated=len(valid), complete=len(valid)==86, **values))
    complete = [r for r in metrics if r['complete']]
    summary = dict(repeats_complete=len(complete), repeats_planned=3, cases_per_repeat=86)
    for k in ('accuracy','macro_f1'):
        vals = [r[k] for r in complete]
        summary[k+'_mean'] = mean(vals) if vals else None
        summary[k+'_std'] = stdev(vals) if len(vals)>1 else (0 if vals else None)
    dest=output/mode/'analysis'
    dest.mkdir(parents=True,exist_ok=True)
    write_csv(dest/'round_metrics.csv',metrics)
    write_csv(dest/'error_frequency.csv',list(errors.values()))
    save_json(dest/'summary.json',summary)
    return summary


def execute(output=DEFAULT_OUTPUT, mode='dry-run', approved=False):
    if mode not in ('dry-run','mock','live','analyze'):
        raise ValueError('Invalid mode')
    if mode=='live' and not approved:
        raise ValueError('Live requires --approve-paid-api')
    output=Path(output).resolve()
    if (output==ROOT or ROOT in output.parents) and output!=DEFAULT_OUTPUT.resolve() and DEFAULT_OUTPUT.resolve() not in output.parents:
        raise ValueError('Use dedicated final-test output or outside repository')
    config,plan,expected=prepare()
    if mode=='live' and not os.environ.get('OPENROUTER_API_KEY'):
        raise ValueError('OPENROUTER_API_KEY is not configured; preflight passed, no paid calls made')
    if mode=='analyze' and not (output/'plan.json').exists():
        raise ValueError('No saved final-test plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    lock=output/'.run.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text(encoding='utf-8-sig'))!=plan:
                raise ValueError('Frozen plan changed; do not mix final-test results')
        else:
            save_json(output/'plan.json',plan)
        if mode=='analyze':
            return dict(calls=0,summary=aggregate(output,'live',expected,config))
        infos=[]
        try:
            for n in (1,2,3):
                print(f'E6 + guidance 2026 round {n}/3: 86 cases; {mode}',flush=True)
                infos.append(run(config,output/mode/f'round-{n:02d}',mode,approved=approved,
                                 system_prompt=guided.GUIDED_SYSTEM))
        finally:
            aggregate(output,mode,expected,config)
        return dict(cases=sum(i['cases'] for i in infos),calls=sum(i['calls'] for i in infos),output=str(output))
    finally:
        lock.unlink()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['dry-run','mock','live','analyze'],default='dry-run')
    p.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--approve-paid-api',action='store_true')
    a=p.parse_args()
    try:
        if a.mode=='live':load_dotenv(ROOT/'.env',override=False)
        print(json.dumps(execute(a.output,a.mode,a.approve_paid_api),ensure_ascii=False))
    except (ValueError,KeyError,ImportError,OSError) as exc:
        p.exit(2,f'{type(exc).__name__}: {exc}\n')

if __name__=='__main__':main()
