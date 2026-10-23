import hashlib
import itertools
import json
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .data import inputs

CONDITIONS = ('E0', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7')
RANDOM = ('E1', 'E2', 'E3', 'E4', 'E6')
TAG_TYPES = {'compound', 'scope', 'expression', 'application', 'status'}
GROUPS = tuple(itertools.product(('Enforcement', 'Risk assessment'),
                                 ('Plant products', 'Animal products')))


class Selector:
    """All conditions use a single ordered example set per year/condition/seed."""
    def __init__(self, pools, tests=None, annotations=None):
        self.pools = pools
        self.tests = {y: [inputs(r) for r in rows] for y, rows in (tests or {}).items()}
        self.annotations = annotations or {}
        self.cache = {}
        self.audit = {}

    def pool(self, year):
        if year not in self.pools:
            raise ValueError(f'Missing labeled candidate pool for calendar year {year}')
        return self.pools[year]

    def choose(self, condition, year, seed, test):
        if condition not in CONDITIONS:
            raise ValueError(f'Unknown condition {condition}')
        if condition == 'E0':
            return []
        cache_key = (condition, year, seed if condition in RANDOM else None)
        if cache_key in self.cache:
            return [dict(r) for r in self.cache[cache_key]]
        def tagged(y, rows):
            assert y < year
            return [dict(r, year=str(y)) for r in rows]
        digest = hashlib.sha256(f'{year}:{condition}:{seed}'.encode()).digest()
        rng = random.Random(int.from_bytes(digest, 'big'))
        def sample(y, count, label=None):
            pool = [r for r in self.pool(y) if label is None or r['EFSA'] == label]
            if len(pool) < count:
                raise ValueError(f'{y}: need {count} {label or "any"} examples, found {len(pool)}')
            return tagged(y, rng.sample(pool, count))
        if condition == 'E7':
            from .e7_examples import VERSION, select
            result = tagged(year - 1, select(self.pool(year - 1), year))
            self.audit[f'{year}:E7'] = {
                'method': 'frozen manual error-informed examples', 'version': VERSION,
                'candidate_year': year - 1, 'order': ['N1', 'Y1', 'N2', 'Y2'],
                'selected': [{'id': r['id'], 'role': r['role'], 'label': r['EFSA'],
                              'reason': r['selection_reason']} for r in result],
            }
        elif condition == 'E1':
            result = sample(year - 1, 4)
        elif condition in ('E2', 'E3'):
            y = year - (1 if condition == 'E2' else 2)
            result = sample(y, 2, 'Yes') + sample(y, 2, 'No')
        elif condition == 'E4':
            result = [r for y in (year - 1, year - 2) for label in ('Yes', 'No') for r in sample(y, 1, label)]
        elif condition == 'E5':
            y = year - 1
            pool = self.pool(y)
            if len(pool) < 4:
                raise ValueError(f'{y}: fewer than 4 candidates')
            if not self.tests.get(year):
                raise ValueError(f'{year}: full unlabeled test inputs required for global similarity')
            vectorizer = TfidfVectorizer()
            matrix = vectorizer.fit_transform([self.text(r) for r in pool])
            queries = vectorizer.transform([self.text(r) for r in self.tests[year]])
            scores = cosine_similarity(queries, matrix).mean(axis=0)
            order = sorted(range(len(pool)), key=lambda i: (-scores[i], pool[i]['id']))
            result = [dict(r, similarity=float(scores[i])) for i in order[:4] for r in tagged(y, [pool[i]])]
            self.audit[f'{year}:E5'] = {
                'method': 'mean cosine similarity over all unlabeled test inputs',
                'n_queries': len(self.tests[year]), 'candidate_year': y,
                'ranking': [{'id': pool[i]['id'], 'mean_similarity': float(scores[i])} for i in order]}
        else:
            result = tagged(year - 1, self.priority(year, seed, rng))
        if condition in RANDOM:
            rng.shuffle(result)
        self.cache[cache_key] = result
        return [dict(r) for r in result]

    def priority(self, year, seed, rng):
        pool = self.pool(year - 1)
        missing = [r['id'] for r in pool if r['id'] not in self.annotations]
        if missing:
            raise ValueError(f'{year - 1}: priority annotations missing for {len(missing)} candidates')
        for row in pool:
            a = self.annotations[row['id']]
            if (not isinstance(a, dict) or not isinstance(a.get('tags'), list)
                    or not a['tags'] or not set(a['tags']) <= TAG_TYPES
                    or not isinstance(a.get('features'), list) or not a['features']
                    or any(not isinstance(f, str) or not f.strip() for f in a['features'])
                    or not isinstance(a.get('reason'), str) or not a['reason'].strip()
                    or type(a.get('complexity')) is not int or not 0 <= a['complexity'] <= 3):
                raise ValueError(f"Invalid priority annotation: {row['id']}")
        groups = [[r for r in pool if (r['purpose'], r['commodity']) == g] for g in GROUPS]
        if any(not g for g in groups):
            raise ValueError(f'{year - 1}: priority selection requires all four purpose/commodity groups')
        best, chosen, ties = None, None, 0
        for rows in itertools.product(*groups):
            aa = [self.annotations[r['id']] for r in rows]
            features = set().union(*(set(a['features']) for a in aa))
            # Lexicographic priorities, not an arbitrarily weighted sum.
            objective = (len(set().union(*(set(a['tags']) for a in aa))), len(features),
                         len({r['substance'].casefold() for r in rows}),
                         -(sum(len(set(a['features'])) for a in aa) - len(features)),
                         -sum(a['complexity'] for a in aa),
                         -sum(len(r['JMPR']) + len(r['EU']) for r in rows))
            if best is None or objective > best:
                best, chosen, ties = objective, rows, 1
            elif objective == best:
                ties += 1
                if rng.randrange(ties) == 0:
                    chosen = rows
        self.audit[f'{year}:E6:{seed}'] = {
            'candidate_year': year - 1, 'objective': list(best), 'tied_sets': ties,
            'objective_order': ['tag_coverage', 'feature_coverage', 'distinct_substances',
                                'negative_repeated_features', 'negative_complexity', 'negative_text_length'],
            'selected': [{'id': r['id'], **self.annotations[r['id']]} for r in chosen]}
        return list(chosen)

    @staticmethod
    def text(row):
        return json.dumps(inputs(row), ensure_ascii=False, sort_keys=True)
