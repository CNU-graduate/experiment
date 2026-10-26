# GPT 전용 P3·P4·P5: 독립 프롬프트 3회 반복

## 조건

| 조건 | 실제 시스템 프롬프트 | 출력 |
|---|---|---|
| P3 | 적용 범위를 명확히 한 독립 통합 지침 | Yes 또는 No |
| P4 | 최소 과제 설명 + 전문가 역할 부여만 | Yes 또는 No |
| P5 | 최소 과제 설명 + CoT 지시만 | 짧은 근거 + 마지막 Final label: Yes/No |

P4·P5에 P3나 기존 P0/P1/P2를 앞에 붙이지 않습니다.
정확한 영문은 residue_experiment/prompt_methods.py에 고정합니다.
P5 설명은 생성된 근거이며 내부 사고 과정을 직접 관찰한 자료가 아닙니다.

GPT 모델 openai/gpt-6-sol 하나만 OpenRouter로 호출합니다.
GPT_MODEL 환경변수는 모델을 덮어쓰지 않습니다.
2023~2025년 각 70개, 총 210개를 조건별 3회 실행합니다.
210×3조건×3회 = 1,890건이며 오류 재시도는 별도입니다.
출력 한도 1,000토큰, timeout 120초, 최대 3시도는 기존 실험과 동일합니다.

## 독립성

- 요청마다 해당 조건의 system 하나와 현재 문제의 user 하나만 전송합니다.
- 이전 문제·회차·조건의 응답, 평가 정답, EFSA 코멘트, 예시를 보내지 않습니다.
- 입력은 기존 5필드이며 examples는 항상 빈 배열입니다.
- 대화 ID나 previous_response_id로 이전 응답을 연결하지 않습니다.
- 조건·회차별 별도 SQLite 체크포인트와 폴더를 사용합니다.
- 같은 API 클라이언트 사용은 대화 기록 누적을 뜻하지 않습니다.
- 서비스 내부 캐시·모델 업데이트·확률성까지 통제한다고 주장하지 않습니다.

순서:
1회차 P3→P4→P5 / 2회차 P4→P5→P3 / 3회차 P5→P3→P4.
각 조건 안에서는 동일한 210문제 순서를 사용합니다.
실행 중 앞선 결과에 따라 지침을 수정하지 않습니다.

## 설치와 무료 확인

별도 브랜치 feat/gpt-p3-p4-p5-independent에서 실행합니다. main 병합은 하지 않습니다.

~~~bash
git fetch origin
git switch feat/gpt-p3-p4-p5-independent
python -m pip install -e ".[api,test]"
python -m pytest -q tests
python -m residue_experiment.prompt_method_repeats --mode dry-run
~~~

전체 dry-run은 cases 1890, calls 0입니다. API 클라이언트를 만들지 않습니다.
기본 설정: config.openrouter.prompt-methods.json.
plan.json과 system_prompts.json에서 실제 지침과 모델을 확인하세요.

mock은 같은 명령에 --mode mock을 사용합니다.
P5 mock 설명은 인프라 검증용 가짜 문구입니다. Mock 점수는 모델 성능이 아닙니다.

## 실제 유료 실험

.env에 본인 OPENROUTER_API_KEY를 설정한 뒤 실행합니다.

~~~bash
python -m residue_experiment.prompt_method_repeats --mode live --approve-paid-api
~~~

이 명령 하나로 P3/P4/P5 각각 3회 실행합니다.
--provider openai는 선택 사항입니다. Claude·Gemini는 허용하지 않습니다.
개발·CI에서는 실제 유료 모델 호출을 하지 않습니다.

일부만 확인하려면:

~~~bash
python -m residue_experiment.prompt_method_repeats --mode dry-run --condition P5 --round 1
~~~

--condition은 P3/P4/P5, --round는 1/2/3입니다.
조건과 회차를 지정하면 그 부분만 실행하며 전체 1,890건을 실행한 것으로 보지 않습니다.

## 결과, 재개, 새 실험

기본 루트:
results/prompt-methods-v1/gpt-6-sol/2023-2025/

- plan.json: 모델·지침·데이터·기존 결과·구현 파일의 해시와 9회 일정
- system_prompts.json: P3·P4·P5의 정확한 시스템 지침
- dry-run/P3/round-01 등: 사전 계획
- mock/P3/round-01 등: 가짜 응답
- live/P3/round-01 ~ live/P5/round-03: 실제 결과
- 모드별 analysis/: 새 결과와 기존 P0/P1/P2 비교

