# EFSA–JMPR 잔류물 정의 Few-shot 실험

## 추가 실험: P1/P2 지침을 각각 3회 (P0 호출 없음)

예시 없이 P1(공통 절차), P2(공통 절차＋모델별 보완 지침)를 각각3회 실행합니다.
기존 E0 3회 결과는 읽기 전용 비교 기준으로 사용합니다. 모델당1,260건입니다.

```bash
python -m residue_experiment.instruction_repeats --provider openai --mode dry-run
```

담당 모델은 openai / anthropic / gemini로 선택합니다.
[설계·검증·실행·재개 안내](docs/RUN_INSTRUCTION_REPEATS.md)를 먼저 확인하세요.


JMPR과 EU 농약 잔류물 정의의 비교 가능성을 Yes/No로 평가합니다. Python 3.11+가 필요합니다.
기본은 dry-run이며 실제 유료 API는 사용자가 승인한 뒤 live 모드로만 호출합니다.
원본 CSV는 수정하지 않습니다. Mock 점수는 실제 모델 성능이 아닙니다.

## 현재 프로젝트 구조

| 경로 | 용도 |
|---|---|
| `residue_experiment/` | 실험 실행, 예시 선택, 프롬프트, API 호출, 결과 집계 |
| `tests/` | 실험 코드 검증 |
| `config.json`, `config.openrouter.yearly-remain.json` | 새 remain 실험 설정 |
| `data/ESFA_*.csv` | 원본 데이터 21개 |
| `results/` | [실험별·모델별 결과 안내](results/README.md)와 로컬 재개용 체크포인트 |
| `analysis/reports/compact_10_type_classification/` | 현재 729건·10개 유형 분류표 |
| `analysis/reports/prompt_clarity_audit/` | 실제 입력과 명확·조건부 사례 비교 |
| `docs/` | 실행 안내와 기존 테스트 보고서 |
| `archive/data_review_2026-10-19/` | 이전 분류표·중간 산출물의 로컬 보관본 |

일회성 분석 스크립트와 해당 바이트코드 캐시는 삭제했습니다. 분류표·보고서는 보존했으며,
`archive/`는 Git 추적 대상에서 제외합니다. 실험 실행에는 필요하지 않습니다.

## 현재 작업: zero-shot 2회 추가

기존 2023~2025년 실행 설정을 읽어 E0만 추가 2회 실행합니다.
이 명령은 config.json이나 config.openrouter*.json 대신 기존 결과의 manifest.json을 읽습니다.
저장된 Claude 모델 ID, 2023~2025년, 최대 출력1000토큰, timeout120초, 최대3회 시도,
재시도 간격1초와 기존 시스템/사용자 프롬프트를 유지합니다. 새 E5/E6 설정은 적용하지 않습니다.
자세한 재개·집계 방법은 [실행 안내](docs/RUN_ZERO_SHOT_REPEATS.txt)를 참고하세요.

```powershell
python -m residue_experiment.zero_shot_repeats --mode dry-run
python -m residue_experiment.zero_shot_repeats --mode live --approve-paid-api
python -m residue_experiment.zero_shot_repeats --mode analyze
```

각 추가 회차는 210문제이며, 기존1회와 합쳐 3회 오답은 핵심 분석,
2회 오답은 보조 분석으로 집계합니다. 유효 응답이 부족하면 미완료로 표시합니다.

## 기본 실험: 공통 예시를 사용하는 네 조건

새 remain 실험 설정의 평가 연도는 2023~2025, seed는 42입니다.

| 조건 | 예시 수 | 선정 방법 | 70문제에서의 사용 |
|---|---:|---|---|
| E0 | 0 | 예시 없음 | 전체 문제에 예시 없음 |
| E1 | 4 | 전년도 remain에서 무작위 | 같은 4개와 순서 고정 |
| E5 | 4 | 테스트 70개 전체와의 평균 TF-IDF cosine 상위 4개 | 같은 4개와 순서 고정 |
| E6 | 4 | 목적×대상 네 조합 + 판정 근거 다양성 우선순위 | 같은 4개와 순서 고정 |

E5는 이제 문제별 검색이 아닙니다. 테스트 입력 전체를 참조하는 transductive 선정이며,
테스트 정답은 선정에 사용하지 않습니다. 이 입력 접근 조건을 연구 보고에 명시하세요.
이전 버전의 문제별 E5 결과와 같은 조건으로 합치지 마세요.
E5는 목적·대상·라벨 균형을 강제하지 않아 같은 그룹이나 농약이 여러 번 선택될 수 있습니다.
E6에만 목적×대상 네 조합을 필수 적용합니다. Yes/No 균형은 강제하지 않습니다.

