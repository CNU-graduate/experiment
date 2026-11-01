"""Freeze a leakage-controlled grouped threshold pilot, without API calls."""
import argparse
import csv
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ('substance','purpose','commodity','JMPR','EU')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True)


def signature(row):
    return tuple(' '.join(unicodedata.normalize('NFKC',row[f]).split()).casefold() for f in FIELDS)


def group(row):
    text=unicodedata.normalize('NFKC',row['substance']).casefold()
    return ' '.join(re.sub('[‐‑‒–—−]','-',text).split())


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo-root',type=Path,default=HERE.parent)
    parser.add_argument('--year',type=int,choices=[2023,2024,2025],default=2023)
    parser.add_argument('--development-n',type=int,default=100)
    parser.add_argument('--validation-n',type=int,default=100)
    args=parser.parse_args()
    if min(args.development_n,args.validation_n)<2:parser.error('Split sizes must be at least 2')
    root=args.repo_root.resolve()
    data=root/'data'
    import sys
    sys.path.insert(0,str(root))
    from residue_experiment.prompt import SYSTEM
    ending='Return exactly Yes or No,\nwithout explanations, punctuation, or markdown.'
    assert SYSTEM.count(ending)==1
    score_system=SYSTEM.replace(ending,'''Instead of a categorical answer, report the strength of support for comparability
as an integer from 0 to 100. Use 0 for strongest support for No, 100 for strongest
support for Yes, and 50 as the midpoint. This is an assessment score, not a
calibrated probability. Return exactly one integer, without explanation or formatting.''')
    used_files={}
    def load(path):
        used_files[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)
    # Unlabelled evaluation inputs are used only to exclude exact historical duplicates.
    all_tests={year:load(data/f'ESFA_{year}70.csv') for year in [2023,2024,2025]}
    eval_signatures={signature(r) for rows in all_tests.values() for r in rows}
    historical=[]
    for path in sorted(data.glob('ESFA_*.csv')):
        match=re.fullmatch(r'ESFA_(\d{4})(70answerkey|_remain)\.csv',path.name)
        if match and int(match[1])<2023:
            historical.extend(load(path))
    unique={};duplicates=[];overlap=[]
    for row in historical:
        assert row['EFSA'] in ('Yes','No')
        key=signature(row)
        if key in eval_signatures:
            overlap.append(row['id']);continue
        if key in unique:
            if unique[key]['EFSA']!=row['EFSA']:
                raise ValueError(f"Conflicting historical labels: {unique[key]['id']} / {row['id']}")
            duplicates.append(row['id']);continue
        unique[key]=row
    historical=list(unique.values())
    groups=sorted({group(r) for r in historical})
    random.Random(42).shuffle(groups)
    development_groups=set(groups[:int(len(groups)*0.70)])
    development=[r for r in historical if group(r) in development_groups]
    validation=[r for r in historical if group(r) not in development_groups]
    random.Random(43).shuffle(development)
    random.Random(44).shuffle(validation)
    if len(development)<args.development_n or len(validation)<args.validation_n:
        raise ValueError(f'Not enough cases: development={len(development)}, validation={len(validation)}')
    development=development[:args.development_n];validation=validation[:args.validation_n]
    assert {group(r) for r in development}.isdisjoint(group(r) for r in validation)
    assert all(set(r['EFSA'] for r in rows)=={'Yes','No'} for rows in [development,validation])
    requests=[];local_labels={};splits=[]
    def request(row,phase,kind):
        key=f"{phase}:{kind}:{row['id']}"
        prompt=canonical({'examples':[],'test':{f:row[f] for f in FIELDS}})
        requests.append(dict(key=key,phase=phase,kind=kind,case_id=row['id'],
            body=dict(model='openai/gpt-6-sol',messages=[dict(role='system',content=score_system if kind=='score' else SYSTEM),dict(role='user',content=prompt)],max_tokens=1000)))
    for phase,rows in [('development',development),('validation',validation)]:
        for row in rows:
            request(row,phase,'score')
            local_labels[f"{phase}:{row['id']}"]=row['EFSA']
            splits.append(dict(phase=phase,id=row['id'],year=row['year'],substance=row['substance'],group=group(row),actual=row['EFSA']))
    tests=all_tests[args.year]
    assert len(tests)==70 and len({r['id'] for r in tests})==70
    for row in tests:
        request(row,'evaluation','direct')
        request(row,'evaluation','score')
    # Test labels remain strictly local, and are not used for splitting or fitting.
    test_answers={r['id']:r for r in load(data/f'ESFA_{args.year}70answerkey.csv')}
    for row in tests:
        answer=test_answers[row['id']]
        assert signature(row)==signature(answer)
        local_labels[f"evaluation:{row['id']}"]=answer['EFSA']
    plan=dict(version='threshold-pilot-v1',evaluation_year=args.year,seed=42,
        model='openai/gpt-6-sol',api_backend='openrouter',timeout_seconds=120,max_output_tokens=1000,
        max_attempts=1,thresholds=list(range(102)),default_threshold=50,
        selection_rule='development macro-F1, then accuracy, then distance to 50, then smaller threshold',
        validation_gate='selected threshold must improve macro-F1 or accuracy, with neither metric below threshold 50',
        dev_n=len(development),validation_n=len(validation),evaluation_n=70,
        max_paid_calls=len(requests),source_files_sha256=used_files,
        removed_exact_duplicates=duplicates,removed_historical_test_overlaps=overlap,
        split_counts={p:dict(Counter(r['EFSA'] for r in rows)) for p,rows in [('development',development),('validation',validation)]},
        grouping='Normalized substance names; this is not chemical-alias resolution',
        evaluation_group_overlap_with_history=len({group(r) for r in tests}&{group(r) for r in historical}),
        limitations=['Retrospective evaluation: 2023-2025 were inspected in earlier work','Development and validation are substance-disjoint; evaluation may share substances across years','Model scores are not calibrated probabilities','One pilot run; paired comparisons are exploratory'])
    serial=''.join(canonical(r)+'\n' for r in requests)
    plan['requests_sha256']=hashlib.sha256(serial.encode()).hexdigest()
    for name,obj in [('plan.json',plan),('labels_LOCAL_ONLY.json',local_labels),('splits_LOCAL_ONLY.json',splits)]:
        path=HERE/name
        content=json.dumps(obj,ensure_ascii=False,indent=2)
        if path.exists() and path.read_text(encoding='utf-8')!=content:
            raise ValueError(f'Existing frozen plan differs: {path}. Use a new experiment directory.')
    (HERE/'requests.jsonl').write_bytes(serial.encode('utf-8'))
    for name,obj in [('plan.json',plan),('labels_LOCAL_ONLY.json',local_labels),('splits_LOCAL_ONLY.json',splits)]:
        (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:plan[k] for k in ['evaluation_year','dev_n','validation_n','evaluation_n','max_paid_calls','split_counts','evaluation_group_overlap_with_history']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
