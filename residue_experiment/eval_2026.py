"""Frozen R6C1 or P0 evaluation: 86 cases from 2026, three repetitions."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from statistics import mean

from .data import FIELDS, inputs
from .evaluation import score, write_csv
from .prompt import build_prompt, parse_label
from .prompt_search import Calls, hash_value, read, save, load_plan as load_search
from .prompt_transfer import load_plan as load_transfer
from .prompt_search_continue import repair_empty
from .risk_search import repair_connection

OUTPUT = 'results/r6c1-eval-2026'
SOURCE = 'results/prompt-search-v2-continued-patience2'
PREVIOUS = 'results/prompt-search-r6c1-eval-2023-2025'
INPUT_DIR = Path('C:/Users/hhj48/OneDrive/문서/카카오톡 받은 파일')


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        if not {'id', 'year', *FIELDS} <= set(reader.fieldnames or []):
            raise ValueError('Missing required CSV fields')
    if any(None in r or any(r.get(k) is None or not r[k].strip() for k in ('id', 'year', *FIELDS)) for r in rows):
        raise ValueError('Malformed or empty input fields')
    return rows


def signature(row):
    def norm(s):
        return re.sub(r'\s+', ' ', s.replace('\\r\\n', ' ').replace('\\n', ' ').replace('\\r', ' ')).strip()
    return tuple(norm(row[k]) for k in FIELDS)


def validate_pair(questions, answers):
    if len(questions) != 86 or len(answers) != 86:
        raise ValueError('Expected 86 questions and 86 answers')
    q, a = {r['id']: r for r in questions}, {r['id']: r for r in answers}
    if len(q) != 86 or len(a) != 86 or set(q) != set(a):
        raise ValueError('Duplicate or mismatched IDs')
    if len({signature(r) for r in questions}) != 86:
        raise ValueError('Duplicate normalized question inputs')
    rows = []
    for r in questions:
        answer = a[r['id']]
        if r['year'] != '2026' or answer['year'] != '2026':
            raise ValueError('Expected year 2026')
        if inputs(r) != inputs(answer):
            raise ValueError(f'Question/answer input mismatch: {r["id"]}')
        if answer.get('EFSA') not in ('Yes', 'No'):
            raise ValueError('Invalid answer label')
        if r['purpose'] not in ('Enforcement', 'Risk assessment'):
            raise ValueError('Invalid purpose')
        rows.append(dict(id=r['id'], year='2026', **inputs(r), EFSA=answer['EFSA']))
    return rows


def prepare(output, questions, answers, condition='R6C1'):
    if condition not in ('R6C1', 'P0'):
        raise ValueError('Unknown condition')
    rows = validate_pair(read_csv(questions), read_csv(answers))
    source = load_search(SOURCE)
    best = read(Path(SOURCE) / 'live/final_prompt.json')
    winner = read(Path(SOURCE) / 'live' / f'round-{best["completed_rounds"]:02d}' / 'selection.json')['winner']
    if best['plan_hash'] != source['plan_hash'] or best['name'] != 'R6C1' or any(best[k] != winner[k] for k in ('name', 'prompt')):
        raise ValueError('R6C1 winner mismatch')
    previous = load_transfer(PREVIOUS)
    groups = {'development': source['development'], 'selection': source['selection'],
              'previous_test': [r for rs in previous['tests'].values() for r in rs]}
    overlap = {name: [r['id'] for r in rows if signature(r) in {signature(x) for x in old}]
               for name, old in groups.items()}
    plan = {'version': 'r6c1-2026-v1', 'config': source['config'], 'prompt': best['prompt'],
            'name': best['name'], 'rows': rows, 'repeats': 3, 'expected_calls': 258,
            'source_plan_hash': source['plan_hash'], 'previous_test_plan_hash': previous['plan_hash'],
            'overlap': overlap, 'excluded_overlap_ids': sorted({i for ids in overlap.values() for i in ids}),
            'input_files': [{'path': str(Path(f).resolve()), 'sha256': hashlib.sha256(Path(f).read_bytes()).hexdigest()}
                            for f in (questions, answers)]}
    if condition == 'P0':
        reference = load_plan(OUTPUT)
        if any(plan[k] != reference[k] for k in ('rows', 'config', 'repeats', 'excluded_overlap_ids')):
            raise ValueError('P0 must use the same frozen data and settings as R6C1')
        plan.update(name='P0', prompt=source['p0'], comparison_plan_hash=reference['plan_hash'])
    plan['plan_hash'] = hash_value(plan)
    path = Path(output) / 'plan.json'
    if path.exists() and read(path) != plan:
        raise ValueError('Frozen plan differs; use a new output folder')
    save(path, plan)
    return plan


def load_plan(output):
    p = read(Path(output) / 'plan.json')
    digest = p.pop('plan_hash')
    if p['version'] != 'r6c1-2026-v1' or hash_value(p) != digest:
        raise ValueError('Frozen plan changed')
    p['plan_hash'] = digest
    return p


class EvaluationCalls(Calls):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.count += sum(len(list((self.folder / d).glob('*.json')))
                          for d in ('empty_response_attempts', 'connection_error_attempts'))


def run(plan, output, mode, max_calls=None):
    calls = EvaluationCalls(plan, output, mode, max_calls)
    predictions, metrics = [], []
    excluded = set(plan['excluded_overlap_ids'])
    for repeat in range(1, plan['repeats'] + 1):
        current = []
        for n, row in enumerate(plan['rows'], 1):
            label = parse_label(calls.call(f'test/2026/{plan["name"]}/{repeat}/{row["id"]}', plan['prompt'],
                                           build_prompt(row, []), 'prediction'))
            current.append(dict(id=row['id'], year='2026', substance=row['substance'], purpose=row['purpose'],
                                commodity=row['commodity'], repeat=repeat, actual=row['EFSA'], prediction=label,
                                correct=label == row['EFSA'], prior_input_overlap=row['id'] in excluded))
            if n % 10 == 0:
                print(f'2026 repeat {repeat}: {n}/{len(plan["rows"])}; calls={calls.count}', flush=True)
        predictions.extend(current)
        for subset in ('all_86', 'without_prior_overlap'):
            for purpose in ('all', 'Enforcement', 'Risk assessment'):
                group = [r for r in current if (subset == 'all_86' or not r['prior_input_overlap'])
                         and (purpose == 'all' or r['purpose'] == purpose)]
                if group:
                    metrics.append(dict(subset=subset, purpose=purpose, repeat=repeat, cases=len(group),
                                        **score([r['actual'] for r in group], [r['prediction'] for r in group])))
        write_csv(calls.folder / f'repeat-{repeat:02d}_predictions.csv', current)
        write_csv(calls.folder / 'test_predictions.csv', predictions)
        write_csv(calls.folder / 'test_metrics.csv', metrics)
        print(f'2026: repeat {repeat}/{plan["repeats"]} completed; {len(current)} cases', flush=True)
    summaries = {}
    for subset, purpose in sorted({(m['subset'], m['purpose']) for m in metrics}):
        group = [m for m in metrics if (m['subset'], m['purpose']) == (subset, purpose)]
        summaries.setdefault(subset, {})[purpose] = {
            'cases_per_repeat': group[0]['cases'],
            'accuracy_mean': mean(m['accuracy'] for m in group),
            'macro_f1_mean': mean(m['macro_f1'] for m in group),
            'fp_total': sum(m['fp'] for m in group), 'fn_total': sum(m['fn'] for m in group)}
    errors = [dict(id=r['id'], substance=r['substance'], purpose=r['purpose'], commodity=r['commodity'],
                   actual=r['EFSA'], wrong_count=sum(p['id'] == r['id'] and not p['correct'] for p in predictions))
              for r in plan['rows']]
    write_csv(calls.folder / 'error_frequency.csv', errors)
    result = {'mode': mode, 'name': plan['name'], 'cases': len(plan['rows']), 'repeats': plan['repeats'],
              'calls': calls.count, 'excluded_overlap_ids': plan['excluded_overlap_ids'], 'metrics': summaries}
    save(calls.folder / 'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'run', 'repair-empty', 'repair-connection'])
    parser.add_argument('--output', default=OUTPUT)
    parser.add_argument('--condition', choices=['R6C1', 'P0'], default='R6C1')
    parser.add_argument('--questions', default=str(INPUT_DIR / 'ESFA_202686.csv'))
    parser.add_argument('--answers', default=str(INPUT_DIR / 'ESFA_202686answerkey.csv'))
    parser.add_argument('--mode', choices=['mock', 'live'], default='mock')
    parser.add_argument('--max-calls', type=int)
    parser.add_argument('--call-id')
    a = parser.parse_args()
    if a.stage == 'prepare':
        p = prepare(a.output, a.questions, a.answers, a.condition)
        print(json.dumps({'name': p['name'], 'cases': len(p['rows']), 'repeats': p['repeats'], 'calls': p['expected_calls'], 'overlap': p['overlap']}))
        return
    if a.condition != 'R6C1':
        parser.error('--condition is prepare-only; run uses the frozen plan')
    if a.stage != 'prepare' and (a.questions != str(INPUT_DIR / 'ESFA_202686.csv') or a.answers != str(INPUT_DIR / 'ESFA_202686answerkey.csv')):
        parser.error('--questions and --answers are prepare-only')
    if a.stage == 'repair-connection' and not a.call_id:
        parser.error('Specify --call-id for repair-connection')
    p = load_plan(a.output)
    if a.mode == 'live' and a.stage == 'run':
        from dotenv import load_dotenv
        load_dotenv()
    lock = Path(a.output) / f'{a.mode}.lock'
    with lock.open('x'):
        pass
    try:
        if a.stage == 'repair-empty':
            result = repair_empty(p, a.output, a.mode)
        elif a.stage == 'repair-connection':
            result = repair_connection(p, a.output, a.mode, a.call_id)
        else:
            result = run(p, a.output, a.mode, a.max_calls)
        print(json.dumps(result))
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