## 설치와 공통 코드 버전

```bash
python -m venv .venv
source .venv/bin/activate
# Windows에서는 .venv\Scripts\activate
python -m pip install -e ".[api,test]"
python -m pytest -q
```

세 담당자는 같은 Git 커밋·CSV·주석 파일·패키지 버전을 사용해야 합니다.
API 키나 .env를 공유·커밋하지 마세요. .env와 SQLite 체크포인트는 Git에서 제외됩니다. 결과 CSV와 manifest는 Git으로 관리합니다.

## 세 사람이 모델 하나씩 실행

`--provider`로 담당 모델 하나만 선택하면 models와 model_env를 함께 필터링합니다.
다른 담당 모델의 키·모델 ID는 필요하지 않습니다. 옵션을 빼면 설정의 모든 모델을 실행합니다.

```bash
# GPT 담당: 2024년 무료 계획 검증
python -m residue_experiment.cli --config config.openrouter.yearly-remain.json --provider openai --year 2024 --mode dry-run --output results/remain-v2/gpt-6-sol/2024/dry-run
# Claude 담당
python -m residue_experiment.cli --config config.openrouter.yearly-remain.json --provider anthropic --year 2024 --mode dry-run --output results/remain-v2/claude-opus-5.5/2024/dry-run
# Gemini 담당
python -m residue_experiment.cli --config config.openrouter.yearly-remain.json --provider gemini --year 2024 --mode dry-run --output results/remain-v2/gemini-3.8-flash/2024/dry-run
```

모델 하나·연도 하나·seed 하나에서는 4조건×70문제=280건입니다.
3년이면 담당자당 840건, 세 명 합계 2,520건이며 재시도는 별도입니다.
각 담당자는 examples.csv의 예시 ID·순서가 일치하는지 확인합니다.

## 데이터와 정답 분리

ESFA_YYYY70.csv는 테스트 70문제, ESFA_YYYY70answerkey.csv는 정답지,
ESFA_YYYY_remain.csv는 예시 후보입니다. 평가 연도 t의 후보는 달력상 t−1의 remain만 사용합니다.
과거 테스트 정답지를 예시 후보에 합치지 않습니다.

모델 입력은 substance, purpose, commodity, JMPR, EU 다섯 필드입니다.
선택된 과거 예시에는 EFSA 정답을 추가하지만 테스트에는 정답·코멘트·별도 source 정보·ID·연도를 넣지 않습니다.
EU 본문 안의 출처 설명은 보존합니다. 선정기에 전달하는 테스트 데이터도 입력 다섯 필드뿐입니다.

CSV 구조, 필수값, 연도, 정확한 Yes/No, 중복 ID, 테스트/정답지의 ID·입력 일치를 검사합니다.
테스트는 70건이어야 합니다. remain과 같은 연도 테스트/정답지의 ID가 겹치면 중단합니다.
같은 ID의 동일 예시 행은 기록 후 중복 제거하며, 내용·라벨이 충돌하면 중단합니다.
2020년 자료가 없어 2021년에는 전년도 후보가 없고 E1/E5/E6가 제외됩니다.
2018년도 2017년 자료가 없어 같습니다. 다른 과거 연도로 자동 보충하지 않습니다.
동봉한 E6 주석은 후보 연도2022~2024만 지원하므로 다른 연도는 주석 추가 전까지 E6를 제외합니다.
같은 농약이나 정의가 여러 연도에 반복되는 것은 현재 시간 분할에서 허용합니다.

## E5: 전체 평균 유사도

1. 전년도 remain의 다섯 입력 필드를 JSON 텍스트로 만들어 그 후보에만 TF-IDF를 fit합니다.
2. 현재 연도 테스트 70문제의 입력을 transform하고 70×후보 수의 cosine 유사도 행렬을 계산합니다.
3. 각 후보와 70문제 사이의 유사도를 평균합니다.
4. 평균이 높은 순서로 4개를 선택합니다. 동점은 ID 오름차순입니다.
5. 네 예시를 평균 유사도 순서로 전체 70문제에 공통 사용합니다.

의미 임베딩이 아닌 단어 기반 방식입니다. 정답·코멘트는 유사도에 사용하지 않습니다.
전체에서 한 세트를 고르므로 개별 문제에 대한 최적 적합이나 예시 간 다양성을 보장하지 않습니다.

## E6: 합의한 우선순위의 4-shot

