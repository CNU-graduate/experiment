"""Score, fit on development only, validate, freeze, then evaluate."""
import argparse
import hashlib
import inspect
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(labels,predictions):
    tn=sum(a==b=='No' for a,b in zip(labels,predictions))
    tp=sum(a==b=='Yes' for a,b in zip(labels,predictions))
    fp=sum(a=='No' and b=='Yes' for a,b in zip(labels,predictions))
    fn=sum(a=='Yes' and b=='No' for a,b in zip(labels,predictions))
    divide=lambda a,b:a/b if b else 0.0
    return dict(n=len(labels),correct=tn+tp,accuracy=divide(tn+tp,len(labels)),
        macro_f1=(divide(2*tp,2*tp+fp+fn)+divide(2*tn,2*tn+fp+fn))/2,
        precision=divide(tp,tp+fp),recall=divide(tp,tp+fn),tn=tn,fp=fp,fn=fn,tp=tp)


def classify(scores,threshold):
    return ['Yes' if s>=threshold else 'No' for s in scores]


def choose_threshold(scores,labels):
    curve=[dict(threshold=t,**metrics(labels,classify(scores,t))) for t in range(102)]
    winner=max(curve,key=lambda r:(r['macro_f1'],r['accuracy'],-abs(r['threshold']-50),-r['threshold']))
    return winner['threshold'],curve


def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def score_diagnostics(scores,labels):
    positive=[s for s,y in zip(scores,labels) if y=='Yes']
    negative=[s for s,y in zip(scores,labels) if y=='No']
    auc=sum((a>b)+0.5*(a==b) for a in positive for b in negative)/(len(positive)*len(negative))
    return dict(unique_scores=len(set(scores)),extreme_score_fraction=sum(s in (0,100) for s in scores)/len(scores),auc=auc)


def fit_and_validate(results,labels,requests,output):
    sets={}
    for phase in ['development','validation']:
        items=[r for r in requests if r['phase']==phase]
        if not all(r['key'] in results and results[r['key']]['status']=='success' for r in items):
            raise ValueError(f'{phase} scores incomplete; no threshold or evaluation')
        sets[phase]=([results[r['key']]['value'] for r in items],[labels[f"{phase}:{r['case_id']}"] for r in items])
    # Evaluation labels and scores cannot participate in threshold selection.
    threshold,curve=choose_threshold(*sets['development'])
    baseline=metrics(sets['validation'][1],classify(sets['validation'][0],50))
    tuned=metrics(sets['validation'][1],classify(sets['validation'][0],threshold))
    epsilon=1e-12
    passed=(tuned['macro_f1']>=baseline['macro_f1']-epsilon and tuned['accuracy']>=baseline['accuracy']-epsilon
        and (tuned['macro_f1']>baseline['macro_f1']+epsilon or tuned['accuracy']>baseline['accuracy']+epsilon))
    fitted=dict(threshold=threshold,selected_from='development only',validation_passed=passed,
        validation_B_threshold_50=baseline,validation_C_frozen_threshold=tuned,
        diagnostics={p:score_diagnostics(*sets[p]) for p in sets},
        calibration_response_sha256=hashlib.sha256(json.dumps({k:v for k,v in results.items() if k.startswith(('development:','validation:'))},sort_keys=True).encode()).hexdigest())
    path=output/'frozen_threshold.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=fitted:
        raise ValueError('Frozen threshold differs; refusing to overwrite')
    dump(path,fitted)
    dump(output/'development_threshold_curve.json',curve)
    return fitted


