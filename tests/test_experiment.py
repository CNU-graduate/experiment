import csv
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from residue_experiment.data import Dataset, FIELDS
from residue_experiment.selection import Selector
from residue_experiment.prompt import build_prompt, parse_label
from residue_experiment.evaluation import score
from residue_experiment.runner import run
from residue_experiment.providers import Provider

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('status,fatal', [(400,True),(401,True),(402,True),(403,True),(404,True),(408,False),(409,False),(429,False),(500,False),(503,False)])
def test_http_error_policy(status, fatal):
    from residue_experiment.runner import error_policy
    exc = RuntimeError('SECRET_DO_NOT_LOG')
    exc.status_code = status
    assert error_policy(exc) == (status, fatal)


def test_credit_error_stops_and_exports(config, tmp_path, monkeypatch):
    config.update(conditions=['E0'], models={'openai':'test'})
    exc = RuntimeError('SECRET_DO_NOT_LOG')
    exc.status_code = 402
    client = MagicMock()
    client.call.side_effect = exc
    monkeypatch.setattr('residue_experiment.runner.Provider', lambda *args: client)
    with pytest.raises(ValueError, match='HTTP 402'):
        run(config, tmp_path, 'live', approved=True)
    assert client.call.call_count == 1
    rows = list(csv.DictReader((tmp_path/'predictions.csv').open(encoding='utf-8-sig')))
    assert len(rows) == 70
    assert sum(r['status'] == 'pending' for r in rows) == 69
    errors = (tmp_path/'api_errors.csv').read_text(encoding='utf-8-sig')
    assert '402' in errors and 'SECRET_DO_NOT_LOG' not in errors


@pytest.fixture
def data():
    return Dataset(ROOT)


@pytest.fixture
def config():
    c = json.loads((ROOT/'config.json').read_text())
    c.update(data_dir=str(ROOT), years=[2025], seeds=[7, 11], max_attempts=2, retry_delay_seconds=0)
    return c


def test_real_csv_integrity(data):
    assert len(data.files) == 21
    assert sum(len(t) for t in data.tests.values()) == 490
    assert data.issues == []
    assert {y: len(p) for y,p in data.pools.items()} == {2018:109,2019:107,2021:141,2022:114,2023:90,2024:86,2025:82}


@pytest.mark.parametrize('condition', ['E0','E1','E2','E3','E4','E5'])
def test_selection_constraints(data, condition):
    selector = Selector(data.pools)
    test = data.tests[2025][0]
    rows = selector.choose(condition, 2025, 42, test)
    assert rows == selector.choose(condition, 2025, 42, test)
    assert len(rows) == (0 if condition == 'E0' else 4)
    assert len({r['id'] for r in rows}) == len(rows)
    assert all(int(r['year']) < 2025 for r in rows)
    assert all(r['EFSA'] in ('Yes','No') for r in rows)
    if condition in ('E2','E3','E4'):
        assert sum(r['EFSA']=='Yes' for r in rows) == 2
    if condition == 'E3':
        assert {r['year'] for r in rows} == {'2023'}
    elif condition == 'E4':
        assert sorted((r['year'],r['EFSA']) for r in rows) == [('2023','No'),('2023','Yes'),('2024','No'),('2024','Yes')]
    elif condition != 'E0':
        assert {r['year'] for r in rows} == {'2024'}


def test_random_examples_fixed_across_tests(data):
    s = Selector(data.pools)
    for c in ('E1','E2','E3','E4'):
        assert s.choose(c,2025,42,data.tests[2025][0]) == s.choose(c,2025,42,data.tests[2025][-1])
        assert s.choose(c,2025,42,data.tests[2025][0]) != s.choose(c,2025,123,data.tests[2025][0])


def test_similarity_ignores_labels_and_metadata(data):
    a = Selector(data.pools)
    changed = {y: [dict(r, EFSA='No' if r['EFSA']=='Yes' else 'Yes', efsa_comments='LEAK') for r in p] for y,p in data.pools.items()}
    b = Selector(changed)
    t = data.tests[2025][0]
    aa = a.choose('E5',2025,None,t)
    bb = b.choose('E5',2025,None,dict(t,EFSA='No',source_url='LEAK'))
    assert [(r['id'],r['similarity']) for r in aa] == [(r['id'],r['similarity']) for r in bb]