priority_annotations.json에는 후보 연도2022/2023/2024의 remain 전체 80행에 대한 입력 특징 주석이 있습니다.
이는 아시스턴트가 정리한 초기 주석이며 전문가 확인 완료를 뜻하지 않습니다.
팀에서 태그·세부 특징·복잡도를 검토하고 같은 파일을 고정한 뒤 live 실험을 진행하세요.
기존 Yes/No를 재판정하지 않으며 주석 생성에는 테스트 입력·정답·코멘트를 사용하지 않았습니다.

1. Enforcement/Risk assessment × Plant/Animal의 각 조합에서 하나씩 고르는 모든 세트를 비교합니다.
2. 다섯 분류 태그의 커버 수, 그다음 세부 판정 특징의 커버 수를 최대화합니다.
3. 그다음 서로 다른 농약 수를 최대화하고 동일 판정 특징의 중복을 최소화합니다.
4. 같은 정보를 준다면 주석의 복잡도 합, 그다음 정의 본문 길이 합을 최소화합니다.
5. 모든 지표가 같은 세트는 고정 seed로 선택하고 최종 예시 순서도 seed로 고정합니다.

가중 합산이 아니라 앞선 기준을 먼저 만족시키는 사전식 비교입니다.
주분류는 compound(화합물 대응), scope(포함 범위), expression(표현 기준),
application(적용 조건), status(법적·제안·잠정 등의 상태)입니다.
세부 특징은 같은 다섯 태그 안에서도 서로 다른 판단을 구별합니다.
복잡도는 0=단일 모화합물, 1=단순 조건, 2=대사체·환산·예외, 3=복수 정의·시점·조직 조건입니다.
태그와 복잡도는 정보성의 대리지표이며 실제 모델 성능이나 엄밀한 정보이론량은 아닙니다.
태그·이유는 선정 및 감사용이며 모델에 보내지 않습니다. 모델에는 과거 예시 입력 다섯 필드와 정답만 보냅니다.

전년도 remain의 모든 후보에 주석이 필요합니다. 누락·형식 오류·네 조합 부족이면 E6를 제외하고 임의 보충하지 않습니다.
selection_audit.json에 선정 ID·태그·이유·목적함수를, manifest에는 주석 파일 해시를 저장합니다.
과거 오답 분석을 참고해 설계했으므로 이미 확인한 테스트는 개발 근거이며 미참조 최종 평가와 구별합니다.

## API 설정과 실행

새 remain 실험은 config.openrouter.yearly-remain.json(OpenRouter) 또는 config.json(공식 API)을 사용합니다.
기존 config.openrouter.json은 main의 Claude 전용 설정을 유지합니다. 새 네 조건 실험과 구분하세요.
기존 E5와 새 E5는 선정 방식이 다르므로 예전 결과와 새 결과를 합쳐 비교하지 않습니다.
data_dir와 priority_annotations는 설정 파일 기준 상대 경로입니다.
정확한 모델 ID를 지정하세요. 환경변수는 설정 파일과 같은 폴더의 .env에서 읽으며 기존 환경값을 덮어쓰지 않습니다.
OpenRouter 예시:

```dotenv
OPENROUTER_API_KEY=your_key
GPT_MODEL=exact_openai_model_id
CLAUDE_MODEL=exact_anthropic_model_id
GEMINI_MODEL=exact_google_model_id
```

공식 API 키는 OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY입니다.
공식 설정의 models가 비어 있으므로 실행 전에 담당 모델 ID를 설정해야 합니다.
모델 기본 생성 설정을 사용하고 temperature는 명시하지 않습니다.
매 문제는 독립 API 요청이며 과거 응답·대화 이력·채점 결과를 누적하지 않습니다.
OpenAI Responses는 store=False이고 previous_response_id 등을 보내지 않습니다.

```bash
# API 호출과 SDK 클라이언트 생성 없이 계획 검증
python -m residue_experiment.cli --config config.openrouter.yearly-remain.json --provider openai --year 2024 --mode dry-run --output results/remain-v2/gpt-6-sol/2024/dry-run
# 가상 응답으로 저장·채점 검증. 실제 모델 성능이 아님
python -m residue_experiment.cli --config config.openrouter.yearly-remain.json --provider openai --year 2024 --mode mock --output results/remain-v2/gpt-6-sol/2024/mock
# 실제 과금 실행은 사용자 승인 후에만
python -m residue_experiment.cli --config config.openrouter.yearly-remain.json --provider openai --year 2024 --mode live --approve-paid-api --output results/remain-v2/gpt-6-sol/2024/live
```

