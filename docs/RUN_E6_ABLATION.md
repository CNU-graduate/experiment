# G1・G2・G3: E6 보완 규칙 제거 실험 (각 2회)

브랜치: `feat/e6-guided-ablation-two-repeats`. main에는 병합하지 않는다.
유료 실행은 사용자가 live 명령을 실행할 때만 시작한다.

## 조건과 검증할 질문

현재 E6+보완 지침(3회 평균 정확도 97.30%)에서 추가 문단 하나만 제거한다.
이전에 계획한 B/C/D 대신 G1/G2/G3라는 새 조건명을 쓴다.

| 조건 | 제거하는 보완 문단 | 검증할 질문 |
|---|---|---|
| G1 | 1번: 별도 평가와 합산 정의 구분 | Thiamethoxam 개선과 Mancozeb 악화가 이 추가 문단과 관련되는가? |
| G2 | 2번: 목적·대상·출처별 예외 범위 | 예외를 해당 범위에 제한하는 추가 지침이 정답과 신규 오류에 미치는 영향은? |
| G3 | 3번: 상태·측정 설명과 실질 차이 구분 | 과도한 No를 줄이는 효과와 실제 범위 차이를 놓치는 부작용이 있는가? |

각 조건 2023~2025년 210문제 × **2회** = 420건. 세 조건 합계 **1,260건**이며
오류 재시도(문제당 최대 3시도)는 별도다. 완전 지침 기준 조건을 새로 호출하지 않는다.
현재 E6+보완 지침 3회와 원래 E6 3회는 읽기 전용 검증·비교 자료로 사용한다.

고정 사항: E6의 예시 4개, 연도별 예시 ID·내용·정답·순서, 문제 5필드,
seed 42, OpenRouter `openai/gpt-6-sol`, 기존 호출 설정과 Yes/No 출력.
`GPT_MODEL` 환경변수로 모델을 바꾸지 않는다.
원래 E6 system과 보완 지침의 공통 머리말·꼬리말을 유지한다. 남은 문단의 번호도 바꾸지 않는다.
**기본 지침에도 유사한 내용이 있으므로 전체 개념을 제거하는 실험이 아니라,
추가한 세 보완 문단 각각의 기여를 보는 실험이다.**
정확한 문구와 삭제 문단은 `residue_experiment/e6_ablation.py` 및 `plan.json`에 보존된다.

## 실행 순서

- 1회차: G1 → G2 → G3
- 2회차: G3 → G2 → G1

두 회차의 순서를 반대로 하여 순서 편향을 일부 줄인다. 무작위 배정이나 완전한 균형 설계는 아니다.
조건별 명령으로 따로 실행하면 이 전체 순서와 달라지므로 실제 실행 순서를 보고한다.
한 결과 루트는 한 프로세스만 사용한다.

## VS Code 명령

기존 Python 환경을 활성화하고 저장소 루트에서 실행한다.

```bash
git fetch origin
git switch feat/e6-guided-ablation-two-repeats
git pull --ff-only origin feat/e6-guided-ablation-two-repeats
python -m pip install -e ".[api,test]"
```

무료 사전 확인:

```bash
python -m residue_experiment.e6_ablation --mode dry-run
```

정상 출력은 **cases 1260 / calls 0 / runs 6**이다. SDK 클라이언트도 생성하지 않는다.
실행 전 임시 무료 계획으로 과거 E6 및 E6+보완 지침의 문제·예시 전체와 대조한다.
예시 ID·라벨·순서·실제 내용, 테스트 ID·정답·연도, 모델·호출 설정·주석이 다르면
유료 클라이언트 생성 전에 중단한다. 문자열의 CRLF/LF만 비교 시 정규화한다.

`.env`에 기존 `OPENROUTER_API_KEY`를 설정하고, 유료 실행을 의도한 경우:

```bash
python -m residue_experiment.e6_ablation --mode live --approve-paid-api
```

