"""Read-only v1 audit; no API calls. Exports reproducible descriptive evidence."""
import csv
import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'results/prompt-search-2023'
OUT = ROOT / 'analysis/reports/prompt_search_audit'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    plan = read(SOURCE / 'plan.json')
    live = SOURCE / 'live'
    annotations = {r['id']: r for r in rows(ROOT / 'analysis/reports/compact_10_type_classification/all_729_classified.csv')}
    selection = {r['id']: r for r in plan['selection']}
    test = {r['id']: r for r in plan['test']}
    distributions = {}
    for name in ('development', 'selection', 'test'):
        data = plan[name]
        distributions[name] = {field: dict(Counter(r[field] for r in data))
                               for field in ('year', 'EFSA', 'purpose', 'commodity')}
        distributions[name]['type'] = dict(Counter(annotations.get(r['id'], {}).get('primary_type', 'unknown') for r in data))
    substances = {name: {r['substance'].casefold().strip() for r in plan[name]}
                  for name in ('development', 'selection', 'test')}
    shared_substances = {'development_selection': len(substances['development'] & substances['selection']),
                         'past_test': len((substances['development'] | substances['selection']) & substances['test'])}
    candidates, errors, rounds = [], [], []
    prediction_maps = {}
    best = 'P0'
    for n in range(1, 6):
        folder = live / f'round-{n:02d}'
        chosen = read(folder / 'selection.json')
        generated = read(folder / 'candidates.json')
        batch = {r['id']: r for r in plan['batches'][n - 1]}
        for p in rows(folder / 'development_predictions.csv'):
            if p['prediction'] != p['actual']:
                r = batch[p['id']]
                errors.append({'round': n, 'parent': best, **r, 'prediction': p['prediction'],
                               'type': annotations.get(r['id'], {}).get('primary_type', 'unknown')})
        for i, c in enumerate(chosen['candidates']):
            ps = rows(folder / (c['name'] + '_predictions.csv'))
            assert len(ps) == 140 and {p['id'] for p in ps} == set(selection)
            assert all(p['actual'] == selection[p['id']]['EFSA'] for p in ps)
            correct = sum(p['actual'] == p['prediction'] for p in ps)
            assert abs(correct / 140 - c['metrics']['accuracy']) < 1e-12
            prediction_maps[c['name']] = {p['id']: p for p in ps}
            candidates.append({'round': n, 'parent': best, 'name': c['name'], 'correct': correct,
                               'metrics': c['metrics'], 'chars': len(c['prompt']),
                               'prompt': c['prompt'], 'change': generated['raw']['candidates'][i]['change'],
                               'risk': generated['raw']['candidates'][i]['risk']})
        rounds.append({'round': n, 'parent': best, 'winner': chosen['winner']['name'],
                       'analysis': generated['analysis'], 'winner_metrics': chosen['winner']['metrics']})
        best = chosen['winner']['name']
    comparisons = {}
    for a, b in [('R2C1', 'R4C1'), ('R4C1', 'R5C2')]:
        changes = []
        for ident, first in prediction_maps[a].items():
            second = prediction_maps[b][ident]
            if first['prediction'] != second['prediction']:
                changes.append({**selection[ident], a: first['prediction'], b: second['prediction']})
        comparisons[a + '_to_' + b] = changes
    predictions = rows(live / 'test_predictions.csv')
    assert len(predictions) == 420
    by_condition = defaultdict(list)
    error_cases = []
    for p in predictions:
        assert p['actual'] == test[p['id']]['EFSA']
        by_condition[p['condition']].append(p)
    strata = []
    for field in ('purpose', 'commodity', 'type'):
        get = lambda r: annotations.get(r['id'], {}).get('primary_type', 'unknown') if field == 'type' else r[field]
        for value in sorted({get(r) for r in test.values()}):
            ids = {r['id'] for r in test.values() if get(r) == value}
            counts = {c: sum(p['actual'] == p['prediction'] for p in ps if p['id'] in ids)
                      for c, ps in by_condition.items()}
            strata.append({'field': field, 'value': value, 'unique_items': len(ids),
                           'responses_per_condition': len(ids) * 3, 'correct': counts})
    for ident, r in test.items():
        wrong = {c: sum(p['prediction'] != p['actual'] for p in ps if p['id'] == ident)
                 for c, ps in by_condition.items()}
        if any(wrong.values()):
            error_cases.append({**r, 'wrong': wrong, 'type': annotations.get(ident, {}).get('primary_type', 'unknown')})
    result = {'source': str(SOURCE), 'distributions': distributions, 'shared_substances': shared_substances,
              'development_errors': errors, 'development_error_labels': dict(Counter(r['EFSA'] for r in errors)),
              'candidates': candidates, 'rounds': rounds, 'selection_changes': comparisons,
              'test_metrics': read(live / 'test_summary.json'), 'test_strata': strata, 'test_error_cases': error_cases,
              'call_logs_available': (live / 'calls').exists(),
              'limitations': ['No causal attribution to individual clauses without ablation.',
                             'Candidate validation is one draw, not repeated estimation.',
                             '2023 has already informed follow-up design; subsequent tests are exploratory.',
                             'Existing type annotations are descriptive, not independently revalidated.']}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    esc = lambda v: html.escape(str(v))
    pieces = ['<!doctype html><meta charset="utf-8"><title>Prompt search audit</title>',
              '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;line-height:1.6}pre{white-space:pre-wrap;background:#f3f5f7;padding:16px}td,th{padding:8px;border:1px solid #ddd}table{border-collapse:collapse}</style>',
              '<h1>프롬프트 탐색 v1 전체 감사</h1><p>유료 API 호출 없이 저장된 예측을 대조한 기술 통계입니다. 문장별 오류 인과관계는 확정하지 않습니다.</p>',
              '<p>선택: 124/140 → 131/140. 2023: 194/210 → 188/210 (70문제 × 3회).</p>',
              '<h2>분포 및 유형별 결과</h2><pre>' + esc(json.dumps({'distributions': distributions, 'strata': strata}, ensure_ascii=False, indent=2)) + '</pre>']
    pieces[4:4] = [
        '<h2>확인된 결과와 원인 가설</h2>',
        '<p>개발 오답 21개 중 Yes 정답이 18개, No 정답이 3개였다. 서로 다른 배치·서로 다른 지침의 결과이므로 시계열 성능 향상의 증거가 아니다. Yes 누락을 교정하는 방향으로 피드백이 편중됐을 가능성이 있다.</p>',
        '<p>2023년 정답 응답: Yes 110/120 → 113/120, No 84/90 → 75/90. 순손실 6건은 70개 고유 문제를 3회 실행한 210개 응답 기준이다. 위험평가 정답은 74/87 → 69/87로 하락했다.</p>',
        '<p>출처별 일치 허용 규칙은 R2에서 등장했다. R3에서는 추가 TDM 정의 반례, R5에서는 포합체가 추가된 출처 반례가 발견됐다. 그러나 보완 후보들은 선택 점수에서 탈락했다. 후보를 원래 개발 오답에 재적용한 기록이 없어 교정 효과는 알 수 없다.</p>',
        '<p>R4C1 → R5C2의 선택 응답 차이는 Profenofos 한 문제뿐이었다. 이는 1회 평가의 약한 선택 근거이나, 재실행 없이 확률적 잡음이라고 단정할 수 없다.</p>',
        '<p>2023의 신규 오류: Indoxacarb·Flutriafol은 출처/추가 정의 처리, Emamectin benzoate는 염 형태와 표현 기준의 경계, Pyridate는 명칭·포합체·출처 해석이 의심된다. 문장별 개입 실험이 없어 인과 원인은 미확정이다.</p>',
        '<p>기존 분류의 N4 비중은 선택 4/140, 평가 7/70이다. 같은 농약명이 개발·선택에 70종 겹치지만 이것만으로 정답 누출을 입증하지는 않는다. 완전 중복 제거가 농약/유형 분포의 독립성을 보장하지 않는다.</p>',
        '<h2>후속 변경과 우선순위</h2>',
        '<ol><li>구현: 최대 5회, 2회 연속 미채택 시 종료; 개발 사례 최대 10개씩 누적, 후보별 목표 교정·순정답 변화 기록.</li>'
        '<li>구현: 개발 반례와 정답 사례를 수정 요청에 전달, 한 규칙만 수정하도록 요청, P0 선택 개별 응답을 별도 저장. 지시 준수는 자동 증명하지 않는다.</li>'
        '<li>다음 검증: 후보 간 1문제 차이는 두 후보 추가 반복으로 확인. 이는 3,370회 예산에는 미포함이며 선택 과적합을 제거하지 않는다.</li>'
        '<li>추가 설계: 농약 그룹 분할·유형별 성능 비교를 별도 실험으로 검토. 기존 분할을 몰래 바꾸지 않는다.</li>'
        '<li>전문가 확인: 원문만으로 정답 근거가 부족한 사례를 분리하고, 검증된 동의어·출처 적용 기준이 필요하다면 별도 정보 제공 조건으로 평가.</li></ol>',
        '<h2>문헌 근거와 적용 한계</h2>',
        '<p><a href="https://arxiv.org/abs/1506.02629">Dwork et al., Generalization in Adaptive Data Analysis and Holdout Reuse</a>: 반복적·적응적 선택의 과적합 위험에 대한 근거. 여기서는 논문의 차등프라이버시 방법을 구현하지 않았다.</p>',
        '<p><a href="https://aclanthology.org/2023.emnlp-main.494/">ProTeGi</a>: 오류 피드백 기반 후보 탐색의 근거. 여기의 누적 검증 임계값과 조기 종료는 자체 설계이며 성능 보장은 없다.</p>',
        '<p><a href="https://arxiv.org/abs/2507.19457">GEPA</a>: 상호 보완적인 후보를 유지하는 후속 대안. 이번 v2는 GEPA나 앙상블을 구현하지 않는다.</p>',
        '<p>원본 호출 로그가 없어 API 비용·응답 모델·실제 요청 순서는 감사할 수 없다. 저장된 예측과 집계의 일관성만 확인했다. 2023 결과를 본 후 설계한 후속 실험은 탐색적 검증이다.</p>'
    ]
    for rnd in rounds:
        pieces.append('<h2>Round ' + str(rnd['round']) + ': ' + esc(rnd['parent']) + ' → ' + esc(rnd['winner']) + '</h2>')
        pieces.append('<details><summary>개발 오류 분석 전문</summary><pre>' + esc(rnd['analysis']) + '</pre></details>')
        for c in candidates:
            if c['round'] == rnd['round']:
                pieces.append('<h3>' + esc(c['name']) + ' — ' + str(c['correct']) + '/140</h3><p>' + esc(c['change']) + '</p><p>생성자가 기록한 위험: ' + esc(c['risk']) + '</p><pre>' + esc(c['prompt']) + '</pre>')
    pieces.append('<h2>개발 오답 원문</h2><pre>' + esc(json.dumps(errors, ensure_ascii=False, indent=2)) + '</pre>')
    pieces.append('<h2>2023 오류 원문·변화</h2><pre>' + esc(json.dumps(error_cases, ensure_ascii=False, indent=2)) + '</pre>')
    (OUT / 'report.html').write_text('\n'.join(pieces), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('distributions','shared_substances','development_error_labels','test_strata')},ensure_ascii=False))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    main()