def summarize(results,labels,requests,fitted,output,mode):
    report=dict(mode=mode,completed_requests=sum(r['status']=='success' for r in results.values()),
        planned_calibration_requests=sum(r['phase']!='evaluation' for r in requests),
        frozen_threshold=fitted,method='Uncalibrated model scores plus a development-selected decision threshold')
    items=[r for r in requests if r['phase']=='evaluation']
    if fitted and all(r['key'] in results and results[r['key']]['status']=='success' for r in items):
        direct={r['case_id']:results[r['key']]['value'] for r in items if r['kind']=='direct'}
        scores={r['case_id']:results[r['key']]['value'] for r in items if r['kind']=='score'}
        ids=sorted(scores)
        actual=[labels[f'evaluation:{i}'] for i in ids]
        predictions={'A_direct':[direct[i] for i in ids],
            'B_score_50':classify([scores[i] for i in ids],50),
            'C_score_tuned':classify([scores[i] for i in ids],fitted['threshold'])}
        report['evaluation']={k:metrics(actual,p) for k,p in predictions.items()}
        report['evaluation_diagnostics']=score_diagnostics([scores[i] for i in ids],actual)
        paired=[]
        for i,case_id in enumerate(ids):
            paired.append(dict(case_id=case_id,actual=actual[i],score=scores[case_id],**{k:p[i] for k,p in predictions.items()}))
        dump(output/'evaluation_predictions_LOCAL_ONLY.json',paired)
        report['B_to_C_changes']=dict(
            corrected=sum(p['B_score_50']!=p['actual'] and p['C_score_tuned']==p['actual'] for p in paired),
            new_errors=sum(p['B_score_50']==p['actual'] and p['C_score_tuned']!=p['actual'] for p in paired))
    report['limitations']=['One retrospective pilot; no claim of untouched evaluation data',
        'Development/validation split by normalized substance name; chemical aliases are not fully resolved',
        'Evaluation can contain substances seen in historical data',
        'B/C share exactly the same evaluation model scores; only decision threshold changes',
        'Mock results are arbitrary infrastructure checks, never model-performance evidence']
    dump(output/'summary.json',report)
    lines=['Threshold pilot result',f'Mode: {mode}',f"Successful API/model records: {report['completed_requests']}"]
    if fitted:
        lines.extend([f"Frozen threshold: {fitted['threshold']}",f"Validation gate passed: {fitted['validation_passed']}"])
        for name in ['validation_B_threshold_50','validation_C_frozen_threshold']:
            m=fitted[name];lines.append(f"{name}: accuracy {m['accuracy']:.2%}, macro-F1 {m['macro_f1']:.5f}")
    for name,m in report.get('evaluation',{}).items():
        lines.append(f"{name}: {m['correct']}/{m['n']}, accuracy {m['accuracy']:.2%}, macro-F1 {m['macro_f1']:.5f}")
    if fitted and not fitted['validation_passed'] and 'evaluation' not in report:
        lines.append('Evaluation stopped: the selected threshold did not pass the pre-specified validation gate.')
    lines.extend(['',*report['limitations']])
    (output/'summary.txt').write_text('\n'.join(lines),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['dry-run','mock','live'],default='dry-run')
    parser.add_argument('--phase',choices=['all','calibration','evaluation'],default='all')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--approve-paid-api',action='store_true')
    args=parser.parse_args()
    if args.mode=='live' and not args.approve_paid_api:parser.error('live requires --approve-paid-api')
    plan=json.loads((HERE/'plan.json').read_text(encoding='utf-8'))
    if digest(HERE/'requests.jsonl')!=plan['requests_sha256']:raise ValueError('Frozen requests changed')
    requests=[json.loads(line) for line in (HERE/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    print(json.dumps(dict(mode=args.mode,phase=args.phase,development=plan['dev_n'],validation=plan['validation_n'],evaluation=plan['evaluation_n'],max_paid_calls=plan['max_paid_calls'],evaluation_year=plan['evaluation_year']),ensure_ascii=False),flush=True)
    if args.mode=='dry-run':return
    output=(args.output or HERE/'runs'/args.mode).resolve()
    output.mkdir(parents=True,exist_ok=True)
    labels=json.loads((HERE/'labels_LOCAL_ONLY.json').read_text(encoding='utf-8'))
    from residue_experiment.providers import Provider
    identity=dict(mode=args.mode,plan_sha256=digest(HERE/'plan.json'),labels_sha256=digest(HERE/'labels_LOCAL_ONLY.json'),
        implementation_sha256=digest(Path(__file__).resolve()),provider_sha256=digest(ROOT/'residue_experiment/providers.py'))
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    lock=output/'run.lock'
    with lock.open('x',encoding='utf-8') as handle:handle.write(str(time.time()))
    results={};fitted=None;verified=False
    try:
        with sqlite3.connect(output/'checkpoint.sqlite',timeout=0) as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (fingerprint TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY,payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY,key TEXT,status TEXT,payload TEXT)')
            old=db.execute('SELECT fingerprint FROM metadata').fetchone()
            if old and old[0]!=fingerprint:raise ValueError('Changed data/settings/code/mode: use a new output directory')
            if not old:db.execute('INSERT INTO metadata VALUES (?)',(fingerprint,))
            db.commit();verified=True
            results={k:json.loads(payload) for k,payload in db.execute('SELECT key,payload FROM results')}
            if db.execute("SELECT 1 FROM calls WHERE status='started'").fetchone():
                raise ValueError('Interrupted request outcome unknown; inspect checkpoint before resending')
            dump(output/'manifest.json',dict(fingerprint=fingerprint,mode=args.mode,model=plan['model'],max_paid_calls=plan['max_paid_calls'],identity=identity,plan=plan))
            clients={}
            if args.mode=='live':
                from dotenv import load_dotenv
                load_dotenv(ROOT/'.env',override=False)
            def execute(items):
                for item in items:
                    key=item['key']
                    if key in results:
                        if results[key]['status']=='success':continue
                        raise ValueError(f'Previous failed call requires review: {key}')
                    count=db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]
                    if count>=plan['max_paid_calls']:raise ValueError('Cumulative request budget exhausted')
                    record=dict(key=key,case_id=item['case_id'],phase=item['phase'],kind=item['kind'],status='started',started_epoch=time.time())
                    cursor=db.execute('INSERT INTO calls(key,status,payload) VALUES (?,?,?)',(key,'started',json.dumps(record)))
                    db.commit();started=time.monotonic()
                    try:
                        if args.mode=='mock':
                            number=int(hashlib.sha256(key.encode()).hexdigest()[:8],16)
                            raw=str(number%101) if item['kind']=='score' else ('Yes' if number%2 else 'No')
                            usage={};rid='mock'
                        else:
                            kind=item['kind']
                            if kind not in clients:
                                system=item['body']['messages'][0]['content']
                                config=dict(api_backend='openrouter',timeout_seconds=120,max_output_tokens=1000,system_prompt=system)
                                kwargs={'system_prompt':system} if 'system_prompt' in inspect.signature(Provider).parameters else {}
                                clients[kind]=Provider('openai',plan['model'],config,**kwargs)
                            raw,usage,rid=clients[kind].call(item['body']['messages'][1]['content'])
                        record.update(raw=raw,usage=usage,response_id=rid)
                        value=raw.strip()
                        if item['kind']=='score':
                            if not re.fullmatch(r'(?:0|[1-9][0-9]?|100)',value):raise ValueError('Invalid integer score')
                            value=int(value)
                        elif value not in ('Yes','No'):raise ValueError('Invalid classification label')
                        record.update(value=value,status='success')
                    except Exception as exc:
                        record.update(status='error',error_type=type(exc).__name__)
                    record['seconds']=time.monotonic()-started
                    db.execute('UPDATE calls SET status=?,payload=? WHERE id=?',(record['status'],json.dumps(record,ensure_ascii=False),cursor.lastrowid))
                    db.execute('INSERT INTO results VALUES (?,?)',(key,json.dumps(record,ensure_ascii=False)))
                    db.commit();results[key]=record
                    if record['status']!='success':raise ValueError(f'API/format failure: {key}. No automatic retry.')
                    if len(results)%10==0:print(f'{len(results)}/{plan["max_paid_calls"]} successful',flush=True)
            if args.phase in ('all','calibration'):
                execute([r for r in requests if r['phase']=='development'])
                execute([r for r in requests if r['phase']=='validation'])
            fitted=fit_and_validate(results,labels,requests,output)
            if args.phase in ('all','evaluation'):
                if fitted['validation_passed']:
                    execute([r for r in requests if r['phase']=='evaluation'])
                else:
                    print('Validation gate failed: evaluation calls were not issued.',flush=True)
            report=summarize(results,labels,requests,fitted,output,args.mode)
            print(json.dumps(dict(output=str(output),successful=len(results),threshold=fitted['threshold'],validation_passed=fitted['validation_passed'],evaluation_complete='evaluation' in report),ensure_ascii=False),flush=True)
    finally:
        if verified:
            dump(output/'responses.json',results)
            summarize(results,labels,requests,fitted,output,args.mode)
        lock.unlink()


if __name__=='__main__':
    main()
