"""Build the pre-2023 pool using exact parsed field equality only."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'reports' / 'pre2023_exact_dedup'
YEARS = (2018, 2019, 2021, 2022)
INPUTS = ('substance', 'purpose', 'commodity', 'JMPR', 'EU')
KEY = (*INPUTS, 'EFSA')


def main():
    rows, columns, sources = [], [], []
    for year in YEARS:
        for suffix in ('70answerkey', '_remain'):
            path = ROOT / 'data' / f'ESFA_{year}{suffix}.csv'
            with path.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                for column in reader.fieldnames:
                    if column not in columns:
                        columns.append(column)
                batch = list(reader)
            assert all(all(r.get(k) is not None for k in KEY) for r in batch)
            rows.extend(dict(r, source_file=path.name) for r in batch)
            sources.append({'file': path.name, 'rows': len(batch),
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len(rows) == 471, f'Unexpected source count: {len(rows)}'
    assert len({r['id'] for r in rows}) == len(rows)
    kept, removed, seen = [], [], {}
    inputs = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in KEY)
        inputs[tuple(row[k] for k in INPUTS)].append(row)
        if key in seen:
            representative = seen[key]
            removed.append(dict(row, retained_id=representative['id'],
                                retained_year=representative['year'],
                                retained_source_file=representative['source_file']))
        else:
            seen[key] = row
            kept.append(row)
    conflicts = []
    for group in inputs.values():
        if len({r['EFSA'] for r in group}) > 1:
            conflicts.append({'ids': [r['id'] for r in group],
                              'labels': [r['EFSA'] for r in group]})
    assert len(kept) + len(removed) == len(rows)
    assert len({tuple(r[k] for k in KEY) for r in kept}) == len(kept)
    OUT.mkdir(parents=True, exist_ok=True)
    def write(name, records, fields):
        with (OUT / name).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    fields = [*columns, 'source_file']
    write('pool_unique.csv', kept, fields)
    write('duplicates_removed.csv', removed,
          [*fields, 'retained_id', 'retained_year', 'retained_source_file'])
    summary = {
        'years': YEARS, 'missing_year': 2020, 'exact_match_fields': KEY,
        'normalization': 'None: case, whitespace, punctuation and parsed cell newlines are preserved.',
        'ignored_metadata': [c for c in columns if c not in KEY],
        'retention_rule': 'First occurrence: ascending year; answerkey before remain; source row order.',
        'original_count': len(rows), 'unique_count': len(kept),
        'removed_count': len(removed),
        'by_year': [{'year': y, 'original': sum(r['year'] == str(y) for r in rows),
                     'retained': sum(r['year'] == str(y) for r in kept),
                     'removed': sum(r['year'] == str(y) for r in removed)} for y in YEARS],
        'retained_labels': dict(Counter(r['EFSA'] for r in kept)),
        'same_input_different_label_groups': conflicts,
        'sources': sources,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    for source in sources:
        assert hashlib.sha256((ROOT / 'data' / source['file']).read_bytes()).hexdigest() == source['sha256']
    print(json.dumps({k: v for k, v in summary.items() if k not in ('sources', 'ignored_metadata')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
