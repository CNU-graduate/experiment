import hashlib
import json
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .data import FIELDS, inputs

CONDITIONS = ('E0', 'E1', 'E2', 'E3', 'E4', 'E5')
RANDOM = ('E1', 'E2', 'E3', 'E4')


class Selector:
    """Random exemplars fixed per year/condition/seed; E5 varies per test."""
    def __init__(self, pools):
        self.pools = pools
        self.cache = {}

    def pool(self, year):
        if year not in self.pools:
            raise ValueError(f'Missing labeled candidate pool for calendar year {year}')
        return self.pools[year]

    def choose(self, condition, year, seed, test):
        if condition not in CONDITIONS:
            raise ValueError(f'Unknown condition {condition}')
        if condition == 'E0':
            return []
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
        if condition == 'E1':
            result = sample(year - 1, 4)
        elif condition in ('E2', 'E3'):
            y = year - (1 if condition == 'E2' else 2)
            result = sample(y, 2, 'Yes') + sample(y, 2, 'No')
        elif condition == 'E4':
            result = [r for y in (year - 1, year - 2) for label in ('Yes', 'No') for r in sample(y, 1, label)]
        else:
            y = year - 1
            pool = self.pool(y)
            if len(pool) < 4:
                raise ValueError(f'{y}: fewer than 4 candidates')
            if y not in self.cache:
                vectorizer = TfidfVectorizer()
                matrix = vectorizer.fit_transform([self.text(r) for r in pool])
                self.cache[y] = vectorizer, matrix
            vectorizer, matrix = self.cache[y]
            scores = cosine_similarity(vectorizer.transform([self.text(test)]), matrix)[0]
            order = sorted(range(len(pool)), key=lambda i: (-scores[i], pool[i]['id']))[:4]
            return [dict(r, similarity=float(scores[i])) for i in order for r in tagged(y, [pool[i]])]
        rng.shuffle(result)
        return result

    @staticmethod
    def text(row):
        return json.dumps(inputs(row), ensure_ascii=False, sort_keys=True)