def test_similarity_ranking_and_tie_break():
    pool = [dict.fromkeys(FIELDS,'apple') | {'id':str(i),'EFSA':'Yes','year':'2024'} for i in range(5)]
    pool[-1] = dict.fromkeys(FIELDS,'zebra') | {'id':'4','EFSA':'No','year':'2024'}
    s = Selector({2024:pool})
    assert [r['id'] for r in s.choose('E5',2025,None,dict.fromkeys(FIELDS,'zebra'))] == ['4','0','1','2']


def test_prompt_allowlist(data):
    examples = Selector(data.pools).choose('E2',2025,7,data.tests[2025][0])
    p = json.loads(build_prompt(data.tests[2025][0],examples))
    assert set(p['test']) == set(FIELDS)
    assert all(set(r) == set(FIELDS)|{'EFSA'} for r in p['examples'])
    for k in ('id','year','EFSA','efsa_comments','source_url','source_table'):
        assert k not in p['test']


def test_missing_and_insufficient_pools(data):
    s = Selector(data.pools)
    with pytest.raises(ValueError, match='2020'):
        s.choose('E2',2021,42,data.tests[2021][0])
    tiny = {2024:[r for r in data.pools[2024] if r['EFSA']=='Yes']}
    with pytest.raises(ValueError, match='found 0'):
        Selector(tiny).choose('E2',2025,42,data.tests[2025][0])


def test_metrics_known_values():
    m = score(['Yes','Yes','No','No'],['Yes','No','No','No'])
    assert m['accuracy'] == .75
    assert m['precision'] == 1
    assert m['recall'] == .5
    assert m['macro_f1'] == pytest.approx((2/3+.8)/2)
    assert (m['tn'],m['fp'],m['fn'],m['tp']) == (2,0,1,1)


@pytest.mark.parametrize('raw',['YES','Yes.','Maybe','Yes because...',''])
def test_invalid_response(raw):
    with pytest.raises(ValueError): parse_label(raw)


def test_mock_resume_and_same_examples(config,tmp_path,monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a: pytest.fail('SDK constructed'))
    config['conditions']=['E2']
    a=run(config,tmp_path,'mock')
    b=run(config,tmp_path,'mock')
    assert a == b == {'cases':420,'calls':420}
    rows=list(csv.DictReader((tmp_path/'examples.csv').open(encoding='utf-8-sig')))
    for seed in ('7','11'):
        sets={tuple((r['example_id'],r['example_year']) for r in rows if r['seed']==seed and r['provider']==p and r['id']==rows[0]['id']) for p in config['models']}
        assert len(sets)==1
    with pytest.raises(ValueError,match='different config'):
        run(dict(config,seeds=[99]),tmp_path,'mock')


def test_dry_run_no_calls(config,tmp_path,monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a: pytest.fail('SDK constructed'))
    monkeypatch.setattr('residue_experiment.runner.mock_call',lambda *a: pytest.fail('mock called'))
    config['conditions']=['E0']
    assert run(config,tmp_path) == {'cases':210,'calls':0}
    assert set(r['prediction'] for r in csv.DictReader((tmp_path/'predictions.csv').open(encoding='utf-8-sig'))) == {''}


def test_live_guard(config,tmp_path,monkeypatch):
    monkeypatch.setattr('residue_experiment.runner.Provider',lambda *a: pytest.fail('SDK constructed'))
    with pytest.raises(ValueError,match='approval'):run(config,tmp_path,'live')
    assert not tmp_path.joinpath('checkpoint.sqlite').exists()


