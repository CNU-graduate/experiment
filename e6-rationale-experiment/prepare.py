"""Freeze original E6 and E6+rationale requests. No API or SDK calls."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIELDS = {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    snapshot = json.loads((HERE / 'source_snapshot.json').read_text(encoding='utf-8'))
    source = ROOT / 'results/remain-v2/gpt-6-sol/2023-2025'
    for item in snapshot['files'] + [snapshot['scoring_source']]:
        raw = (ROOT / item['path']).read_bytes()
        variants = (raw, raw.replace(b'\r\n', b'\n'))
        blobs = [hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() for b in variants]
        if item['git_blob_sha'] not in blobs:
            raise ValueError(f"GitHub snapshot mismatch: {item['path']}")
    annotations = json.loads((HERE / 'rationales.json').read_text(encoding='utf-8'))
    rationales = annotations['examples']
    manifest = snapshot['original_manifest']
    system = manifest['system_prompt']
    records = [json.loads(line) for line in (source / 'prompts.jsonl').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    records = [r for r in records if r['condition'] == 'E6' and r['provider'] == 'openai']
    assert len(records) == 210
    with (source / 'examples.csv').open(encoding='utf-8-sig', newline='') as f:
        selected = defaultdict(list)
        for row in csv.DictReader(f):
            if row['condition'] == 'E6' and row['provider'] == 'openai':
                selected[(int(row['year']), row['id'])].append(row)
    requests, examples, review = [], {}, []
    seen_ids = set()
    for record in records:
        year, case_id = int(record['year']), record['id']
        payload = json.loads(record['prompt'])
        assert set(payload) == {'examples', 'test'} and set(payload['test']) == FIELDS
        assert len(payload['examples']) == 4
        order = sorted(selected[(year, case_id)], key=lambda r: int(r['rank']))
        assert len(order) == 4
        augmented = json.loads(record['prompt'])
        audit_examples = []
        for rank, (original, row) in enumerate(zip(payload['examples'], order), 1):
            example_id = row['example_id']
            annotation = rationales[example_id]
            assert int(row['example_year']) == year - 1
            assert set(original) == FIELDS | {'EFSA'}
            assert original['EFSA'] == row['example_label'] == annotation['expected_label']
            for quote in annotation['jmpr_quotes']:
                assert quote in original['JMPR'], (example_id, 'JMPR', quote)
            for quote in annotation['eu_quotes']:
                assert quote in original['EU'], (example_id, 'EU', quote)
            augmented['examples'][rank - 1]['rationale'] = annotation['rationale']
            audit_examples.append(dict(id=example_id, rank=rank, **original, **annotation))
            seen_ids.add(example_id)
        without = json.loads(json.dumps(augmented))
        for example in without['examples']:
            del example['rationale']
        assert without == payload
        assert augmented['test'] == payload['test']
        if str(year) not in examples:
            examples[str(year)] = audit_examples
            review.extend(dict(evaluation_year=year, **r) for r in audit_examples)
        else:
            assert examples[str(year)] == audit_examples
        for condition, prompt in [('E6', record['prompt']), ('E6_R', json.dumps(augmented, ensure_ascii=False, sort_keys=True))]:
            requests.append({
                'case_id': case_id, 'year': year, 'condition': condition,
                'body': {
                    'model': manifest['config']['models']['openai'],
                    'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
                    'max_tokens': manifest['config']['max_output_tokens']
                }
            })
    assert seen_ids == set(rationales) and len(requests) == 420
    # Freeze inference requests before separately reading local scoring labels.
    requests_path = HERE / 'requests.jsonl'
    requests_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in requests), encoding='utf-8')
    dump(HERE / 'examples_with_rationales.json', {'authorship': annotations['authorship'], 'years': examples})
    (HERE / 'system_prompt.txt').write_text(system, encoding='utf-8')
    for year in (2023, 2024, 2025):
        demo = next(r for r in requests if r['year'] == year and r['condition'] == 'E6_R')
        dump(HERE / f'messages_{year}_first_case.json', demo['body'])
    with (HERE / 'review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['evaluation_year', 'rank', 'id', 'substance', 'purpose', 'commodity', 'EFSA', 'rationale', 'rationale_ko', 'conditional', 'review_note', 'jmpr_quotes', 'eu_quotes', 'JMPR', 'EU']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in review:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in row.items()})
    with (source / 'predictions.csv').open(encoding='utf-8-sig', newline='') as f:
        keys = [{'case_id': r['id'], 'year': int(r['year']), 'actual': r['actual']} for r in csv.DictReader(f) if r['condition'] == 'E6' and r['provider'] == 'openai']
    assert len(keys) == 210 and {(r['year'], r['case_id']) for r in keys} == {(r['year'], r['case_id']) for r in requests}
    assert all(r['actual'] in ('Yes', 'No') for r in keys)
    dump(HERE / 'evaluation_key_LOCAL_ONLY.json', keys)
    report = {
        'version': annotations['version'], 'source_commit': snapshot['commit'],
        'requests': 420, 'unique_test_cases': 210, 'examples': 12,
        'example_order': {year: [e['id'] for e in rows] for year, rows in examples.items()},
        'conditional_examples': [r['id'] for r in review if r['conditional']],
        'verified': ['GitHub source blob hashes (LF checkout normalization)', '4 examples per year in saved request order', 'all 210 control prompts unchanged', 'all rationale quotations are literal source substrings', 'removing rationale restores original payload', 'test contains only original five input fields', 'system and model request settings unchanged'],
        'requests_sha256': sha(requests_path.read_bytes()),
        'rationales_sha256': sha((HERE / 'rationales.json').read_bytes()),
        'authorship': annotations['authorship'], 'paid_api_calls': 0
    }
    dump(HERE / 'validation.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
