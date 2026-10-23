import copy
import json
import sqlite3
import unittest
import tempfile
from pathlib import Path
from residue_experiment.zero_shot_repeats import ROOT, prepare, aggregate


def save(path, rows):
    path.mkdir(parents=True)
    with sqlite3.connect(path / 'checkpoint.sqlite') as db:
        db.execute('create table cases (payload text)')
        db.executemany('insert into cases values (?)', [(json.dumps(r),) for r in rows])


class RepeatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'results', ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_baseline_and_settings(self):
        config, rows = prepare(ROOT / 'results/claude-opus-5.5__baseline__2023-2025')
        assert len(rows) == 210
        assert config['conditions'] == ['E0']
        assert config['years'] == [2023, 2024, 2025]
        assert config['models'] == {'anthropic': 'anthropic/claude-opus-5.5'}
        assert 'model_env' not in config
        assert config['max_output_tokens'] == 1000


    def test_partial_and_error_frequency(self):
        tmp_path = self.folder
        _, baseline = prepare(ROOT / 'results/claude-opus-5.5__baseline__2023-2025')
        # Choose baseline errors so controlled repeats yield exactly 3/3 and 2/3.
        wrong = [r for r in baseline.values() if r['prediction'] != r['actual']]
        core, secondary = wrong[0]['id'], wrong[1]['id']
        r2 = copy.deepcopy(list(baseline.values()))
        r3 = copy.deepcopy(r2)
        for r in r3:
            if r['id'] == secondary:
                r['prediction'] = r['actual']
        save(tmp_path / 'live/round_2', r2)
        partial = aggregate(baseline, tmp_path)
        assert sum(r['incomplete'] for r in partial) == 210
        assert sum(r['core'] for r in partial) == 0
        save(tmp_path / 'live/round_3', r3)
        full = aggregate(baseline, tmp_path)
        assert sum(r['complete'] for r in full) == 210
        import csv
        p = tmp_path / 'analysis'
        with (p / 'all_210_error_frequency.csv').open(encoding='utf-8-sig') as handle:
            rows = {r['id']: r for r in csv.DictReader(handle)}
        assert rows[core]['analysis_group'] == '핵심 분석'
        assert rows[secondary]['analysis_group'] == '보조 분석'


    def test_reject_mixed_prompts(self):
        tmp_path = self.folder
        _, baseline = prepare(ROOT / 'results/claude-opus-5.5__baseline__2023-2025')
        row = copy.deepcopy(next(iter(baseline.values())))
        row['prompt'] = 'changed'
        save(tmp_path / 'live/round_2', [row])
        with self.assertRaisesRegex(ValueError, 'prompt'):
            aggregate(baseline, tmp_path)