def test_error_logging_retry_and_resume(config,tmp_path,monkeypatch):
    config.update(conditions=['E0'],models={'openai':''})
    def fail(*a): raise RuntimeError('SECRET_DO_NOT_LOG')
    monkeypatch.setattr('residue_experiment.runner.mock_call',fail)
    assert run(config,tmp_path,'mock') == {'cases':70,'calls':140}
    assert 'SECRET_DO_NOT_LOG' not in (tmp_path/'api_errors.csv').read_text()
    monkeypatch.setattr('residue_experiment.runner.mock_call',lambda *a: ('Yes',{},'recovered'))
    assert run(config,tmp_path,'mock') == {'cases':70,'calls':210}
    assert run(config,tmp_path,'mock')['calls'] == 210


def test_interrupt_export_and_resume(config,tmp_path,monkeypatch):
    config.update(conditions=['E0'],models={'openai':''})
    count=0
    def interrupt(*a):
        nonlocal count
        count+=1
        if count==3:raise KeyboardInterrupt()
        return 'Yes',{},'test'
    monkeypatch.setattr('residue_experiment.runner.mock_call',interrupt)
    with pytest.raises(KeyboardInterrupt):run(config,tmp_path,'mock')
    rows=list(csv.DictReader((tmp_path/'predictions.csv').open(encoding='utf-8-sig')))
    assert len(rows)==70
    assert sum(r['status']=='success' for r in rows)==2
    monkeypatch.setattr('residue_experiment.runner.mock_call',lambda *a: ('No',{},'resumed'))
    assert run(config,tmp_path,'mock')=={'cases':70,'calls':71}


def test_data_conflict_and_invalid_label(tmp_path):
    for name in ('ESFA_202570.csv','ESFA_202570answerkey.csv','ESFA_2025_remain.csv'):
        (tmp_path/name).write_bytes((ROOT/name).read_bytes())
    p=tmp_path/'ESFA_202570answerkey.csv'
    with p.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows[0]['EFSA'] = 'Maybe'
    with p.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError,match='invalid EFSA'):Dataset(tmp_path)


@pytest.mark.parametrize('provider',['openai','anthropic','gemini'])
def test_official_adapter_requests(provider,monkeypatch):
    # SDK network calls are stubbed; adapters themselves execute normally.
    config=json.loads((ROOT/'config.json').read_text())
    from residue_experiment.providers import KEYS
    monkeypatch.setenv(KEYS[provider],'dummy-unit-test')
    if provider=='openai':
        import openai
        factory=MagicMock()
        monkeypatch.setattr(openai,'OpenAI',factory)
        factory.return_value.responses.create.return_value=SimpleNamespace(output_text='Yes',usage=None,id='test')
    elif provider=='anthropic':
        import anthropic
        factory=MagicMock()
        monkeypatch.setattr(anthropic,'Anthropic',factory)
        factory.return_value.messages.create.return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='Yes')],usage=MagicMock(model_dump=lambda:{}),id='test')
    else:
        from google import genai
        factory=MagicMock()
        monkeypatch.setattr(genai,'Client',factory)
        factory.return_value.models.generate_content.return_value=SimpleNamespace(text='Yes',usage_metadata=None,response_id='test')
    client=Provider(provider,'test-model',config)
    assert client.call('safe-input')[0]=='Yes'
    if provider=='openai':
        assert factory.return_value.responses.create.call_args.kwargs['input']=='safe-input'
    elif provider=='anthropic':
        assert factory.return_value.messages.create.call_args.kwargs['messages'][0]['content']=='safe-input'
    else:
        assert factory.return_value.models.generate_content.call_args.kwargs['contents']=='safe-input'


def test_pool_overlap_dedup_and_conflict(tmp_path):
    for name in ('ESFA_202570.csv','ESFA_202570answerkey.csv','ESFA_2025_remain.csv'):
        (tmp_path/name).write_bytes((ROOT/name).read_bytes())
    key=tmp_path/'ESFA_202570answerkey.csv'
    with key.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        fields,rows=reader.fieldnames,list(reader)
    remain=tmp_path/'ESFA_2025_remain.csv'
    with remain.open('a',encoding='utf-8',newline='') as f:
        csv.DictWriter(f,fieldnames=fields).writerow(rows[0])
    d=Dataset(tmp_path)
    assert len(d.pools[2025])==82
    assert d.issues[0]['type']=='pool_overlap_removed'
    rows[0]['EFSA']='No' if rows[0]['EFSA']=='Yes' else 'Yes'
    with remain.open('a',encoding='utf-8',newline='') as f:
        csv.DictWriter(f,fieldnames=fields).writerow(rows[0])
    with pytest.raises(ValueError,match='conflicting duplicate'):Dataset(tmp_path)


