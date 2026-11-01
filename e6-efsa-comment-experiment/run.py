"""Run the frozen E6 control/treatment through the repository's existing adapter."""
import argparse
import csv
import hashlib
import inspect
import json
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(actual, predicted):
    tn = sum(a == p == 'No' for a, p in zip(actual, predicted))
    tp = sum(a == p == 'Yes' for a, p in zip(actual, predicted))
    fp = sum(a == 'No' and p == 'Yes' for a, p in zip(actual, predicted))
    fn = sum(a == 'Yes' and p == 'No' for a, p in zip(actual, predicted))
    safe = lambda n, d: n / d if d else 0.0
    return dict(accuracy=safe(tp + tn, len(actual)),
                macro_f1=(safe(2 * tp, 2 * tp + fp + fn) + safe(2 * tn, 2 * tn + fp + fn)) / 2,
                precision=safe(tp, tp + fp), recall=safe(tp, tp + fn), tn=tn, fp=fp, fn=fn, tp=tp)


def export(db, planned, output):
    results = [json.loads(r[0]) for r in db.execute('SELECT payload FROM results ORDER BY key')]
    columns = ['repeat', 'condition', 'year', 'case_id', 'status', 'prediction', 'response', 'response_id', 'usage', 'seconds']
    with (output / 'predictions.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in results:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v for k, v in row.items() if k in columns})
    # Scoring labels are loaded only here, never passed to the provider.
    answers = {(r['year'], r['case_id']): r['actual'] for r in json.loads((HERE / 'evaluation_key_LOCAL_ONLY.json').read_text(encoding='utf-8'))}
    groups = defaultdict(list)
    for key, item in planned:
        groups[(item['repeat'], item['condition'], 'all')].append(key)
        groups[(item['repeat'], item['condition'], item['year'])].append(key)
    saved = {r['key']: r for r in results if r['status'] == 'success'}
    scores = []
    for (repeat, condition, year), keys in groups.items():
        valid = [saved[k] for k in keys if k in saved]
        score = metrics([answers[(r['year'], r['case_id'])] for r in valid], [r['prediction'] for r in valid]) if valid else {}
        scores.append(dict(repeat=repeat, condition=condition, year=year, n_total=len(keys), n_evaluated=len(valid), coverage=len(valid)/len(keys), complete=len(valid)==len(keys), **score))
    (output / 'metrics.json').write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['dry-run', 'mock', 'live'], default='dry-run')
    p.add_argument('--condition', choices=['both', 'E6', 'E6_EFSA'], default='both')
    p.add_argument('--year', type=int, choices=[2023, 2024, 2025])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--limit', type=int, help='Smoke test only; limits total planned requests')
    p.add_argument('--output', type=Path)
    p.add_argument('--approve-paid-api', action='store_true')
    args = p.parse_args()
    if args.repeats < 1 or (args.limit is not None and args.limit < 1):
        p.error('repeats and limit must be positive')
    if args.mode == 'live' and not args.approve_paid_api:
        p.error('live requires --approve-paid-api')
    validation = json.loads((HERE / 'validation.json').read_text(encoding='utf-8'))
    if digest(HERE / 'requests.jsonl') != validation['requests_sha256'] or digest(HERE / 'comment_annotations.json') != validation['rationales_sha256']:
        raise ValueError('Frozen inputs changed: rerun prepare.py and use a new output directory')
    requests = [json.loads(line) for line in (HERE / 'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    requests = [r for r in requests if (args.condition == 'both' or r['condition'] == args.condition) and (args.year is None or r['year'] == args.year)]
    planned = []
    for repeat in range(1, args.repeats + 1):
        for record in requests:
            item = dict(record, repeat=repeat)
            key = f"{repeat}:{record['condition']}:{record['year']}:{record['case_id']}"
            planned.append((key, item))
    if args.limit:
        planned = planned[:args.limit]
    config = json.loads((HERE / 'source_snapshot.json').read_text(encoding='utf-8'))['original_manifest']['config']
    print(json.dumps(dict(mode=args.mode, planned_requests=len(planned), conditions=sorted({r['condition'] for _, r in planned}), model=config['models']['openai'], max_attempts=config['max_attempts']), ensure_ascii=False))
    if args.mode == 'dry-run':
        return
    from residue_experiment.prompt import parse_label
    from residue_experiment.providers import Provider, mock_call
    identity = dict(mode=args.mode, plan=[(k, r['body']) for k, r in planned],
                    key_sha256=digest(HERE / 'evaluation_key_LOCAL_ONLY.json'),
                    implementation={str(path.relative_to(ROOT)): digest(path) for path in [Path(__file__).resolve(), ROOT / 'residue_experiment/providers.py', ROOT / 'residue_experiment/prompt.py']})
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    output = (args.output or HERE / 'runs' / args.mode).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output / 'checkpoint.sqlite', timeout=0) as db:
        # The lock file prevents concurrent writers; each call is committed separately.
        lock = output / 'run.lock'
        with lock.open('x', encoding='utf-8') as handle:
            handle.write(datetime.now(timezone.utc).isoformat())
        verified_output = False
        try:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (fingerprint TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, payload TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, key TEXT, status TEXT, payload TEXT)')
            old = db.execute('SELECT fingerprint FROM metadata').fetchone()
            if old and old[0] != fingerprint:
                raise ValueError('Different plan/settings/code: choose another --output')
            if not old:
                db.execute('INSERT INTO metadata VALUES (?)', (fingerprint,))
            db.commit()
            verified_output = True
            if db.execute("SELECT 1 FROM calls WHERE status='started'").fetchone():
                raise ValueError('An interrupted request has an unknown outcome; inspect checkpoint before resending')
            manifest = dict(fingerprint=fingerprint, mode=args.mode, planned_requests=len(planned), config=config,
                            requests_sha256=validation['requests_sha256'], source_commit=validation['source_commit'],
                            execution_order='interleaved E6 and E6_EFSA in each repeat', mock_is_not_model_performance=args.mode=='mock')
            (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            client = None
            if args.mode == 'live':
                from dotenv import load_dotenv
                load_dotenv(ROOT / '.env', override=False)
                config = dict(config, system_prompt=requests[0]['body']['messages'][0]['content'])
                kwargs = {'system_prompt': config['system_prompt']} if 'system_prompt' in inspect.signature(Provider).parameters else {}
                client = Provider('openai', config['models']['openai'], config, **kwargs)
            for index, (key, item) in enumerate(planned, 1):
                previous = db.execute('SELECT payload FROM results WHERE key=?', (key,)).fetchone()
                if previous and json.loads(previous[0])['status'] == 'success':
                    continue
                used = db.execute('SELECT COUNT(*) FROM calls WHERE key=?', (key,)).fetchone()[0]
                if used >= config['max_attempts']:
                    raise ValueError(f'Attempt budget exhausted for {key}')
                for attempt in range(used + 1, config['max_attempts'] + 1):
                    call = dict(attempt=attempt, started_utc=datetime.now(timezone.utc).isoformat())
                    cursor = db.execute('INSERT INTO calls(key,status,payload) VALUES (?,?,?)', (key, 'started', json.dumps(call)))
                    db.commit()
                    started = time.monotonic()
                    row = {k: item[k] for k in ['repeat', 'condition', 'year', 'case_id']}
                    row.update(key=key, status='error', prediction='', response='', usage={}, response_id='')
                    fatal = False
                    try:
                        prompt = item['body']['messages'][1]['content']
                        raw, usage, rid = mock_call('openai', prompt) if args.mode == 'mock' else client.call(prompt)
                        row.update(response=raw, usage=usage, response_id=rid)
                        row.update(prediction=parse_label(raw), status='success')
                    except Exception as exc:
                        # Do not store exception messages, which can contain credentials.
                        row['error_type'] = type(exc).__name__
                        status = getattr(exc, 'status_code', None)
                        fatal = isinstance(status, int) and 400 <= status < 500 and status not in (408, 409, 429)
                    row['seconds'] = time.monotonic() - started
                    call.update(row)
                    db.execute('UPDATE calls SET status=?,payload=? WHERE id=?', (row['status'], json.dumps(call, ensure_ascii=False), cursor.lastrowid))
                    db.execute('INSERT OR REPLACE INTO results VALUES (?,?)', (key, json.dumps(row, ensure_ascii=False)))
                    db.commit()
                    if row['status'] == 'success':
                        break
                    if fatal or attempt == config['max_attempts']:
                        raise ValueError(f'API/format error for {key}; inspect checkpoint')
                    time.sleep(config['retry_delay_seconds'] * 2**(attempt - 1))
                if index % 10 == 0:
                    print(f'{index}/{len(planned)} complete', flush=True)
                export(db, planned, output)
        finally:
            if verified_output:
                export(db, planned, output)
            lock.unlink()
    print(str(output))


if __name__ == '__main__':
    main()
