# 위험평가용 7개·단속용 3개 + 원문 보존 후보

새 계획: `results/r6c1-risk-search-balanced`. 기존 mixed 결과는 그대로 유지한다. 시작은 R6C1이며 기존 탈락 후보를 시작점으로 사용하지 않는다.

## 실행

계획은 준비 완료했다. 전체 실행:

```powershell
python -m residue_experiment.risk_search run --output results/r6c1-risk-search-balanced --mode live --max-calls 3650
```

첫 라운드만:

```powershell
python -m residue_experiment.risk_search run --output results/r6c1-risk-search-balanced --mode live --through-round 1 --max-calls 762
```

그 뒤 전체 명령으로 재개하면 정상 응답과 완료 라운드를 재사용한다. 한도는 해당 폴더의 누적 호출 수이다. 후보 생성/평가 요청 수는 기존 mixed와 같으며 실제 호출은 캐시·조기 종료로 감소한다. 실패 재시도는 별도 호출 예산을 소모한다.

준비를 재현하는 명령(유료 호출 없음):

```powershell
python -m residue_experiment.risk_search prepare --balanced --output results/r6c1-risk-search-balanced
```

## 변경점

- 개발 배치는 여전히 매 라운드 위험평가용 35개·단속용 15개다.
- 수정용 입력은 첫 라운드부터 위험평가용 7개·단속용 3개다. 첫 위험평가용은 기존 제안에서 Clothianidin, Fenpicoxamid, Thiamethoxam, Fenazaquin, Trifloxystrobin, Methoxyfenozide, Chlorothalonil 사례를 유지한다. 단속용은 첫 배치의 Pyriofenone, Flutianil, Profenofos 동물성 사례 3개를 고정한다. 단속용 3개는 전문가 의미적 선정이 아닌 배치 순서 기반이다.
- 이후 위험평가용은 현재 오답 우선 최대 4개, 단속용은 최대 1개를 먼저 고른다. 각 유형의 나머지는 현재 정답에서 No/Yes와 문구 유사도를 고려하여 채운다. 정답이 부족하면 해당 유형의 남은 오답으로 채워 7:3을 유지한다. 사례 부족 시 다른 유형으로 대체하지 않고 중단한다. 선정 가능한 오답이 전혀 없으면 후보 생성을 생략하고 미개선으로 계산한다.
- 후보 1번: LLM은 최대 2,000자의 `risk_assessment_rule`만 제공한다. 코드는 현재 지침 전체를 문자 그대로 보존한 뒤 `For Risk assessment only (not Enforcement):` 범위 표시와 보완 규칙을 추가한다. 기존 위험평가 문장의 삭제·교체도 하지 않는다. 모델이 함께 반환한 전체 prompt는 후보 1번에서 무시한다.
- 후보 2·3번: 적용 한계 명시 및 전체 재작성 방식이다.
- 원문 보존은 동작 보존을 보장하지 않으므로 모든 후보의 단속용 평가를 유지한다. 검증/채택 기준, 누적 사례 재검증, 최대 5라운드·2회 연속 미개선 종료는 그대로다. 선택 자료는 수정용 LLM에 제공하지 않는다.

첫 10개가 모두 위험평가용이었던 이전 실험과 달리 이번 실험은 처음부터 7:3이다. 10개 비율과 후보 생성 제약을 동시에 바꾸므로 개선되더라도 두 변경의 효과를 따로 입증한 것으로 해석하지 않는다.

결과: `live/round-NN/optimizer_input.json`, `generation_input.json`, `candidates.json`, `selection.json`. 최종 결과는 `live/final_prompt.json`. 2023~2025년 평가를 자동 실행하지 않는다.
