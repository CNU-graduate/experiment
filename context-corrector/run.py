"""Offline contextual correction using frozen GPT scores; no API client or network."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
CANDIDATES=(0.01,0.1,1.0,10.0)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(labels,predictions):
    tn=sum(a==b=='No' for a,b in zip(labels,predictions))
    tp=sum(a==b=='Yes' for a,b in zip(labels,predictions))
    fp=sum(a=='No' and b=='Yes' for a,b in zip(labels,predictions))
    fn=sum(a=='Yes' and b=='No' for a,b in zip(labels,predictions))
    div=lambda a,b:a/b if b else 0.0
    return dict(n=len(labels),correct=tn+tp,accuracy=div(tn+tp,len(labels)),
        macro_f1=(div(2*tp,2*tp+fp+fn)+div(2*tn,2*tn+fp+fn))/2,
        precision=div(tp,tp+fp),recall=div(tp,tp+fn),tn=tn,fp=fp,fn=fn,tp=tp)


def text_input(records):
    # Deliberately exclude IDs, grouping names, outcomes and EFSA comments.
    return [f"PURPOSE {r['input']['purpose']} COMMODITY {r['input']['commodity']} JMPR {r['input']['JMPR']} EU {r['input']['EU']}" for r in records]


def numerical_input(records):
    features=[]
    for r in records:
        j=r['input']['JMPR'].casefold();e=r['input']['EU'].casefold()
        marker=lambda s,w:float(w in s)
        # Fixed before validation: an anchored GPT score and small lexical indicators.
        values=[8*r['score']/100, float(r['score']>=50)]
        for word in ['conjugat','isomer','expressed as','considered separately','not required','not proposed','provisional']:
            values.extend([marker(j,word),marker(e,word),marker(e,word)-marker(j,word)])
        values.extend([min(len(j),2000)/2000,min(len(e),2000)/2000,
            min(len(re.findall(r'peer review|mrl review|reg\.',e)),5)/5])
        features.append(values)
    return np.asarray(features,dtype=float)


def model(c):
    features=FeatureUnion([
        ('word',Pipeline([('extract',FunctionTransformer(text_input,validate=False)),
            ('tfidf',TfidfVectorizer(ngram_range=(1,2),min_df=1,max_features=5000,sublinear_tf=True))])),
        ('character',Pipeline([('extract',FunctionTransformer(text_input,validate=False)),
            ('tfidf',TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=2,max_features=15000,sublinear_tf=True))])),
        ('numeric',FunctionTransformer(numerical_input,validate=False))])
    return Pipeline([('features',features),('classifier',LogisticRegression(C=c,solver='liblinear',max_iter=2000,random_state=42))])


def train_select(development):
    labels=np.asarray([r['actual'] for r in development])
    groups=np.asarray([r['group'] for r in development])
    if len(set(groups))<5:raise ValueError('At least five substance groups required')
    folds=list(StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=42).split(np.zeros(len(development)),labels,groups))
    for train,test in folds:
        assert set(groups[train]).isdisjoint(groups[test])
        if len(set(labels[train]))<2:raise ValueError('A training fold lacks both classes')
    candidates=[]
    for c in CANDIDATES:
        predictions=np.empty(len(development),dtype=object)
        for train,test in folds:
            estimator=model(c)
            estimator.fit([development[i] for i in train],labels[train])
            predictions[test]=estimator.predict([development[i] for i in test])
        candidates.append(dict(C=c,**metrics(labels,predictions)))
    selected=max(candidates,key=lambda r:(r['macro_f1'],r['accuracy'],-r['C']))
    estimator=model(selected['C'])
    estimator.fit(development,labels)
    return estimator,selected,candidates,folds


def load_data(directory):
    plan=json.loads((directory/'plan.json').read_text(encoding='utf-8'))
    manifest_path=directory/'runs/live/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['mode']!='live':raise ValueError('Real saved GPT responses are required; mock data rejected')
    if digest(directory/'plan.json')!=manifest['identity']['plan_sha256']:raise ValueError('Plan changed after GPT run')
    if digest(directory/'labels_LOCAL_ONLY.json')!=manifest['identity']['labels_sha256']:raise ValueError('Labels changed after GPT run')
    if digest(directory/'requests.jsonl')!=plan['requests_sha256']:raise ValueError('Requests changed')
    responses=json.loads((directory/'runs/live/responses.json').read_text(encoding='utf-8'))
    labels=json.loads((directory/'labels_LOCAL_ONLY.json').read_text(encoding='utf-8'))
    splits={(r['phase'],r['id']):r for r in json.loads((directory/'splits_LOCAL_ONLY.json').read_text(encoding='utf-8'))}
    records=[]
    for line in (directory/'requests.jsonl').read_text(encoding='utf-8').splitlines():
        request=json.loads(line)
        if request['phase'] not in ('development','validation'):continue
        response=responses.get(request['key'])
        if not response or response['status']!='success':raise ValueError(f"Incomplete response: {request['key']}")
        score=response['value']
        if type(score) is not int or not 0<=score<=100:raise ValueError('Invalid saved score')
        split=splits[request['phase'],request['case_id']]
        records.append(dict(id=request['case_id'],phase=request['phase'],group=split['group'],
            actual=labels[f"{request['phase']}:{request['case_id']}"],score=score,
            input=json.loads(request['body']['messages'][1]['content'])['test']))
    development=[r for r in records if r['phase']=='development']
    validation=[r for r in records if r['phase']=='validation']
    if len(development)!=100 or len(validation)!=100:raise ValueError('Expected frozen 100/100 pilot')
    assert {r['group'] for r in development}.isdisjoint(r['group'] for r in validation)
    return development,validation


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=ROOT/'threshold-pilot')
    parser.add_argument('--output',type=Path,default=HERE/'runs/offline-v1')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    directory=args.input.resolve();output=args.output.resolve()
    development,validation=load_data(directory)
    if args.check_only:
        print(json.dumps(dict(development=len(development),validation=len(validation),substance_overlap=0,api_calls=0)));return
    # Hyperparameter selection receives development records only. TF-IDF is fitted
    # inside each training fold, never on the held-out folds or validation set.
    estimator,selected,candidates,folds=train_select(development)
    identity=dict(version='context-corrector-v1',sklearn=sklearn.__version__,implementation_sha256=digest(Path(__file__).resolve()),
        scores_sha256=digest(directory/'runs/live/responses.json'),plan_sha256=digest(directory/'plan.json'),
        labels_sha256=digest(directory/'labels_LOCAL_ONLY.json'),candidates=CANDIDATES,
        selection='pooled development group-OOF macro-F1; accuracy; smaller C',selected=selected,
        folds=[dict(train_ids=[development[i]['id'] for i in train],heldout_ids=[development[i]['id'] for i in test]) for train,test in folds])
    output.mkdir(parents=True,exist_ok=True)
    frozen=output/'frozen_model_design.json'
    if frozen.exists() and json.loads(frozen.read_text(encoding='utf-8'))!=json.loads(json.dumps(identity)):
        raise ValueError('Different frozen design; use another output directory')
    frozen.write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding='utf-8')
    predicted=estimator.predict(validation).tolist()
    actual=[r['actual'] for r in validation]
    baseline=['Yes' if r['score']>=50 else 'No' for r in validation]
    report=dict(version='context-corrector-v1',mode='offline reuse of live GPT scores',api_calls=0,
        selected_C=selected['C'],development_group_oof_candidates=candidates,
        validation_GPT_score_50=metrics(actual,baseline),validation_context_corrector=metrics(actual,predicted),
        corrected=sum(a!=y and b==y for a,b,y in zip(baseline,predicted,actual)),
        new_errors=sum(a==y and b!=y for a,b,y in zip(baseline,predicted,actual)),
        limitations=['Exploratory reuse of already-inspected validation cases, not a fresh confirmatory test',
            'Only 100 development cases; 5-fold CV is internal model selection, not independent replication',
            'A supervised conventional classifier is added; this is no longer a GPT-only system',
            'No validation-label-driven model selection or threshold retuning; final classifier uses its default decision rule',
            'No improvement is assumed or guaranteed'])
    records=[dict(id=r['id'],substance=r['input']['substance'],actual=r['actual'],GPT_score=r['score'],
        GPT_score_50=a,context_corrector=b,changed=a!=b) for r,a,b in zip(validation,baseline,predicted)]
    (output/'predictions_LOCAL_ONLY.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['Offline contextual correction pilot',f"Selected C: {selected['C']}",'API calls: 0']
    for key in ['validation_GPT_score_50','validation_context_corrector']:
        m=report[key];lines.append(f"{key}: {m['correct']}/{m['n']}, accuracy {m['accuracy']:.2%}, macro-F1 {m['macro_f1']:.5f}")
    lines.extend([f"Corrected: {report['corrected']} / New errors: {report['new_errors']}",'',*report['limitations']])
    (output/'summary.txt').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print(str(output))


if __name__=='__main__':main()
