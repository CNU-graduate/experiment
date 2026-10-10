import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

FIELDS = ('substance', 'purpose', 'commodity', 'JMPR', 'EU')
LABELS = ('No', 'Yes')
PATTERN = re.compile(r'ESFA_(\d{4})(70answerkey|70|_remain)\.csv$')


def inputs(row):
    return {field: row[field] for field in FIELDS}


def signature(row):
    return tuple(row[f] for f in FIELDS)


class Dataset:
    def __init__(self, directory):
        self.files, self.tables, self.tests, self.pools = [], {}, {}, {}
        self.issues = []
        for path in sorted(Path(directory).rglob('*.csv')):
            match = PATTERN.fullmatch(path.name)
            if not match:
                continue
            year, kind = int(match[1]), match[2]
            if (year, kind) in self.tables:
                raise ValueError(f'Duplicate dataset file: {path.name}')
            with path.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                columns = reader.fieldnames or []
                required = {'id', 'year', *FIELDS} | ({'EFSA'} if kind != '70' else set())
                if not required.issubset(columns):
                    raise ValueError(f'{path.name}: missing columns {required - set(columns)}')
                rows = list(reader)
            seen, clean = {}, []
            for line, row in enumerate(rows, 2):
                if None in row or any(row.get(f) is None for f in required):
                    raise ValueError(f'{path.name}:{line}: malformed CSV row')
                if not row['id'].strip() or row['year'].strip() != str(year):
                    raise ValueError(f'{path.name}:{line}: invalid id/year')
                if any(not row[f].strip() for f in FIELDS):
                    raise ValueError(f'{path.name}:{line}: empty model input')
                if kind != '70' and row['EFSA'] not in LABELS:
                    raise ValueError(f'{path.name}:{line}: invalid EFSA label')
                if row['id'] in seen:
                    old = seen[row['id']]
                    if signature(old) != signature(row) or old.get('EFSA') != row.get('EFSA'):
                        raise ValueError(f'{path.name}: conflicting duplicate {row["id"]}')
                    self.issues.append({'year': year, 'type': 'duplicate_removed', 'detail': f'{path.name}:{row["id"]}'})
                    if kind == '70':
                        raise ValueError(f'{path.name}: duplicate test id')
                    continue
                seen[row['id']] = row
                clean.append(row)
            counts = Counter(r.get('EFSA', '') for r in rows)
            self.files.append({'file': path.name, 'year': year, 'kind': kind, 'rows': len(rows),
                               'unique_ids': len(clean), 'Yes': counts['Yes'], 'No': counts['No'],
                               'columns': '|'.join(columns), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            self.tables[year, kind] = clean
        if not self.tables:
            raise ValueError('No ESFA year CSV files found')
        for year in sorted({y for y, _ in self.tables}):
            test = self.tables.get((year, '70'))
            key = self.tables.get((year, '70answerkey'))
            remain = self.tables.get((year, '_remain'))
            if test is not None and key is not None:
                answers = {r['id']: r for r in key}
                if {r['id'] for r in test} != set(answers):
                    raise ValueError(f'{year}: test/answerkey id mismatch')
                if len(test) != 70:
                    raise ValueError(f'{year}: expected 70 test rows, found {len(test)}')
                for row in test:
                    if signature(row) != signature(answers[row['id']]):
                        raise ValueError(f'{year}:{row["id"]}: test/answerkey input mismatch')
                self.tests[year] = [dict(r, EFSA=answers[r['id']]['EFSA']) for r in test]
            else:
                self.issues.append({'year': year, 'type': 'missing_test_pair', 'detail': 'test or answerkey absent'})
            if key is None or remain is None:
                self.issues.append({'year': year, 'type': 'missing_pool_file', 'detail': 'answerkey or remain absent'})
                continue
            pool = {}
            for row in key + remain:
                old = pool.get(row['id'])
                if old:
                    if signature(old) != signature(row) or old['EFSA'] != row['EFSA']:
                        raise ValueError(f'{year}: conflicting candidate {row["id"]}')
                    self.issues.append({'year': year, 'type': 'pool_overlap_removed', 'detail': row['id']})
                else:
                    pool[row['id']] = row
            self.pools[year] = sorted(pool.values(), key=lambda r: r['id'])
