import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from .data import Dataset, inputs
from .selection import Selector, RANDOM
from .prompt import build_prompt, parse_label, SYSTEM
from .providers import Provider, mock_call, KEYS
from .evaluation import write_csv, evaluate


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def error_policy(exc):
    """Return a safe HTTP status and whether the entire run must stop."""
    status = getattr(exc, 'status_code', None)
    if status is None:
        status = getattr(exc, 'code', None)
    if not isinstance(status, int):
        status = None
    # Authentication, credit, request and model errors need operator action.
    fatal = status is not None and 400 <= status < 500 and status not in (408, 409, 429)
    return status, fatal


def run(config, output, mode='dry-run', approved=False, *, system_prompt=None):
    system = SYSTEM if system_prompt is None else system_prompt
    explained = config.get('response_format', 'label') == 'explanation'
    if config.get('response_format', 'label') not in ('label', 'explanation'):
        raise ValueError('Unsupported response_format')
    if explained:
        from .explanation import parse_explanation
        if system_prompt is None:
            raise ValueError('Explanation output requires an explicit system prompt')
    if not isinstance(system, str) or not system.strip():
        raise ValueError('A nonempty system prompt is required')
    if any(c in ('P1', 'P2') for c in config['conditions']) and system_prompt is None:
        raise ValueError('Instruction variants require an explicit system prompt')
    if mode == 'live' and not approved:
        raise ValueError('Live calls require separate user approval and --approve-paid-api')
    data = Dataset(config['data_dir'])
    annotations = {}
    annotation_files = []
    if 'E6' in config['conditions'] and config.get('priority_annotations'):
        annotation_path = Path(config['priority_annotations'])
        if not annotation_path.is_absolute():
            annotation_path = Path(config['data_dir']) / annotation_path
        raw = annotation_path.read_bytes()
        annotations = json.loads(raw)['annotations']
        annotation_files = [{'file': annotation_path.name, 'sha256': hashlib.sha256(raw).hexdigest()}]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output/'validation.csv', data.files)
    write_csv(output/'data_issues.csv', data.issues, ['year', 'type', 'detail'])
    identity = {'config': config, 'files': data.files, 'mode': mode,
                                            'system': system, 'version': 2, 'annotation_files': annotation_files,
                                            'implementation': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                for p in sorted(Path(__file__).parent.glob('*.py'))}}
    fingerprint = hashlib.sha256(canonical(identity).encode()).hexdigest()
    # Only the retry/logging implementation changed; allow the exact previous
    # implementation with identical data, config, prompt and other source files.
    legacy = dict(identity, implementation=dict(identity['implementation']))
    legacy['implementation']['runner.py'] = '5b2c7ff7d36581b06d80967f261afa15cac9a8d542beefa56352e37fd0af3d8a'
    legacy_fingerprint = hashlib.sha256(canonical(legacy).encode()).hexdigest()
    db = sqlite3.connect(output/'checkpoint.sqlite')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS metadata (fingerprint TEXT)')
        old = db.execute('SELECT fingerprint FROM metadata').fetchone()
        if old and old[0] not in (fingerprint, legacy_fingerprint):
            raise ValueError('Output belongs to different config/data/mode; use a new directory')
        if not old:
            db.execute('INSERT INTO metadata VALUES (?)', (fingerprint,))
        db.execute('CREATE TABLE IF NOT EXISTS cases (key TEXT PRIMARY KEY, payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, payload TEXT)')
        db.commit()
        selector = Selector(data.pools, {y: [inputs(r) for r in rows] for y, rows in data.tests.items()}, annotations)
        clients = {}
        if mode == 'live':
            clients = {p: (Provider(p, m, config) if system_prompt is None else
                           Provider(p, m, config, system_prompt=system))
                       for p, m in config['models'].items()}
        # Persist the entire plan before any calls, so interruptions retain denominator.
        for year in config['years']:
            if year not in data.tests:
                raise ValueError(f'Missing valid test/answerkey for {year}')
            for condition in config['conditions']:
                seeds = config['seeds'] if condition in RANDOM else [None]
                for seed in seeds:
                    for test in data.tests[year]:
                        examples, error = [], ''
                        try:
                            examples = ([] if condition in ('P1', 'P2') else
                                        selector.choose(condition, year, seed, inputs(test)))
                        except ValueError as exc:
                            error = str(exc)
                        prompt = build_prompt(test, examples)
                        if config.get('prompt_newlines') == 'lf':
                            prompt = prompt.replace('\\r\\n', '\\n')
                        elif config.get('prompt_newlines') == 'crlf':
                            prompt = prompt.replace('\\r\\n', '\\n').replace('\\n', '\\r\\n')
                        for provider, model in config['models'].items():
                            key = canonical([year, condition, seed, test['id'], provider])
                            payload = {'mode': mode, 'provider': provider, 'model': model or 'UNCONFIGURED',
                                       'year': year, 'condition': condition, 'seed': seed,
                                       'id': test['id'], 'actual': test['EFSA'], 'prediction': '',
                                       'status': 'excluded' if error else 'pending', 'error': error,
                                       'examples': [{'id': r['id'], 'year': int(r['year']), 'label': r['EFSA'],
                                                     'similarity': r.get('similarity', '')} for r in examples],
                                       'prompt_sha256': hashlib.sha256((system+prompt).encode()).hexdigest(),
                                       'prompt': prompt}
                            db.execute('INSERT OR IGNORE INTO cases VALUES (?, ?)', (key, canonical(payload)))
        db.commit()
        (output/'selection_audit.json').write_text(json.dumps(selector.audit, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest = {'annotation_files': annotation_files, 'fingerprint': fingerprint, 'mode': mode, 'config': config,
                    'data_files': data.files, 'system_prompt': system,
                    'created_utc': datetime.now(timezone.utc).isoformat()}
        if not (output/'manifest.json').exists():
            (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            for key, stored in db.execute('SELECT key, payload FROM cases ORDER BY key').fetchall():
                row = json.loads(stored)
                if row['status'] in ('success', 'excluded', 'planned'):
                    continue
                if mode == 'dry-run':
                    row['status'] = 'planned'
                else:
                    for attempt in range(1, config['max_attempts']+1):
                        stop_run = False
                        started = time.monotonic()
                        call = {'case_key': key, 'mode': mode, 'provider': row['provider'],
                                'model': row['model'], 'attempt': attempt,
                                'started_utc': datetime.now(timezone.utc).isoformat(),
                                'status': 'started', 'error_type': '', 'response': '',
                                'usage': '', 'response_id': '', 'seconds': '', 'http_status': ''}
                        cursor = db.execute('INSERT INTO calls(payload) VALUES (?)', (canonical(call),))
                        db.commit()
                        try:
                            raw, usage, response_id = (mock_call(row['provider'], row['prompt']) if mode == 'mock'
                                else clients[row['provider']].call(row['prompt']))
                            call.update(response=raw, usage=canonical(usage), response_id=response_id)
                            if explained:
                                if mode == 'mock':
                                    raw = 'Mock explanation; not model evidence.\nFinal label: ' + raw
                                    call['response'] = raw
                                label, explanation = parse_explanation(raw)
                                row.update(prediction=label, explanation=explanation, response=raw,
                                           status='success', error='')
                            else:
                                row.update(prediction=parse_label(raw), status='success', error='')
                            call['status'] = 'success'
                        except Exception as exc:
                            # Do not persist SDK exception messages: they may contain request secrets.
                            row.update(prediction='', status='error', error=type(exc).__name__)
                            call.update(status='error', error_type=type(exc).__name__)
                            status, stop_run = error_policy(exc)
                            call['http_status'] = status if status is not None else ''
                        call['seconds'] = time.monotonic()-started
                        db.execute('UPDATE calls SET payload=? WHERE id=?', (canonical(call), cursor.lastrowid))
                        db.execute('UPDATE cases SET payload=? WHERE key=?', (canonical(row), key))
                        db.commit()
                        if stop_run:
                            raise ValueError(f'Experiment stopped: HTTP {status}. Check API credits, credentials, model and request settings; saved results can be resumed.')
                        if row['status'] == 'success':
                            break
                        if attempt < config['max_attempts']:
                            time.sleep(config['retry_delay_seconds'] * 2**(attempt-1))
                    if row['status'] == 'error' and mode == 'live':
                        raise ValueError('Experiment stopped after repeated API/response errors. Check api_errors.csv before resuming.')
                db.execute('UPDATE cases SET payload=? WHERE key=?', (canonical(row), key))
                db.commit()
        finally:
            export(db, output)
        return {'cases': db.execute('SELECT COUNT(*) FROM cases').fetchone()[0],
                'calls': db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]}
    finally:
        db.close()


def export(db, output):
    rows = [json.loads(x[0]) for x in db.execute('SELECT payload FROM cases ORDER BY key')]
    example_rows = []
    for row in rows:
        for rank, e in enumerate(row['examples'], 1):
            example_rows.append({k: row[k] for k in ('mode', 'provider', 'model', 'year', 'condition', 'seed', 'id')} |
                                {'rank': rank, 'example_id': e['id'], 'example_year': e['year'],
                                 'example_label': e['label'], 'similarity': e['similarity']})
    with (output/'prompts.jsonl').open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(canonical({k: row[k] for k in ('provider', 'model', 'year', 'condition', 'seed', 'id', 'prompt')}) + '\n')
    write_csv(output/'examples.csv', example_rows, ['mode','provider','model','year','condition','seed','id','rank','example_id','example_year','example_label','similarity'])
    public = [{k: v for k, v in r.items() if k not in ('examples', 'prompt')} for r in rows]
    write_csv(output/'predictions.csv', public)
    write_csv(output/'exclusions.csv', [r for r in public if r['status']=='excluded'], list(public[0]) if public else None)
    calls = [json.loads(x[0]) for x in db.execute('SELECT payload FROM calls ORDER BY id')]
    fields = ['case_key','mode','provider','model','attempt','started_utc','status','error_type','response','usage','response_id','seconds','http_status']
    write_csv(output/'api_calls.csv', calls, fields)
    write_csv(output/'api_errors.csv', [c for c in calls if c['status']!='success'], fields)
    metrics, comparison = evaluate(rows)
    write_csv(output/'metrics.csv', metrics)
    write_csv(output/'comparison.csv', comparison)
