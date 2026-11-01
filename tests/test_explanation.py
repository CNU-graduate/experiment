import csv
import json
from pathlib import Path
import pytest
from residue_experiment.explanation import EXPLANATION_SYSTEM, OUTPUT_RULE, parse_explanation
from residue_experiment.explanation_2023 import prepare
from residue_experiment.prompt import SYSTEM, parse_label
from residue_experiment.runner import run

ROOT = Path(__file__).resolve().parents[1]


def test_prompt_changes_only_output_instruction():
    assert EXPLANATION_SYSTEM.startswith(SYSTEM.removesuffix(OUTPUT_RULE))
    assert OUTPUT_RULE not in EXPLANATION_SYSTEM
    with pytest.raises(ValueError):
        parse_label('Evidence\nFinal label: Yes')


@pytest.mark.parametrize('text', ['Yes', 'Final label: Yes',
    'Evidence\nFinal label: Yes\nextra', 'Final label: No\nEvidence\nFinal label: Yes'])
def test_invalid_explanation(text):
    with pytest.raises(ValueError):
        parse_explanation(text)


def test_2023_saved_explanation_and_resume(tmp_path, monkeypatch):
    config = json.loads((ROOT / 'config.explanation-2023.gpt.json').read_text())
    config.update(data_dir=str(ROOT / 'data'), years=[2024, 2025])
    config = prepare(config)
    assert config['years'] == [2023]
    seen = []
    class Client:
        def call(self, prompt):
            seen.append(prompt)
            assert json.loads(prompt)['examples'] == []
            assert 'EFSA' not in json.loads(prompt)['test']
            return 'Source evidence and comparison.\nFinal label: No', {}, 'fake'
    monkeypatch.setattr('residue_experiment.runner.Provider', lambda *a, **kw: Client())
    result = run(config, tmp_path, 'live', True, system_prompt=EXPLANATION_SYSTEM)
    assert result == {'cases': 70, 'calls': 70}
    rows = list(csv.DictReader((tmp_path / 'predictions.csv').open(encoding='utf-8-sig')))
    assert all(r['year'] == '2023' and r['provider'] == 'openai' and
               r['prediction'] == 'No' and r['explanation'] == 'Source evidence and comparison.'
               for r in rows)
    run(config, tmp_path, 'live', True, system_prompt=EXPLANATION_SYSTEM)
    assert len(seen) == 70


def test_reject_other_models():
    with pytest.raises(ValueError):
        prepare({'models': {'gemini': 'gemini'}})