같은 명령과 같은 폴더로 다시 실행하면 재개합니다.
성공 응답은 재호출하지 않고 미완료·실패 문제부터 진행합니다.
P3 성공 응답은 P4·P5나 다른 회차의 성공으로 취급하지 않습니다.
calls는 해당 실행 결과 폴더에 누적 저장된 API 시도 수입니다.

완전히 새로 시작하려면 --fresh를 붙이세요.
새 timestamp 하위 루트를 만들며 기존 응답을 재사용하지 않습니다.
--output으로 빈 별도 루트를 지정할 수도 있습니다.
dry-run/mock/live는 분리되어 dry-run 때문에 live가 생략되지 않습니다.

한 결과 루트는 한 프로세스만 사용합니다.
.run.lock이 남았다면 실행 중인 프로세스가 없는지 확인한 후에만 수동 제거하세요.
코드·데이터·지침·기준선·설정 변경 시 기존 결과에 섞지 않고 중단합니다.
기존 baseline/remain-v2/zero-shot-repeats/instruction-v1 등에는 출력할 수 없습니다.

## P5 채점과 실패

P5는 설명에 등장한 Yes/No를 찾지 않고 마지막 Final label: Yes/No 줄만 채점합니다.
마지막 라벨은 한 번만 있어야 하며 앞에 짧은 설명이 있어야 합니다.
라벨 누락·중복·후행 텍스트·형식 오류는 오류로 기록하고 재시도합니다.
예측 CSV response와 api_calls.csv에 원문 응답을 보존합니다.
P3·P4는 기존의 엄격한 Yes/No 형식을 유지합니다.
정상 응답률·실패 시도 수를 보고하고 API 실패를 오답으로 세지 않습니다.
반복 실패·치명적 HTTP 오류 시 저장 후 중단합니다. 문제를 고친 뒤 같은 폴더에서 재개합니다.
출력이 잘려 최종 라벨이 없으면 형식 오류로 처리됩니다.
실제 성능은 모든 210문제가 정상 완료됐는지 함께 확인해야 합니다.

## 기준선과 분석

기존 P0/P1/P2는 읽기만 합니다. 모델을 재호출하지 않습니다.

- P0: results/zero-shot-repeats/gpt-6-sol/2023-2025
- P1/P2: results/instruction-v1/gpt-6-sol/2023-2025

P0의 210개 ID·라벨·3개 정상 응답과 저장된 원본 해시를 대조합니다.
P1/P2의 각 3회 원본 예측·manifest·모델·입력 해시·호출 설정도 대조합니다.
비교 집합은 P0/P2로 미리 고정합니다.

| 집합 | 기준 |
|---|---|
| P2 신규 오답 | P0 3회 정답 → P2 한 번 이상 오답 |
| P2 해결 | P0 3회 오답 → P2 3회 정답 |
| 공통 안정 정답 | P0·P2 모두 3회 정답 |

분석 파일:
- round_metrics.csv: P0~P5 회차별·연도별 Accuracy, Macro-F1, FP/FN, coverage
- condition_summary.csv: 정상 완료 회차만의 평균·표본 표준편차와 완료 회차 수
- baseline_comparison.csv: 신규 오답 복구, P2 개선 유지·상실, 추가 신규 오답
- P3_error_frequency.csv 등: 문제별 3회 예측·상태·P0/P2 빈도
- *_recovered_p2_errors.csv / *_lost_p2_fixes.csv / *_additional_new_errors.csv
- resources.csv: API 시도, 실패 시도, 보고된 토큰, 호출 시간, 응답 문자 수

미완료 문제는 해결·훼손으로 확정하지 않습니다.
토큰 합계는 API가 보고한 usage가 있는 시도 기준이며 usage_records를 함께 확인합니다.
기존 결과는 historical=True로 표시합니다. dry-run 새 결과에는 실제 성능이 없습니다.

저장된 live 결과만 다시 분석:

~~~bash
python -m residue_experiment.prompt_method_repeats --mode analyze
~~~

## 연구 해석

P3·P4·P5는 서로 다른 프롬프트 방식의 비교입니다.
P3에 역할 또는 CoT를 추가한 순수한 효과를 측정하는 설계가 아닙니다.
P4는 최소 과제+역할, P5는 최소 과제+CoT이며 P3의 상세 규칙을 포함하지 않습니다.
P5는 출력 길이·형식도 다르므로 CoT만의 순수한 효과라고 단정하지 않습니다.
P0~P2와 실행 시점이 다를 수 있습니다. 결과가 서로 영향을 받지 않는 요청 구조와
모델 서비스의 시간적 변동은 구분해야 합니다.
이미 오답을 분석한 210문제는 탐색·개발 자료입니다. 일반화는 별도 미검토 자료로 검증합니다.
