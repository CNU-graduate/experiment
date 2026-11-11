"""Compare original E6 and independent P3 on all 86 cases from 2026, three repeats."""
import argparse
import copy
import json
import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from . import e6_final_2026 as final
from .prompt import SYSTEM
from .prompt_methods import P3
from .instruction_repeats import read_csv, save_json
from .evaluation import write_csv
from .runner import run

ROOT=final.ROOT
VERSION='e6-p3-final-2026-v1'
DEFAULT_OUTPUT=ROOT/'results'/VERSION/'gpt-6-sol'
PROMPTS={'E6':SYSTEM,'P3':P3}
SCHEDULE=[('E6',1),('P3',1),('P3',2),('E6',2),('E6',3),('P3',3)]


def prepare():
    base,reference,_=final.prepare()
    configs,expected={},{}
    for c in PROMPTS:
        configs[c]=copy.deepcopy(base)
        configs[c]['conditions']=[c]
        if c=='P3':
            configs[c].pop('priority_annotations',None)
        with tempfile.TemporaryDirectory(prefix='e6-p3-final-check-') as temp:
            folder=Path(temp)
            info=run(configs[c],folder,'dry-run',system_prompt=PROMPTS[c])
            rows=read_csv(folder/'predictions.csv')
            if info!=dict(cases=86,calls=0) or len(rows)!=86 or any(r['status']!='planned' for r in rows):
                raise ValueError('Both conditions require all 86 planned cases')
            for line in (folder/'prompts.jsonl').read_text(encoding='utf-8-sig').splitlines():
                payload=json.loads(json.loads(line)['prompt'])
                if set(payload)!= {'test','examples'} or set(payload['test'])!=set(final.FIELDS):
                    raise ValueError('Target answer/comment leakage')
                if len(payload['examples'])!=(4 if c=='E6' else 0):
                    raise ValueError('E6 needs four examples; P3 must be zero-shot')
            expected[c]={r['id']:r for r in rows}
            if c=='E6':
                examples=read_csv(folder/'examples.csv')
                selected=[r for r in examples if r['id']==rows[0]['id']]
                if selected!=reference['selected_examples']:
                    raise ValueError('E6 examples must match guided final evaluation')
    if {i:r['actual'] for i,r in expected['E6'].items()}!={i:r['actual'] for i,r in expected['P3'].items()}:
        raise ValueError('Condition test sets differ')
    plan=dict(version=VERSION,configs=configs,system_prompts=PROMPTS,reference=reference,
              schedule=[dict(condition=c,round=n) for c,n in SCHEDULE],total_cases=516,repeats=3,
              note='Follow-up comparison after inspecting guided results; original prompts unchanged. '
              'E6 uses identical four 2025 examples, P3 is zero-shot. All 86 cases including two prior overlaps.')
    return configs,plan,expected


def aggregate(output,mode,configs,expected):
    summaries=[]
    errors={}
    for c in PROMPTS:
        summary=final.aggregate(output/c,mode,expected[c],configs[c],system_prompt=PROMPTS[c])
        summaries.append(dict(condition=c,**summary))
        errors[c]={r['id']:r for r in read_csv(output/c/mode/'analysis/error_frequency.csv')}
    dest=output/mode/'analysis'
    dest.mkdir(parents=True,exist_ok=True)
    write_csv(dest/'condition_summary.csv',summaries)
    write_csv(dest/'error_comparison.csv',[
        dict(id=i,actual=errors['E6'][i]['actual'],
             **{f'{c}_{k}':errors[c][i][k] for c in PROMPTS for k in ('valid_runs','wrong_count')})
        for i in expected['E6']])
    return summaries


def execute(output=DEFAULT_OUTPUT,mode='dry-run',approved=False):
    if mode not in ('dry-run','mock','live','analyze'):raise ValueError('Invalid mode')
    if mode=='live' and not approved:raise ValueError('Live requires --approve-paid-api')
    output=Path(output).resolve()
    allowed=DEFAULT_OUTPUT.resolve()
    if (output==ROOT or ROOT in output.parents) and output!=allowed and allowed not in output.parents:
        raise ValueError('Use dedicated E6 P3 output or outside repository')
    configs,plan,expected=prepare()
    if mode=='live' and not os.environ.get('OPENROUTER_API_KEY'):
        raise ValueError('OPENROUTER_API_KEY is not configured; no paid calls made')
    if mode=='analyze' and not (output/'plan.json').exists():raise ValueError('No saved plan')
    if not (output/'plan.json').exists() and output.exists() and any(output.iterdir()):
        raise ValueError('Use empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    lock=output/'.run.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        if (output/'plan.json').exists():
            if json.loads((output/'plan.json').read_text(encoding='utf-8-sig'))!=plan:
                raise ValueError('Frozen plan changed; use new output')
        else:save_json(output/'plan.json',plan)
        if mode=='analyze':return dict(calls=0,summary=aggregate(output,'live',configs,expected))
        results=[]
        try:
            for c,n in SCHEDULE:
                print(f'{c} 2026 round {n}/3: 86 cases; {mode}',flush=True)
                results.append(run(configs[c],output/c/mode/f'round-{n:02d}',mode,approved=approved,
                                   system_prompt=PROMPTS[c]))
        finally:aggregate(output,mode,configs,expected)
        return dict(cases=sum(r['cases'] for r in results),calls=sum(r['calls'] for r in results),runs=len(results),output=str(output))
    finally:lock.unlink()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['dry-run','mock','live','analyze'],default='dry-run')
    p.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--approve-paid-api',action='store_true')
    a=p.parse_args()
    try:
        if a.mode=='live':load_dotenv(ROOT/'.env',override=False)
        print(json.dumps(execute(a.output,a.mode,a.approve_paid_api),ensure_ascii=False))
    except (ValueError,KeyError,ImportError,OSError) as exc:p.exit(2,f'{type(exc).__name__}: {exc}\n')

if __name__=='__main__':main()
