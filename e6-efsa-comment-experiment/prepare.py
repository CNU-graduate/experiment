"""Build an E6 comparison using only relevant EFSA comment summaries."""
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OLD = ROOT / 'e6-rationale-experiment'


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(node):
    return ' '.join(''.join(node.itertext()).split())


def main():
    annotations = json.loads((HERE / 'comment_annotations.json').read_text(encoding='utf-8'))
    original = json.loads((OLD / 'examples_with_rationales.json').read_text(encoding='utf-8'))
    rows = {}
    data_hashes = {}
    for year in (2022, 2023, 2024):
        source = ROOT / 'data' / f'ESFA_{year}_remain.csv'
        data_hashes[source.name] = digest(source)
        with source.open(encoding='utf-8-sig', newline='') as handle:
            rows.update({r['id']: r for r in csv.DictReader(handle)})
    trees = {year: ET.parse(HERE / 'sources' / f'{year}.xml').getroot() for year in (2023, 2024)}
    audited, order = [], {}
    for evaluation_year, examples in original['years'].items():
        order[evaluation_year] = [r['id'] for r in examples]
        for example in examples:
            row = rows[example['id']]
            for field in ('substance', 'purpose', 'commodity', 'JMPR', 'EU', 'EFSA'):
                assert row[field].replace('\r\n', '\n') == example[field].replace('\r\n', '\n'), (row['id'], field)
            annotation = annotations['examples'][row['id']]
            year = int(row['year'])
            table_rows = []
            if year in trees:
                table_id = f"efs2{8111 if year == 2023 else 8841}-tbl-{int(row['source_table']):04d}"
                table = next(t for t in trees[year].findall('.//table-wrap') if t.get('id') == table_id)
                for tr in table.findall('.//tr'):
                    table_rows.append([text(cell) for cell in tr])
                comment_rows = [r for r in table_rows if r and r[0].lower().startswith('conclusion')]
                assert len(comment_rows) == 1, row['id']
                source_comment = ' '.join(comment_rows[0][1:])
                verification = 'Compared with primary article XML mirrored by Europe PMC'
                source_url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{'10466198' if year == 2023 else '11255603'}/#{table_id}"
            else:
                source_comment = row['efsa_comments']
                verification = 'Repository transcription; full 2022 article retrieval was unsuccessful. Primary web index also exposes the Thiamethoxam comment.'
                source_url = row['source_table_url']
            if annotation['status'] == 'comment_absent':
                assert source_comment.strip() in ('–', '-', '—', '')
            audited.append(dict(evaluation_year=int(evaluation_year), rank=example['rank'],
                id=row['id'], substance=row['substance'], purpose=row['purpose'], commodity=row['commodity'],
                EFSA=row['EFSA'], source_section=row['source_section'], source_table=row['source_table'],
                source_url=source_url, verification=verification, original_efsa_comment=source_comment,
                repository_efsa_comment=row['efsa_comments'], primary_table_rows=table_rows, **annotation))
    assert len(audited) == 12
    assert sum(r['rationale'] is not None for r in audited) == 6
    dump(HERE / 'source_examples.json', {'authorship': annotations['authorship'], 'examples': audited})
    by_id = {r['id']: r for r in audited}
    requests = []
    for line in (OLD / 'requests.jsonl').read_text(encoding='utf-8').splitlines():
        record = json.loads(line)
        if record['condition'] != 'E6':
            continue
        requests.append(record)
        treatment = json.loads(json.dumps(record))
        treatment['condition'] = 'E6_EFSA'
        prompt = json.loads(record['body']['messages'][1]['content'])
        for example, example_id in zip(prompt['examples'], order[str(record['year'])]):
            assert example['EFSA'] == by_id[example_id]['EFSA']
            rationale = by_id[example_id]['rationale']
            if rationale is not None:
                example['rationale'] = rationale
        restored = json.loads(json.dumps(prompt))
        for e in restored['examples']:
            e.pop('rationale', None)
        assert restored == json.loads(record['body']['messages'][1]['content'])
        assert set(prompt['test']) == {'substance', 'purpose', 'commodity', 'JMPR', 'EU'}
        treatment['body']['messages'][1]['content'] = json.dumps(prompt, ensure_ascii=False, sort_keys=True)
        requests.append(treatment)
    assert len(requests) == 420
    (HERE / 'requests.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in requests), encoding='utf-8')
    for year in (2023, 2024, 2025):
        record = next(r for r in requests if r['year'] == year and r['condition'] == 'E6_EFSA')
        dump(HERE / f'messages_{year}_first_case.json', record['body'])
    for name in ('source_snapshot.json', 'evaluation_key_LOCAL_ONLY.json', 'system_prompt.txt'):
        (HERE / name).write_bytes((OLD / name).read_bytes())
    runner = (OLD / 'run.py').read_text(encoding='utf-8').replace('E6_R', 'E6_EFSA').replace('rationales.json', 'comment_annotations.json')
    (HERE / 'run.py').write_text(runner, encoding='utf-8')
    fields = ['evaluation_year', 'rank', 'id', 'substance', 'purpose', 'commodity', 'EFSA', 'status', 'rationale', 'rationale_ko', 'note', 'source_url', 'source_section', 'source_table', 'verification', 'original_efsa_comment', 'repository_efsa_comment']
    with (HERE / 'comment_review.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(audited)
    lines = ['E6 실제 EFSA 코멘트와 요약', '원문 코멘트와 연구용 요약을 구별한다. null인 근거는 모델 예시에 추가하지 않는다.', '2022년: 저장소 전사본 기반. 2023·2024년: 원문 XML 비교표 대조.', '']
    for row in audited:
        lines.extend([f"평가 {row['evaluation_year']} / 순서 {row['rank']} / {row['id']} / {row['substance']}",
            f"목적·대상: {row['purpose']} / {row['commodity']} / 원래 판정: {row['EFSA']}",
            f"출처: {row['source_url']}", f"원문 검증: {row['verification']}",
            'EFSA 원문 코멘트:', row['original_efsa_comment'],
            '모델에 추가할 영어 요약:', row['rationale'] or '(추가하지 않음)',
            '한국어 설명:', row['rationale_ko'], '주의:', row['note'], ''])
    (HERE / 'source_review.txt').write_text('\n'.join(lines), encoding='utf-8')
    report = dict(version=annotations['version'], source_commit=json.loads((OLD / 'source_snapshot.json').read_text(encoding='utf-8'))['commit'],
        requests=420, unique_test_cases=210, examples=12, augmented_examples=6,
        annotation_coverage_by_evaluation_year={y: sum(by_id[i]['rationale'] is not None for i in ids) for y, ids in order.items()},
        statuses=dict(Counter(r['status'] for r in audited)), example_order=order,
        requests_sha256=digest(HERE / 'requests.jsonl'), rationales_sha256=digest(HERE / 'comment_annotations.json'),
        data_files_sha256=data_hashes, primary_xml_sha256={str(y): digest(HERE / 'sources' / f'{y}.xml') for y in trees},
        paid_api_calls=0,
        verified=['All original E6 example inputs and labels match repository data', 'All 210 control prompts unchanged', 'Removing rationale restores every original payload', 'No target answers or comments in inference test fields', 'Missing or scope-mismatched comments do not receive invented rationales'],
        limitations=['Only 6/12 examples have usable summaries; this is partial comment augmentation', '2022 comments are repository transcriptions, not independently full-text verified', '2023/2024 table comments may be narrower than the CSV concatenation', 'Evaluation cases were inspected in previous work'])
    dump(HERE / 'validation.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