응답은 앞뒤 공백 제거 후 정확히 Yes/No여야 합니다. 설명이나 대소문자 차이는 형식 오류입니다.
잘못된 응답·통신 오류는 최대 3회 시도하며 기본 대기 간격은 1초·2초입니다. 오답이라는 이유로 재시도하지 않습니다.
SDK 자체 재시도는 비활성화합니다. 이번 변경 검증에서 실제 모델 API를 호출하지 않았습니다.

## 재개와 신규 실행

--year 2025로 연도를 지정하고 --seed 123으로 무작위 선정/E6 동점 처리·순서를 변경할 수 있습니다.
같은 seed는 같은 예시를 재현합니다. E5는 seed와 무관하게 전체 평균으로 한 번 선택합니다.
--output을 생략하면 매번 타임스탬프의 새 폴더를 만듭니다.
같은 --output을 지정하면 같은 설정·데이터·코드의 실행을 SQLite에서 재개합니다.
성공한 문제는 다시 호출하지 않고 미완료·오류만 재개합니다. --fresh는 새로운 하위 폴더를 만듭니다.
코드·설정·데이터·주석이 달라지면 기존 결과와 혼합하지 않도록 재개를 거부합니다.
한 폴더는 한 프로세스만 사용하세요. 새 E5/E6는 이전 결과 폴더를 재사용하지 마세요.
서버 응답과 로컬 저장 사이에 중단되면 재개 시 같은 요청이 다시 과금될 수 있습니다.

## 결과와 팀 집계

| 파일 | 내용 |
|---|---|
| validation.csv / data_issues.csv | CSV 해시·건수·검증 기록 |
| selection_audit.json | E5 전체 후보 평균 유사도, E6 태그·이유·목적함수 |
| examples.csv | 문제별 예시 ID·연도·정답·순서·평균 유사도 |
| prompts.jsonl | 모델에 보내는 사용자 프롬프트. 테스트 정답 제외 |
| predictions.csv | 정답·예측·상태. 정답은 로컬 채점용 |
| metrics.csv | 조건/seed별 Accuracy·Precision·Recall·Macro-F1·혼동행렬·coverage |
| comparison.csv | 완료한 반복만의 평균·표준편차 |
| exclusions.csv | 전년도·주석 부족 등에 따른 제외 사유 |
| api_calls.csv / api_errors.csv | 요청 기록·응답·토큰·시간·오류 |
| manifest.json | 설정·모델·입력/주석 해시·시스템 지침 |
| checkpoint.sqlite | 재개용 전체 계획·상태 |

Precision/Recall은 Yes를 양성, Macro-F1은 Yes/No 같은 비중, 혼동행렬은 행=실제·열=예측의 [No,Yes] 순서입니다.
실패·제외를 임의 정답/오답으로 바꾸지 않습니다. 성공 응답만 채점하므로 coverage/complete도 확인하세요.
단일 seed의 표준편차0은 변동성이 없다는 뜻이 아닙니다. dry-run은 예측·성능이 공란입니다.
세 담당자는 같은 문제 ID·예시 순서·파일 해시를 확인한 뒤 모델×연도×조건 성능을 비교하세요.
세 담당자의 결과 폴더를 자동 통합하는 기능은 아직 없습니다.

## 기존 추가 조건

E2는 전년도 Yes2/No2, E3는 2년 전 Yes2/No2, E4는 전년도/2년 전에서 Yes1/No1씩입니다.
새 remain 실험의 기본 비교에는 포함하지 않습니다.

## GitHub 반영

제공된 코드 패키지의 새 파일을 `CNU-graduate/experiment` 체크아웃에 복사하세요.
원본 CSV는 변경하거나 다시 업로드할 필요가 없습니다.

```bash
git switch -c feat/residue-few-shot
# 제공된 residue_experiment/, tests/, README.md, config.json,
# pyproject.toml, .env.example, .gitignore를 복사
python -m pytest -q
git add residue_experiment tests README.md config.json pyproject.toml .env.example .gitignore
git diff --cached --stat
git commit -m "Implement temporal EFSA-JMPR few-shot experiments"
git push -u origin feat/residue-few-shot
```

CSV 변경이 없는지 `git diff -- '*.csv'`로 확인하세요. 실제 유료 API 호출은 실행하지 않았습니다.
API 통합 테스트도 SDK 네트워크 메서드를 Mock으로 대체합니다.

## E7 고정 4-shot 반복 실험

오류 분석 기반 고정 예시를 사용하는 E7 실행 방법은 [E7 안내](docs/RUN_E7.md)를 확인하세요. 현재 저장된 자료는 3회 합계 630건의 dry-run 실행 계획이며 유료 모델 응답이 아닙니다.
