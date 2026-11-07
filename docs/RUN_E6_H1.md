# H1: 성분 대응과 평가 구조를 분리하는 비교 실험

## 실험 목적과 조건

별도·합산 평가 보완 문단을 제거한 G1에서 Mancozeb는 복구되고 Thiamethoxam은 악화됐다.
H1은 성분의 대응과 평가 구조의 대응을 구분하는 절차로 그 문단만 교체한다.
농약명·문제 ID·테스트 정답·문제별 코멘트를 지침에 넣지 않는다.
효과는 가설이며, 해당 사례를 맞히는 것만으로 성공을 판단하지 않는다.

| 조건 | 시스템 지침 | 반복 |
|---|---|---|
| C0 | 기존 E6+보완 지침 전체 그대로 | 새로 3회 |
| H1 | C0의 추가 1번 문단만 성분 대응/평가 구조 분리 절차로 교체 | 3회 |

예시 4개·ID·순서·내용·정답, 현재 문제 5필드, seed 42, OpenRouter `openai/gpt-6-sol`,
출력 1000토큰, timeout 120초, 최대 3시도 등 나머지 설정은 유지한다.
출력은 설명 없이 Yes/No. 각 요청은 독립 system/user 메시지이며 대화 이력을 누적하지 않는다.
사용자/예시 입력은 과거 E6/E6-guided 자료와 사전 대조한다. CRLF/LF만 비교 시 정규화한다.

기본 실행은 **210문제 × 2조건 × 3회 = 1,260건**이며 재시도는 별도다.
과거 97.30%를 기준 대조군 대신 쓰지 않고 **C0도 새로 호출**한다.
회차별 블록 순서: C0→H1 / H1→C0 / C0→H1.
동시기 비교지만 문제별 교차·무작위 배정은 아니며 시간 변동을 완전히 제거하지는 못한다.

## VS Code에서 준비

기존 실험 Python 환경을 활성화한 뒤 저장소 루트에서:

```bash
git fetch origin
git switch feat/e6-h1-structure-comparison
git pull --ff-only origin feat/e6-h1-structure-comparison
python -m pip install -e ".[api,test]"
python -m residue_experiment.e6_h1 --mode dry-run
```

무료 확인의 정상 출력은 `cases: 1260`, `calls: 0`, `runs: 6`이다.
dry-run은 유료 클라이언트를 만들지 않으며 test의 fake live도 실제 API를 호출하지 않는다.

## 유료 실행 (별도 의도적 실행)

기존 `.env` 또는 환경의 `OPENROUTER_API_KEY`를 사용한다. GPT_MODEL은 모델을 변경하지 않는다.

```bash
python -m residue_experiment.e6_h1 --mode live --approve-paid-api
```

한 명령으로 C0/H1 각각 3회 실행한다. `--condition H1`만 실행하면 신규 대조군이 없는
630건 실험이 되므로 권장 전체 설계와 구분해 보고한다. `--round 1` 등 부분 실행도 가능하다.
문제별 출력 없이 조건/회차 시작 메시지만 보이므로 실행 중 잠시 조용할 수 있다.

기본 출력: `results/e6-h1-v1/gpt-6-sol/2023-2025/`.
`live/C0/round-01` 및 `live/H1/round-01` 등으로 분리하고 dry-run/mock/live도 분리한다.
원시 CSV condition은 선정기 호환용 E6이며 신규 조건은 경로·config.h1_condition·plan·집계에서 구별한다.
과거 실험과 원본 자료는 수정하지 않는다. main으로 업로드/병합하지 않는다.

중단되면 같은 컴퓨터·폴더·명령으로 재개한다. 성공한 문제는 로컬 checkpoint를 재사용한다.
checkpoint.sqlite는 Git 제외 대상이며 실행 컴퓨터에 보존한다. CSV만 다른 컴퓨터에 받아 live를
실행하면 재호출될 수 있다. 서버 응답과 로컬 저장 사이 중단은 중복 과금 가능성이 있다.
실행 중 코드를 업데이트하지 말고, 한 결과 루트는 한 프로세스만 사용한다.
코드/자료/지침/기준 결과가 바뀌면 재개를 거부한다. 프로세스 종료 확인 전 lock을 지우지 않는다.

## 집계 및 사전 판단 기준

```bash
python -m residue_experiment.e6_h1 --mode analyze
```

이 명령은 저장된 live 결과를 재집계하며 API를 호출하지 않는다.

- `plan.json`/`system_prompts.json`: 실제 지침, 교체 문단, 일정, 설정과 자료·코드 해시.
- `live/analysis/condition_summary.csv`: 두 조건의 연도별·전체 Accuracy/Macro-F1 평균·표본 표준편차.
- `round_metrics.csv`: 회차별 지표, coverage, complete, FP/FN.
- `error_frequency.csv`: 각 문제의 C0/H1 3회 예측·오답 빈도, 반복 오류 복구와 안정 정답 훼손.
- `comparison.csv`: 신규 C0 반복 오답(2회 이상)을 H1에서 모두 복구한 수와 C0 안정 정답 훼손 수.
  양 조건 각 3회가 모두 완료되기 전에는 해당 문제의 복구·훼손을 확정하지 않는다.
- `resources.csv`: 시도/오류/미완료 로그. 원문 응답과 usage는 회차별 api_calls.csv.

전체 성능을 먼저 보고 기존 정답 보존 여부와 반복 오답의 변화를 함께 평가한다.
Mancozeb 개선과 Thiamethoxam 개선 유지, 출처가 다른 정의의 비교는 사전 관심 사례다.
일부 사례만 맞힌 결과로 성공을 선언하거나 중간 결과로 지침을 고치지 않는다.
기존 210문제는 이미 개발에 사용됐으므로 미검토 일반화 시험이 아니다.
결과 확인 후 최종 지침을 고정하고 사용 이력을 점검한 별도 자료에서 검증해야 한다.

## 실행된 결과를 GitHub에 업로드

두 조건 각 3회 완료 후:

```bash
git branch --show-current
git add results/e6-h1-v1/gpt-6-sol/2023-2025/
git diff --cached --stat
git commit -m "results: add C0 H1 three-round comparison"
git push origin feat/e6-h1-structure-comparison
```

키·SQLite·잠금 파일이 staging에 없는지 확인한다. force push는 하지 않는다.
