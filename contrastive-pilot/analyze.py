"""Analyze source accuracy, surface invariance and synthetic edit sensitivity separately."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE/'runs/live')
    args = parser.parse_args()
    output = args.output.resolve()
    manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    with (output/'predictions.csv').open(encoding='utf-8-sig', newline='') as handle:
        predictions = list(csv.DictReader(handle))
    cases = {r['case_id']: r for r in json.loads((HERE/'cases_LOCAL_ONLY.json').read_text(encoding='utf-8'))}
    valid = [r for r in predictions if r['status']=='success']
    groups, families = defaultdict(list), defaultdict(dict)
    for row in valid:
        case = cases[row['case_id']]
        correct = row['prediction']==case['gold']
        groups[row['condition']].append(correct)
        families[(int(row['repeat']),case['family_id'])][row['condition']] = dict(prediction=row['prediction'],correct=correct)
    complete = [r for r in families.values() if set(r)=={'original','preserved','substantive'}]
    invariance = sum(r['original']['prediction']==r['preserved']['prediction'] for r in complete)
    flip = sum(r['original']['prediction']!=r['substantive']['prediction'] for r in complete)
    correct_pairs = sum(r['original']['correct'] and r['substantive']['correct'] for r in complete)
    triads = sum(all(item['correct'] for item in r.values()) for r in complete)
    round_rows=[]
    for repeat in sorted({int(r['repeat']) for r in valid}):
        round_families = [r for (rep,_),r in families.items() if rep==repeat and set(r)=={'original','preserved','substantive'}]
        counts = {condition:sum(r[condition]['correct'] for r in round_families) for condition in ['original','preserved','substantive']}
        round_rows.append(dict(repeat=repeat, complete_families=len(round_families),correct=counts,
            surface_invariant=sum(r['original']['prediction']==r['preserved']['prediction'] for r in round_families),
            substantive_correct_pair=sum(r['original']['correct'] and r['substantive']['correct'] for r in round_families),
            all_three_correct=sum(all(item['correct'] for item in r.values()) for r in round_families)))
    errors=[]
    for row in valid:
        case=cases[row['case_id']]
        if row['prediction']!=case['gold']:
            errors.append(dict(repeat=int(row['repeat']),family_id=case['family_id'],source_id=case['source_id'],
                substance=case['input']['substance'],condition=row['condition'],expected=case['gold'],prediction=row['prediction'],
                operation=case['operation'],input=case['input']))
    result=dict(mode=manifest['mode'],model=manifest['config']['models']['openai'],
        n_success=len(valid),planned_calls=manifest['planned_requests'],coverage=len(valid)/manifest['planned_requests'],
        condition_metrics={k:dict(correct=sum(v),n=len(v),accuracy=sum(v)/len(v)) for k,v in groups.items()},
        paired_metrics=dict(n_complete_triads=len(complete),surface_invariance_count=invariance,
            substantive_prediction_flip_count=flip,substantive_correct_pair_count=correct_pairs,
            all_three_correct_count=triads),round_metrics=round_rows,errors=errors,
        limitations=['Exploratory diagnostic; not an E6 improvement comparison',
            '20 purposively selected source cases, not 180 independent source cases',
            'Synthetic expected labels are assistant rule-derived; no independent expert validation',
            'Surface control only changes JSON field order and whitespace',
            'Hypothetical marker names can provide shortcut cues',
            'Report original EFSA-label accuracy separately from synthetic-label accuracy'])
    (output/'contrastive_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['Contrastive pilot results',f"Mode: {result['mode']} / Model: {result['model']}",
        f"Successful calls: {len(valid)}/{manifest['planned_requests']}",
        'Condition metrics (dependent repetitions; 20 source cases):']
    for k,v in result['condition_metrics'].items():
        lines.append(f"{k}: {v['correct']}/{v['n']} = {v['accuracy']:.2%}")
    lines.extend(['',f'Complete triads: {len(complete)}',f'Surface invariance: {invariance}/{len(complete)}',
        f'Substantive correct pair: {correct_pairs}/{len(complete)}',f'All three correct: {triads}/{len(complete)}','',
        'Errors:'])
    for e in errors:
        lines.append(f"Repeat {e['repeat']} / {e['source_id']} / {e['substance']} / {e['condition']}: expected {e['expected']}, predicted {e['prediction']}")
    lines.extend(['','Limitations:',*result['limitations']])
    (output/'contrastive_summary.txt').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='errors'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