def test_test_answerkey_mismatch(tmp_path):
    for name in ('ESFA_202570.csv','ESFA_202570answerkey.csv','ESFA_2025_remain.csv'):
        (tmp_path/name).write_bytes((ROOT/name).read_bytes())
    p=tmp_path/'ESFA_202570.csv'
    with p.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        fields,rows=reader.fieldnames,list(reader)
    rows[0]['JMPR']='changed only in test'
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='input mismatch'):Dataset(tmp_path)


def test_exclusion_and_complete_only_summary(config,tmp_path):
    config.update(years=[2021],conditions=['E2'],models={'openai':''})
    assert run(config,tmp_path,'mock')=={'cases':140,'calls':0}
    rows=list(csv.DictReader((tmp_path/'comparison.csv').open(encoding='utf-8-sig')))
    assert rows[0]['repeats_complete']=='0'
    assert rows[0]['accuracy_mean']==''


def test_missing_keys_fail_without_calls(config,tmp_path,monkeypatch):
    from residue_experiment.providers import KEYS
    for key in KEYS.values():monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr('dotenv.load_dotenv',lambda **kw:False)
    with pytest.raises(ValueError,match='API key'):run(config,tmp_path,'live',approved=True)
    with sqlite3.connect(tmp_path/'checkpoint.sqlite') as db:
        assert db.execute('SELECT COUNT(*) FROM calls').fetchone()[0]==0


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'gemini'])
def test_openrouter_adapter(provider, monkeypatch):
    import openai
    config = json.loads((ROOT/'config.openrouter.json').read_text())
    monkeypatch.setenv('OPENROUTER_API_KEY', 'dummy-unit-test')
    factory = MagicMock()
    monkeypatch.setattr(openai, 'OpenAI', factory)
    factory.return_value.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='Yes'))],
        usage=SimpleNamespace(model_dump=lambda: {'prompt_tokens': 10, 'completion_tokens': 1}),
        id='router-test')
    client = Provider(provider, 'vendor/model', config)
    assert client.call('input') == ('Yes', {'prompt_tokens': 10, 'completion_tokens': 1}, 'router-test')
    assert factory.call_args.kwargs['base_url'] == 'https://openrouter.ai/api/v1'
    assert factory.call_args.kwargs['max_retries'] == 0
    request = factory.return_value.chat.completions.create.call_args.kwargs
    assert request['model'] == 'vendor/model'
    assert request['messages'][0]['role'] == 'system'
    assert request['messages'][1]['content'] == 'input'
    assert request['max_tokens'] == 1000


def test_invalid_backend(config):
    from residue_experiment.cli import validate_config
    with pytest.raises(ValueError, match='api_backend'):
        validate_config(dict(config, api_backend='invalid'))


def test_cli_openrouter_env_resolution(tmp_path, monkeypatch):
    from residue_experiment import cli
    config = json.loads((ROOT/'config.openrouter.json').read_text())
    config['data_dir'] = str(ROOT)
    path = tmp_path/'config.json'
    path.write_text(json.dumps(config))
    (tmp_path/'.env').write_text('GPT_MODEL=openai/test\nCLAUDE_MODEL=anthropic/test\nGEMINI_MODEL=google/test\n')
    for name in ('GPT_MODEL','CLAUDE_MODEL','GEMINI_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr('sys.argv', ['residue-experiment','--config',str(path)])
    captured = {}
    def fake_run(c, *args):
        captured.update(c)
        return {'calls': 0}
    monkeypatch.setattr(cli, 'run', fake_run)
    cli.main()
    assert captured['models'] == {'openai':'openai/test','anthropic':'anthropic/test','gemini':'google/test'}
