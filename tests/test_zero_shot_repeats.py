import copy
import csv
import json
import sqlite3
import unittest
import tempfile
import shutil
from contextlib import closing
from pathlib import Path
from residue_experiment.zero_shot_repeats import ROOT, prepare, aggregate, read_cases
from residue_experiment.runner import run


def save(path, rows):
    path.mkdir(parents=True)
    with closing(sqlite3.connect(path / 'checkpoint.sqlite')) as db, db:
        db.execute('create table cases (payload text)')
        db.executemany('insert into cases values (?)', [(json.dumps(r),) for r in rows])


class RepeatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='residue-tests-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def csv_baseline(self):
        source = ROOT / 'results/baseline/gpt-6-sol/2023-2025'
        for name in ('manifest.json', 'predictions.csv'):
            shutil.copyfile(source / name, self.folder / name)
        manifest_path = self.folder / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['config']['data_dir'] = '/another/computer/missing-data'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        return self.folder

    def test_gpt_csv_baseline_and_local_data(self):
        config, rows = prepare(self.csv_baseline())
        self.assertEqual(len(rows), 210)
        self.assertEqual(config['models'], {'openai': 'openai/gpt-6-sol'})
        self.assertEqual(Path(config['data_dir']), ROOT / 'data')
        self.assertTrue(all(row['seed'] is None for row in rows.values()))
        self.assertFalse((self.folder / 'checkpoint.sqlite').exists())

    def test_reject_modified_csv_prompt_hash(self):
        baseline = self.csv_baseline()
        path = baseline / 'predictions.csv'
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        rows[0]['prompt_sha256'] = 'tampered'
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with self.assertRaisesRegex(ValueError, 'prompt hash'):
            prepare(baseline)

    def test_aggregate_repeat_csv_without_checkpoint(self):
        source = self.csv_baseline()
        _, baseline = prepare(source)
        output = self.folder / 'repeats'
        for number in (2, 3):
            dest = output / 'live' / f'round-{number:02d}'
            dest.mkdir(parents=True)
            shutil.copyfile(source / 'predictions.csv', dest / 'predictions.csv')
        summary = aggregate(baseline, output)
        self.assertEqual(sum(row['complete'] for row in summary), 210)

    def test_gpt_plan_preserves_original_prompt_hashes(self):
        config, baseline = prepare(self.csv_baseline())
        output = self.folder / 'plan'
        run(config, output, 'dry-run')
        rows = read_cases(output)
        self.assertEqual(len(rows), 210)
        for row in rows:
            self.assertEqual(row['prompt'], baseline[row['id']]['prompt'])
            self.assertEqual(row['prompt_sha256'], baseline[row['id']]['prompt_sha256'])

    def test_baseline_and_settings(self):
        config, rows = prepare(ROOT / 'results/baseline/claude-opus-5.5/2023-2025')
        assert len(rows) == 210
        assert config['conditions'] == ['E0']
        assert config['years'] == [2023, 2024, 2025]
        assert config['models'] == {'anthropic': 'anthropic/claude-opus-5.5'}
        assert 'model_env' not in config
        assert config['max_output_tokens'] == 1000


    def test_partial_and_error_frequency(self):
        tmp_path = self.folder
        _, baseline = prepare(ROOT / 'results/baseline/claude-opus-5.5/2023-2025')
        # Choose baseline errors so controlled repeats yield exactly 3/3 and 2/3.
        wrong = [r for r in baseline.values() if r['prediction'] != r['actual']]
        core, secondary = wrong[0]['id'], wrong[1]['id']
        r2 = copy.deepcopy(list(baseline.values()))
        r3 = copy.deepcopy(r2)
        for r in r3:
            if r['id'] == secondary:
                r['prediction'] = r['actual']
        save(tmp_path / 'live/round-02', r2)
        partial = aggregate(baseline, tmp_path)
        assert sum(r['incomplete'] for r in partial) == 210
        assert sum(r['core'] for r in partial) == 0
        save(tmp_path / 'live/round-03', r3)
        full = aggregate(baseline, tmp_path)
        assert sum(r['complete'] for r in full) == 210
        p = tmp_path / 'analysis'
        with (p / 'all_210_error_frequency.csv').open(encoding='utf-8-sig') as handle:
            rows = {r['id']: r for r in csv.DictReader(handle)}
        assert rows[core]['analysis_group'] == '핵심 분석'
        assert rows[secondary]['analysis_group'] == '보조 분석'


    def test_reject_mixed_prompts(self):
        tmp_path = self.folder
        _, baseline = prepare(ROOT / 'results/baseline/claude-opus-5.5/2023-2025')
        row = copy.deepcopy(next(iter(baseline.values())))
        row['prompt'] = 'changed'
        save(tmp_path / 'live/round-02', [row])
        with self.assertRaisesRegex(ValueError, 'prompt'):
            aggregate(baseline, tmp_path)