이 명령 하나가 **G1/G2/G3 각각 2회**를 순차 실행한다. 3회차 선택지는 없다.
필요한 조건만 2회 실행하려면:

```bash
python -m residue_experiment.e6_ablation --mode live --condition G1 --approve-paid-api
python -m residue_experiment.e6_ablation --mode live --condition G2 --approve-paid-api
python -m residue_experiment.e6_ablation --mode live --condition G3 --approve-paid-api
```

일부 회차만 실행하려면 `--round 1` 또는 `--round 2`를 붙인다.
회차 시작 메시지만 출력되며 문제별 진행 출력은 없다.

## 결과와 재개

기본 출력: `results/e6-guided-ablation-v1/gpt-6-sol/2023-2025/`.
조건과 회차별 `live/G1/round-01` 등으로 분리한다. dry-run/mock/live도 분리한다.
기존 선정기 때문에 원시 CSV의 condition은 E6이며, 신규 조건은 폴더 경로와
manifest의 config.ablation_condition/ablation_round, plan, 집계의 G1/G2/G3로 구별한다.

중단되면 같은 컴퓨터에서 같은 명령으로 재개한다. 성공한 문제는 로컬 checkpoint에서 재사용한다.
체크포인트는 Git에 올리지 않고 실행한 컴퓨터에 보존한다. GitHub CSV만 받은 다른 컴퓨터에서
live를 실행하면 요청이 재호출될 수 있다. 응답 도착과 저장 사이의 중단은 중복 과금 가능성이 있다.
코드·설정·입력·과거 기준 결과 변경 시 재개를 거부한다. 진행 중 코드를 업데이트하지 않는다.
실제 프로세스가 종료됐는지 확인하기 전에는 `.run.lock`을 지우지 않는다.

실제 결과만 무료 재집계:

```bash
python -m residue_experiment.e6_ablation --mode analyze
```

- `plan.json`, `system_prompts.json`: 고정 지침, 삭제 문단, 설정, 자료·구현·과거 결과 해시.
- 모드별 `analysis/condition_summary.csv`: 정확도·Macro-F1 평균/표본 표준편차, 완료 회차 수.
- `analysis/round_metrics.csv`: 회차별·연도별·전체 성능, FP/FN, coverage.
- `analysis/error_frequency.csv`: 문제별 과거 3회/신규 2회 오답 수와 비율, 회차별 예측.
- `analysis/baseline_comparison.csv`: 기존 반복 오답(3회 중 2회 이상)을 신규 2회 모두 정답으로
  복구한 수, 과거 3회 안정 정답을 신규에 한 번 이상 틀린 수. 신규 2회 미완료는 판정하지 않는다.
- `analysis/resources.csv`: 시도·실패·미완료 API 로그 수. 원문과 usage는 각 회차 api_calls.csv에 저장.

오답 **횟수는 3회 대 2회이므로 직접 빼지 않는다**. 정확도 평균과 오답 비율을 비교한다.
2회만으로 안정성을 확정하지 않는다. 동시기 완전 지침 대조군이 없고 기존 문제는 분석에 사용돼
탐색적 실험이다. 관찰된 차이를 특정 문단의 인과 효과라고 확정하지 않는다.
보고 시 Mancozeb·Propiconazole 개선뿐 아니라 Pyrethrins·Thiamethoxam 개선 유지와
전체 기존 안정 정답의 훼손을 함께 본다. 성능을 본 뒤 이번 버전의 문구를 수정하지 않는다.

## 결과 업로드

```bash
git add results/e6-guided-ablation-v1/gpt-6-sol/2023-2025/
git diff --cached --stat
git commit -m "results: add G1 G2 G3 two-round ablation results"
git push origin feat/e6-guided-ablation-two-repeats
```

키·SQLite·잠금 파일이 포함되지 않았는지 확인한다. 기존 main에는 push하지 않는다.
