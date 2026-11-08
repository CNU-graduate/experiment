# J1: 목적별 지침 자동 분기, 2023~2025년 각 70문제 × 3회

브랜치: `feat/e6-j1-purpose-routing`. main에는 올리거나 병합하지 않는다.

## 설계

J1은 하나의 평가 전략이다. 테스트의 기존 `purpose` 값으로 시스템 지침만 분기한다.

| purpose 값 | 경로 | 시스템 지침의 초점 | 연도 전체 문제 수 |
|---|---|---|---:|
| Enforcement | J1-E | 적용 가능한 단속 정의의 출처를 분리하고, 별도 평가서 성분을 규정 정의에 합치지 않음 | 119 |
| Risk assessment | J1-R | 위해평가 정의의 화학적 포함 범위와 합산·독립 평가 구조를 분리해 비교 | 91 |

두 경로의 문제는 겹치지 않으며 합쳐 210문제다. 매 회차 각 연도 70문제를 모두 평가하고,
3회 합계는 **630건**이다. J1-E/J1-R을 각각 210문제에 실행하는 설계가 아니다.
예외적 purpose는 임의 라우팅하지 않고 사전 검증에서 거부한다.
이미 주어진 목적을 사용하는 것이므로 목적을 추론하는 별도의 분류기/API는 없다.

E6 예시의 ID·순서·본문·정답은 고정하고 네 예시를 모두 보존한다. 예시를 목적별로 다시 고르거나
같은 목적의 예시만 남기지 않는다. 각 요청은 해당 목적 system 하나와 기존 user 하나를 사용한다.
이전 응답이나 다른 문제의 대화는 누적하지 않는다. 정답과 EFSA 코멘트는 테스트에 추가하지 않는다.

정확한 영문 지침은 `residue_experiment/e6_j1.py`에 고정한다.
단속 지침은 V2 연장 탐색 R6C1의 조건부 출처 분리 문구를 참고했다.
위해평가 지침은 기존 E6-guided/H1/G1에서 관찰한 합산·독립 평가 문제를 고려했다.
특정 농약명·문제 ID·테스트 정답은 지침에 포함하지 않는다.
단속용 지침도 '항상 규정 우선'이라는 일반 원칙을 단정하지 않는다.
위해평가에서 단속 규정의 일치만으로 Yes를 선택하지 않는다.

OpenRouter `openai/gpt-6-sol`, seed 42, 출력1000토큰, timeout120초, 최대3시도를 유지한다.
GPT_MODEL 환경변수는 모델 ID를 바꾸지 않는다. 실제 과금은 630건과 오류 재시도에 발생한다.
과거 E6/E6-guided 결과는 읽기만 하며, C0·H1·V2·기존 E6는 새로 호출하지 않는다.
순서: 1회차 E→R, 2회차 R→E, 3회차 E→R. 각 블록 안에서는 기존 문제 순서를 유지한다.

## VS Code 실행

기존 Python 환경을 활성화한 뒤 저장소 루트에서:

```bash
git fetch origin
git switch feat/e6-j1-purpose-routing
git pull --ff-only origin feat/e6-j1-purpose-routing
python -m pip install -e ".[api,test]"
python -m residue_experiment.e6_j1 --mode dry-run
```

무료 실행은 `cases: 630`, `calls: 0`, `runs: 6`이면 정상이다.
임시 사전 계획에서 과거 E6/E6-guided와 입력·예시·ID·라벨·순서·주석·모델 설정을 대조한다.
purpose별 하위 집합이 정확히 전체210개를 분할하는지도 확인하며 SDK를 만들지 않는다.

사용자가 유료 실행을 의도할 때만 기존 `.env`의 OPENROUTER_API_KEY로:

```bash
python -m residue_experiment.e6_j1 --mode live --approve-paid-api
```

필요하면 `--round 1` 등으로 한 회차만 지정할 수 있다. 전체 실행은 3회다.
새 결과는 `results/e6-j1-purpose-v1/gpt-6-sol/2023-2025/`에 저장한다.
회차별 `live/J1-E/round-01`, `live/J1-R/round-01` 등으로 분리한다.
원시 CSV condition은 E6 선정기 호환용 E6이며, 신규 전략·분기는 plan과 manifest의
config.j1_route/case_purpose 및 분석 결과의 J1/purpose 열로 구별한다.

## 재개와 집계

같은 컴퓨터에서 같은 명령으로 재개한다. 로컬 checkpoint.sqlite에 저장된 성공 요청은 재사용한다.
체크포인트는 Git에 올리지 않고 실행 컴퓨터에 보존한다. CSV만 다른 컴퓨터에서 받아서 live를
실행하면 재호출될 수 있다. 서버 응답과 저장 사이 중단은 중복 과금 가능성이 있다.
한 결과 루트는 한 프로세스만 사용하고 실행 중 코드를 업데이트하지 않는다.
코드/지침/입력/기준 결과가 변경되면 재개를 거부한다. 프로세스 종료 확인 전 lock을 지우지 않는다.

저장된 결과만 무료 재집계:

```bash
python -m residue_experiment.e6_j1 --mode analyze
```

- plan/system_prompts: 두 지침, 목적별 문제수, 입력/코드/기준 결과 해시.
- analysis/condition_summary.csv: J1 및 과거 전체 보완 지침의 연도별·목적별·전체 평균과 표본표준편차.
  전체 결과는 `condition=J1, year=all, purpose=all` 행이다.
- round_metrics.csv: 회차별 지표·FP/FN·coverage·complete. 전체 Macro-F1은 전체 문제를 모아 계산하며
  목적별 F1을 단순 평균하지 않는다.
- error_frequency.csv: 문제별 목적, 과거 보완 지침과 J1의 오답 횟수, 회차별 예측.
- comparison.csv: 과거 반복 오답 복구와 기존 안정 정답 훼손. J1 3회 미완료는 판정하지 않는다.
- resources.csv: 목적 경로별 API 시도/실패/미완료. 응답 원문·usage는 회차별 api_calls.csv.

J1은 라우팅과 두 프롬프트 재작성을 함께 바꾸므로 '목적 분기만의 순수 효과'를 입증하지 않는다.
기존 결과와 실행 시점이 다르고 동일 210문제를 개발에 사용했다. 전체 정확도와 목적별 성능,
기존 정답 훼손을 함께 보고하고, 과거 문제의 개선만으로 일반화를 주장하지 않는다.
후속 연구에서는 미검토 자료 및 지침 내용/분기 효과를 분리하는 대조 조건이 필요하다.

## 결과 GitHub 업로드

```bash
git branch --show-current
git add results/e6-j1-purpose-v1/gpt-6-sol/2023-2025/
git diff --cached --stat
git commit -m "results: add J1 purpose-routed three-round results"
git push origin feat/e6-j1-purpose-routing
```

키·SQLite·잠금 파일이 포함되지 않았는지 확인하고 main에는 push하지 않는다.
