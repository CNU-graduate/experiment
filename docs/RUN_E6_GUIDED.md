# E6-guided-v1: 기존 E6 예시 + 판정 보완 지침

실행 브랜치: `feat/gpt-p3-p4-p5-independent`. main에 병합하지 않습니다.
이 준비 작업은 무료 검증만 수행합니다. 유료 실행은 사용자 승인 후 아래 live 명령으로 합니다.

## 실험 조건

- 기준: 저장된 E6 3회 (기존 remain-v2의 E6 + e6-repeats 2·3회차).
- 신규: 연도별 동일한 E6 예시 4개·순서·seed 42 + 기존 system에 고정한 짧은 추가 지침.
- 추가한 내용은 별도 평가/합산 구분, 목적·대상별 예외 범위, 상태·측정 설명과 실질 차이 구분입니다.
- P3 전체, 역할 부여, CoT, 새 출처 우선순위, 문제별 정답/코멘트를 추가하지 않습니다.
- OpenRouter `openai/gpt-6-sol` 고정. `GPT_MODEL`은 적용하지 않습니다.
- 설정은 기존 manifest에서 가져옵니다: 2023~2025, 출력 1000토큰, timeout 120초, 최대 3시도.
- 신규 210문제 × 3회 = 630건. 오류 재시도는 별도입니다.
- 실제 지침은 `residue_experiment/e6_guided.py`의 `GUIDED_SYSTEM`에 고정됩니다.
- 내부 결과의 condition 열은 기존 선정기를 사용하는 `E6`입니다. 신규 조건은 결과 루트와
  `plan.json`의 version/system prompt 및 집계 condition `e6-guided-v1`로 구별합니다.

P3에서 관찰한 강점을 설명하는 후보 규칙을 시험하는 것이며, 해당 규칙이 성능 차이의 원인으로
입증된 것은 아닙니다. 여러 보완 규칙을 묶었으므로 규칙 하나의 순수 효과도 측정하지 않습니다.

## 사전 검증

매번 SDK 생성 전에 임시 dry-run으로 현재 E6 선정 결과를 과거 세 회차와 대조합니다.
문제 입력 전체와 예시 내용·정답·ID·순서, 테스트 ID·정답·연도, 모델·시스템·호출 설정,
주석 해시를 검증합니다. 입력 문자열의 CRLF/LF만 정규화하며 나머지 내용 차이는 거부합니다.
검증 임시 자료는 실행 후 제거됩니다. 과거 결과는 읽기만 합니다.

VS Code에서 저장소 루트의 Python 환경을 활성화한 후:

```bash
git pull --ff-only origin feat/gpt-p3-p4-p5-independent
python -m pip install -e ".[api,test]"
python -m pytest -q tests/test_e6_guided.py
python -m residue_experiment.e6_guided --mode dry-run
```

정상 dry-run은 `cases: 630`, `calls: 0`입니다. 프롬프트·예시는 새 결과 폴더에서 확인합니다.
테스트의 fake live는 가짜 Provider로 SDK를 대체하며 실제 API 호출을 하지 않습니다.

## 유료 실행

`.env`에 `OPENROUTER_API_KEY`를 설정합니다. 키를 커밋하거나 출력하지 마세요.
사용자가 실행을 승인한 뒤:

```bash
python -m residue_experiment.e6_guided --mode live --approve-paid-api
```

이 명령 하나로 1~3회차를 순차 실행합니다. 회차별 실행을 원하면 `--round 1` 등으로 지정합니다.
중단되면 같은 명령으로 재개합니다. 성공한 문제는 checkpoint에서 재사용합니다.
SDK 응답과 로컬 저장 사이에 중단되면 재개 시 중복 과금될 가능성은 있습니다.
checkpoint.sqlite는 Git에서 제외되므로 실행한 컴퓨터에 보존해야 합니다.
GitHub CSV만 받은 다른 컴퓨터에서 동일 live 명령을 실행하면 재호출될 수 있습니다.
한 결과 루트는 한 프로세스만 사용하며, 실행 중 `.run.lock`을 지우지 않습니다.

## 결과·집계

기본 결과는 `results/e6-guided-v1/gpt-6-sol/2023-2025/`입니다.

- `plan.json`: 고정 지침, 설정, 구현·자료·과거 결과 해시.
- `dry-run/round-01` 등: 무료 계획. live와 별도 체크포인트입니다.
- `live/round-01` ~ `round-03`: 신규 실제 결과.
- 모드별 `analysis/round_metrics.csv`: 회차·연도·전체 Accuracy, Macro-F1, FP/FN, coverage.
- `analysis/condition_summary.csv`: 완료 회차만의 평균·표본 표준편차와 완료 회차 수.
- `analysis/error_frequency.csv`: 기존 E6와 신규 조건의 문제별 오답 빈도,
  기존 반복 오답(2회 이상)의 3회 정답 복구, 기존 안정 정답의 신규 오답 여부.
  신규 3회 미완료 문제는 복구·훼손 판정을 공란으로 남깁니다.
- `api_calls.csv` / `api_errors.csv`: 실제 시도 기록. 시작만 기록된 시도는 완료·실패와 구분해 검토합니다.

기존 결과만 재집계 (유료 호출 없음):

```bash
python -m residue_experiment.e6_guided --mode analyze
```

평가에서는 전체 성능과 회차 변동, 반복 오답 감소, 기존 안정 정답 훼손을 함께 보고합니다.
Pyrethrins·Tebuconazole·Thiamethoxam과 Propiconazole·Acetamiprid는 사전 관심 유형이지만,
이 문제들만 골라 성공을 판정하지 않고 전체 210문제를 보고합니다.
과거 E6와 실행 시점이 달라 시간적 변동이 혼재하며, 이미 분석한 데이터의 개발 실험입니다.
일반화와 인과 효과를 확정하려면 동시기 대조 실험 및 별도 미검토 자료가 필요합니다.

코드·자료·설정·과거 결과가 달라지면 재개를 거부합니다. 변경이 꼭 필요하면 같은 버전에
혼합하지 말고 새 실험 버전을 만드세요. 임시 검증용 `--output`은 저장소 밖 경로를 지원합니다.

## GitHub에 결과 올리기

```bash
git add results/e6-guided-v1/gpt-6-sol/2023-2025/
git diff --cached --stat
git commit -m "results: add GPT E6 guided three-round results"
git push origin feat/gpt-p3-p4-p5-independent
```

키·체크포인트가 포함되지 않았는지 확인합니다. main으로 push하거나 병합하지 않습니다.
