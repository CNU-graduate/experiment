# K1·K2·K3: 목적별 지침의 통제 비교

| 조건 | 시스템 지침 | 반복 |
|---|---|---:|
| K1 | 기존 E6＋보완 지침 전체 원문 | 3 |
| K2 | J1의 단속용·위해평가용 원문을 모두 제공하고 입력 목적에 해당하는 모듈만 적용 | 3 |
| K3 | J1과 동일하게 입력 목적에 해당하는 지침 원문만 제공 | 3 |

2023·2024·2025년 각 70문제, 총 210문제를 조건마다 3회 평가한다.
**전체 평가 9회, 정상 요청 1,890건**이며 오류 재시도는 별도다.
연도별로 세면 70문제 평가 27회다. 목적별 처리 블록은 18개지만 전체 평가 횟수가 18회인 것은 아니다.
한 조건의 한 회차는 단속용 119문제와 위해평가용 91문제로 구성되며 중복 호출하지 않는다.
기존 J1 단독 실행(630건)을 추가로 실행할 필요가 없다.

## 통제와 해석

모델·요청 설정, 평가 정답, 입력 필드, E6의 전년도 예시 4개와 순서·정답은 동일하게 유지한다.
K1도 동일한 목적 블록으로 처리해 실행 구조를 맞추되 시스템 지침은 원문 그대로 유지한다.
조건 순서는 1회차 K1→K2→K3, 2회차 K2→K3→K1, 3회차 K3→K1→K2다.
단속·위해평가 처리 순서는 2회차에 반대로 배치한다. 세 회차는 서로 다른 표본 630개가 아니라 같은 210문제의 반복이다.

- K1↔K2: 목적별로 구체화한 새 지침 내용의 효과를 비교한다.
- K2↔K3: 동일한 지침 모듈을 함께 제공할 때와 해당 목적만 제공할 때를 비교한다. 모듈 선택 문구와 프롬프트 길이도 달라지므로 순수한 라우팅 알고리즘 효과라고 단정하지 않는다.
- K1↔K3: 최종 전략의 종합적인 차이를 비교한다.

주요 지표는 전체·연도별·목적별 정확도와 macro-F1의 3회 평균 및 표준편차다.
반복 오답 회복과 기존 안정 정답의 손상도 함께 본다. 미완료 실행은 완료 횟수·coverage로 구분한다.
기존 과거 결과는 각 조건 하위 분석에서만 historical로 표시하며, 상위 비교는 이번 K1/K2/K3 결과끼리 한다.
동일 물질의 관련 문제가 있어 개별 문제와 반복 응답을 모두 독립 표본으로 간주하면 안 된다.
이미 분석해 온 210문제이므로 개발 평가에 해당한다. 일반화 주장은 별도로 고정한 미사용 평가셋에서 확인해야 한다.

## 실행

저장소 루트에서 기존 가상환경을 활성화하고 의존성을 설치한다.

```bash
python -m pip install -e '.[api,test]'
python -m residue_experiment.e6_purpose_control --mode dry-run
```

위 명령은 API를 호출하지 않는다. 검증 출력은 cases=1890, calls=0, full_evaluations=9, purpose_subruns=18이다.
`.env`에 기존 OpenRouter 키를 설정한 뒤, 유료 실행을 원할 때 아래 명령을 실행한다.

```bash
python -m residue_experiment.e6_purpose_control --mode live --approve-paid-api
```

중단 후 같은 명령으로 이어서 실행하면 저장된 완료 응답은 재호출하지 않는다.
한 회차씩 실행하려면 `--round 1` / `--round 2` / `--round 3`을 붙인다. 각 회차는 세 조건 총 630건이다.
정상 실행 중 다른 프로세스를 동시에 실행하지 않는다. 코드·입력·지침이 바뀌면 기존 결과와 혼합하지 않고 중단한다.

```bash
python -m residue_experiment.e6_purpose_control --mode analyze
```

저장된 응답만으로 분석하며 API를 호출하지 않는다.
결과: `results/e6-purpose-control-v1/gpt-6-sol/2023-2025/`.
상위 `live/analysis/`의 condition_summary.csv, round_metrics.csv, error_frequency.csv, comparison.csv, resources.csv를 확인한다.
원문 응답·프롬프트·예시·manifest는 각 `K1|K2|K3/live/J1-E|J1-R/round-01..03/`에 보관한다.
SQLite 체크포인트와 실행 잠금 파일은 Git에 올리지 않는다.

## 결과 업로드

```bash
git branch --show-current
git add results/e6-purpose-control-v1/gpt-6-sol/2023-2025
git commit -m "results: add K1 K2 K3 purpose-controlled comparison"
git push origin feat/e6-purpose-controlled-comparison
```

현재 브랜치가 `feat/e6-purpose-controlled-comparison`인지 확인하고 실행한다. main에는 올리지 않는다.
