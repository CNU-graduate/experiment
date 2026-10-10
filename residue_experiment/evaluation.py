import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

METRICS = ('accuracy', 'precision', 'recall', 'macro_f1')


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else ['status'])
    path = Path(path)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def score(truth, predictions):
    matrix = confusion_matrix(truth, predictions, labels=['No', 'Yes'])
    return {'accuracy': accuracy_score(truth, predictions),
            'precision': precision_score(truth, predictions, pos_label='Yes', zero_division=0),
            'recall': recall_score(truth, predictions, pos_label='Yes', zero_division=0),
            'macro_f1': f1_score(truth, predictions, labels=['No', 'Yes'], average='macro', zero_division=0),
            'tn': int(matrix[0, 0]), 'fp': int(matrix[0, 1]),
            'fn': int(matrix[1, 0]), 'tp': int(matrix[1, 1])}


def evaluate(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r['mode'], r['provider'], r['model'], r['year'], r['condition'], r['seed']].append(r)
    results = []
    for key, cases in sorted(groups.items()):
        valid = [r for r in cases if r['status'] == 'success']
        metrics = score([r['actual'] for r in valid], [r['prediction'] for r in valid]) if valid else {m: '' for m in (*METRICS, 'tn', 'fp', 'fn', 'tp')}
        results.append(dict(zip(('mode', 'provider', 'model', 'year', 'condition', 'seed'), key),
                            n_total=len(cases), n_evaluated=len(valid), coverage=len(valid)/len(cases),
                            complete=len(valid) == len(cases), **metrics))
    comparisons = defaultdict(list)
    for r in results:
        comparisons[tuple(r[k] for k in ('mode', 'provider', 'model', 'year', 'condition'))].append(r)
    summary = []
    for key, reps in sorted(comparisons.items()):
        complete = [r for r in reps if r['complete']]
        row = dict(zip(('mode', 'provider', 'model', 'year', 'condition'), key),
                   repeats_planned=len(reps), repeats_complete=len(complete))
        for m in METRICS:
            vals = [r[m] for r in complete]
            row[m+'_mean'] = mean(vals) if vals else ''
            row[m+'_std'] = stdev(vals) if len(vals) > 1 else (0.0 if vals else '')
        summary.append(row)
    return results, summary
