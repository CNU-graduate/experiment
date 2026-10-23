import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from residue_experiment.data import Dataset, inputs
from residue_experiment.e7_examples import SELECTION, select
from residue_experiment.e7_repeats import ROOT, execute
from residue_experiment.selection import Selector


class E7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Dataset(ROOT / 'data')

    def test_frozen_selection_ignores_seed_test_and_pool_order(self):
        selector = Selector(self.data.pools, self.data.tests)
        for year, specification in SELECTION.items():
            rows = selector.choose('E7', year, 42, {})
            self.assertEqual([r['id'] for r in rows], [s[1] for s in specification])
            self.assertEqual([r['EFSA'] for r in rows], ['No', 'Yes', 'No', 'Yes'])
            self.assertEqual([r['role'] for r in rows], ['N1', 'Y1', 'N2', 'Y2'])
            self.assertEqual(rows, selector.choose('E7', year, 999, {'EFSA': 'LEAK'}))
            reversed_selector = Selector({year - 1: list(reversed(self.data.pools[year - 1]))})
            self.assertEqual(rows, reversed_selector.choose('E7', year, None, {}))
            self.assertTrue(all(int(r['year']) == year - 1 for r in rows))

    def test_bad_candidates_fail_without_fallback(self):
        pool = self.data.pools[2022]
        ident = SELECTION[2023][0][1]
        for altered in (
            [r for r in pool if r['id'] != ident],
            pool + [next(r for r in pool if r['id'] == ident)],
            [dict(r, EFSA='Yes') if r['id'] == ident else r for r in pool],
            [dict(r, year='2021') if r['id'] == ident else r for r in pool],
        ):
            with self.assertRaises(ValueError):
                select(altered, 2023)
        with self.assertRaises(ValueError):
            select(pool, 2026)

    def test_three_round_plan_no_provider_and_exact_raw_prompts(self):
        config = json.loads((ROOT / 'config.openrouter.e7.json').read_text(encoding='utf-8'))
        config['data_dir'] = str(ROOT / 'data')
        with tempfile.TemporaryDirectory(prefix='residue-e7-tests-') as temp, patch(
                'residue_experiment.runner.Provider', side_effect=AssertionError('No API allowed')):
            output = Path(temp)
            result = execute(config, output)
            self.assertEqual((result['total_cases'], result['calls']), (630, 0))
            previous = None
            for number in (1, 2, 3):
                with closing(sqlite3.connect(output / 'dry-run' / f'round-{number:02d}' / 'checkpoint.sqlite')) as db:
                    rows = [json.loads(s) for s, in db.execute('SELECT payload FROM cases')]
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM calls').fetchone()[0], 0)
                prompts = {r['id']: r['prompt'] for r in rows}
                if previous is not None:
                    self.assertEqual(prompts, previous)
                previous = prompts
                for row in rows:
                    self.assertEqual(row['status'], 'planned')
                    self.assertIsNone(row['seed'])
                    payload = json.loads(row['prompt'])
                    expected = select(self.data.pools[row['year'] - 1], row['year'])
                    self.assertEqual(payload['examples'], [dict(inputs(r), EFSA=r['EFSA']) for r in expected])
                    self.assertEqual(set(payload['test']), set(inputs(expected[0])))
            self.assertEqual(execute(config, output)['calls'], 0)  # Resume is idempotent.
            changed = copy.deepcopy(config)
            changed['models']['anthropic'] = 'different-model'
            with self.assertRaises(ValueError):
                execute(changed, output)

    def test_live_requires_explicit_approval(self):
        with patch('residue_experiment.e7_repeats.prepare', side_effect=AssertionError('No work allowed')):
            with self.assertRaisesRegex(ValueError, 'approve-paid-api'):
                execute({}, Path('unused'), 'live')


if __name__ == '__main__':
    unittest.main()
