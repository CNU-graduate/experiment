# EFSA–JMPR 잔류정의 Few-shot 실험

Python 3.11+에서 JMPR과 EU 잔류정의의 비교 가능성(Yes/No)을 평가합니다.
**기본 모드는 dry-run이며, 사용자 별도 승인 전에는 live 모드를 실행하지 마세요.**
원본 CSV는 읽기만 합니다. Mock 결과는 임의의 결정적 예측으로, 실제 모델 성능이 아닙니다.

## 설치와 무료 검증

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e '.[api,test]'
python -m pytest -q
python -m residue_experiment.cli --mode dry-run --output results/dry-run
python -m residue_experiment.cli --mode mock --output results/mock
```

Mock/dry-run에는 API 키가 필요 없고 SDK 클라이언트도 생성하지 않습니다.
Mock만 쓸 때는 `pip install -e .`로 최소 의존성만 설치할 수 있습니다.
`config.json`의 `data_dir`은 설정 파일 위치 기준으로 해석하며 원본 CSV가 있는 폴더를 지정합니다.
하위 폴더도 검색하지만 동일 연도·종류 파일이 두 개 있으면 오류로 처리합니다.

## 데이터 검증

입력은 `substance`, `purpose`, `commodity`, `JMPR`, `EU` 다섯 필드뿐입니다.
`id`와 `year`는 추적용이고 테스트 `EFSA`, `efsa_comments`, `source_*`는 프롬프트에서 제외합니다.
과거 예시에는 다섯 입력 필드와 정답 `EFSA`만 제공합니다.

UTF-8 BOM 및 인용된 여러 줄 필드를 지원합니다. CSV 구조, 필수 열·값, 파일/행 연도,
정확한 Yes/No 라벨, 중복 ID, 테스트/정답지 ID 집합과 다섯 입력 필드의 일치를 확인합니다.
각 테스트 파일은 70건이어야 합니다. 동일 ID의 입력/정답이 충돌하면 중단합니다.
동일한 예시 중복은 제거하고 기록하며 테스트 ID 중복은 오류입니다.
answerkey와 remain 두 파일을 모두 갖춘 연도만 후보 풀이 됩니다.
원본 문자열과 CSV를 변경하거나 부족한 데이터를 보충하지 않습니다.

| 연도 | 테스트 Yes / No | remain 건수 | 후보 Yes / No | 후보 총수 |
|---|---:|---:|---:|---:|
|2018|35 / 35|39|57 / 52|109|
|2019|43 / 27|37|72 / 35|107|
|2021|44 / 26|71|92 / 49|141|
|2022|48 / 22|44|78 / 36|114|
|2023|40 / 30|20|54 / 36|90|
|2024|42 / 28|16|55 / 31|86|
|2025|43 / 27|12|52 / 30|82|

현재 2020년 CSV가 없습니다. 달력상의 t−1/t−2를 그대로 적용합니다.

| 테스트 연도 | 실행 가능 조건 | 과거 연도 부족으로 제외 |
|---|---|---|
|2018|E0|E1,E2,E3,E4,E5|
|2019|E0,E1,E2,E5|E3,E4|
|2021|E0,E3|E1,E2,E4,E5|
|2022|E0,E1,E2,E5|E3,E4|
|2023~2025|E0~E5|없음|

2018/2019/2021/2022에서는 조건별 분석 표본이 다릅니다. E0~E5를 모두 직접 비교할 때는
`years`를 `[2023,2024,2025]`로 설정해 동일 연도·테스트 집합을 사용하세요.
CSV 내용 자체의 규제적 정답 타당성을 재판정하지는 않습니다.

## 실험 조건과 재현성

- E0: 예시 없음.
- E1: t−1 후보 풀에서 무작위 4개.
- E2: t−1 Yes 2개 + No 2개.
- E3: t−2 Yes 2개 + No 2개.
- E4: t−1과 t−2에서 각각 Yes 1개 + No 1개.
- E5: t−1에서 다섯 입력 필드만 JSON 텍스트로 직렬화해 TF-IDF + cosine 상위 4개.

E1~E4는 **연도·조건·seed마다 한 번 정한 예시 세트**를 해당 70개 테스트에 사용합니다.
정렬된 후보와 SHA-256으로 파생한 random seed를 사용하고 최종 순서도 seed로 섞습니다.
모든 제공자에 동일한 예시와 순서를 적용합니다. `seeds`로 반복 횟수를 변경할 수 있습니다.
E0/E5는 무작위 선택이 없어 seed 없이 한 번만 실행합니다.
E5의 TF-IDF는 과거 후보 풀에만 fit하며 테스트는 transform합니다. 정답은 계산하지 않습니다.
동점은 ID 오름차순이고 유사도가 0이어도 순서대로 4개를 선택합니다.

프롬프트는 fat-solubility 표기만 다른 경우 Yes로 판단하도록 지시하고,
Enforcement/Risk assessment 목적과 EU Regulation 396/2005 / peer review / MRL review를
구분하도록 합니다. EU 필드 내부 출처 설명은 보존하고 별도 출처 메타데이터는 제공하지 않습니다.
응답은 정확히 `Yes` 또는 `No`여야 하며, 다른 응답은 오류로 기록·재시도합니다.

## 실제 실험 — 별도 승인 이후에만

모델은 OpenAI Responses API, Anthropic Messages API, Google Gen AI SDK로 호출합니다.
모델 ID는 `config.json`의 `models`에서 설정합니다. 현재 공란이므로 live 실행은 차단됩니다.
실행 시점에 각 회사 공식 문서/계정에서 사용 가능한 최신 GPT·Claude·Gemini 모델을 확인하고
정확한 모델 ID를 입력하세요. 변경 가능한 `latest` 별칭보다 고정 버전을 권장합니다.
이번 구현에서는 유료 호출로 모델 가용성을 확인하지 않았습니다.

```bash
cp .env.example .env
# .env에 OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY 설정
# config.json의 models 및 years/seeds를 검토
python -m residue_experiment.cli --mode dry-run --output results/preflight
# 사용자 별도 승인을 받은 후에만 아래 명령 실행
python -m residue_experiment.cli --mode live --approve-paid-api --output results/live-v1
```

`.env`와 결과 파일은 `.gitignore`에 포함되며 키는 결과·로그에 기록하지 않습니다.
`--approve-paid-api`는 사용자가 승인한 뒤 운영자가 지정하는 실행 확인 옵션입니다.
키가 있다고 자동으로 live 실행하지 않습니다. live 모드에서는 모든 제공자의 키와 모델을
먼저 확인합니다. 실제 요청에는 최대 출력 토큰과 timeout이 적용됩니다.
SDK 자체 재시도는 끄고 실행기에서 `max_attempts`, 지수 backoff로 재시도합니다.
모델별 기본 생성 설정을 사용하므로 서비스측 완전 결정성은 보장하지 않습니다.
현재 개발 환경의 네트워크 허용 목록에 모델 API가 없다면 승인 후 환경 설정도 필요합니다.

## 중단과 재개

동일한 config·mode·output으로 같은 명령을 다시 실행하면 SQLite 체크포인트를 사용합니다.
성공한 케이스는 재호출하지 않고 pending/error 케이스를 다시 시도합니다.
실행 계획 전체를 호출 전에 저장해 중단된 케이스도 지표 분모에 포함합니다.
각 시도는 호출 전에 started로 기록하고 결과·예측은 트랜잭션으로 저장합니다.
Ctrl+C에서는 저장된 상태로 CSV를 갱신합니다. 강제 종료 후에는 재실행해 CSV를 갱신하세요.
데이터/설정/모드/구현 코드가 바뀌면 기존 결과 폴더 재사용을 차단합니다.
**한 결과 폴더에는 한 프로세스만 실행하세요.**

서비스가 응답한 직후 로컬 저장 전에 강제 종료/timeout이 발생하면 서버에서 이미 과금된
요청을 재개 시 다시 호출할 수 있습니다. 공식 API 전반에 exactly-once 보장은 없습니다.
started 시도는 `api_errors.csv`에 남아 이런 불확실한 호출을 확인할 수 있습니다.
재개 시 error 케이스마다 설정한 최대 시도 횟수를 새로 적용합니다.

## 결과 파일

| 파일 | 내용 |
|---|---|
| validation.csv | 모든 CSV의 열, 건수, 라벨 분포, 고유 ID 수, SHA-256 |
| data_issues.csv | 중복 제거, 후보/테스트 파일 부족 |
| predictions.csv | 제공자·모델·연도·조건·seed·ID·정답·예측·상태·프롬프트 해시 |
| examples.csv | 케이스별 예시 ID·연도·정답·순서·E5 유사도 |
| exclusions.csv | 과거 연도/라벨 데이터 부족으로 제외된 케이스와 이유 |
| metrics.csv | 반복별 Accuracy, Precision, Recall, Macro-F1, TN/FP/FN/TP, coverage |
| comparison.csv | 제공자·모델·연도·조건별 반복 평균과 표본 표준편차 |
| api_calls.csv / api_errors.csv | 시도별 시간·상태·응답·토큰 사용량·응답 ID / 오류 |
| manifest.json | 설정, 데이터 해시, 모드, 시스템 프롬프트, 실행 지문 |
| checkpoint.sqlite | 전체 계획·프롬프트·예측·시도 이력 및 재개 상태 |

Precision/Recall은 Yes를 양성으로 계산합니다. Macro-F1은 항상 No와 Yes 두 라벨을
평균하며 zero-division=0입니다. 혼동행렬은 행=실제, 열=예측, 순서 `[No, Yes]`입니다.
실패/제외/미실행을 임의의 정답으로 치환하지 않습니다. 반복별 점수는 성공 응답만으로 계산하고
coverage와 complete를 함께 제공합니다. comparison 평균·표준편차는 **완료된 반복만** 사용하며,
완료가 없는 조건은 공란입니다. 단일 반복 표준편차는 0입니다. 불완전 반복이 있다면 수치를
완료 실험과 동등하게 비교하지 마세요. Dry-run은 예측과 점수가 모두 공란입니다.

기본 설정은 20,580개 계획 중 13,230개 실행 가능, 7,350개 제외입니다.
실제 실행 비용은 실행 가능 케이스 × 재시도와 입력/출력 토큰에 따라 달라집니다.
Mock의 세 제공자 이름은 어댑터 경로를 검증하기 위한 구분이며 실제 모델 응답이 아닙니다.

## GitHub 반영

제공된 코드 패키지의 새 파일을 `CNU-graduate/experiment` 체크아웃에 복사하세요.
원본 CSV는 변경하거나 다시 업로드할 필요가 없습니다.

```bash
git switch -c feat/residue-few-shot
# 제공된 residue_experiment/, tests/, README.md, config.json,
# pyproject.toml, .env.example, .gitignore, TEST_REPORT.md를 복사
python -m pytest -q
git add residue_experiment tests README.md config.json pyproject.toml .env.example .gitignore TEST_REPORT.md
git diff --cached --stat
git commit -m "Implement temporal EFSA-JMPR few-shot experiments"
git push -u origin feat/residue-few-shot
```

CSV 변경이 없는지 `git diff -- '*.csv'`로 확인하세요. 실제 유료 API 호출은 실행하지 않았습니다.
API 통합 테스트도 SDK 네트워크 메서드를 Mock으로 대체합니다.
