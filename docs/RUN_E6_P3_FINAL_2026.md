# 기본 E6와 P3의 2026년 후속 비교

| 조건 | 지침 | 예시 |
|---|---|---|
| E6 | 기존 기본 SYSTEM 원문, 보완 문단 없음 | 앞선 2026 E6＋보완 지침 평가와 같은 2025년 4개 |
| P3 | 기존 독립 P3 원문 | 없음(zero-shot) |

두 조건 모두 2026년 86문제 전체를 각각 3회 평가한다. 총 516 정상 요청이며 재시도는 별도다.
기존 E6＋보완 지침 결과는 다시 실행하거나 덮어쓰지 않는다.
E6 대 보완 지침 비교는 예시·설정을 맞춘 과거 실행 비교이며 실행 시점 차이는 남는다.
E6와 P3는 지침과 예시 유무가 함께 달라서 단일 요소의 효과로 해석하지 않는다.
2026년 보완 지침 결과를 확인한 뒤 추가한 후속 비교이며, 새로 확보한 독립 테스트라고 부르지 않는다.
2026년 정답·코멘트·출처는 모델에 전송하지 않는다. test는 입력 5개 필드만 포함한다.
과거 입력과 겹치는 2문제도 포함해 86문제 전부 평가하며 중복 사실을 명시한다.
선정 태그·프롬프트·평가 파일을 평가 중 수정하지 않는다.

```bash
git fetch origin
git switch feat/e6-p3-final-2026
git pull --ff-only origin feat/e6-p3-final-2026
python -m residue_experiment.e6_p3_final_2026 --mode dry-run
python -m residue_experiment.e6_p3_final_2026 --mode live --approve-paid-api
```

live는 기존 `.env`의 OPENROUTER_API_KEY를 사용한다. 키를 GitHub나 채팅에 올리지 않는다.
중단 후 같은 live 명령으로 재개한다. 저장된 완료 응답은 재사용하고 중단 순간 처리 중인 요청은 중복 과금될 수 있다.
동일 명령을 동시에 두 번 실행하지 않는다.

저장된 결과만 재분석(API 호출 없음):

```bash
python -m residue_experiment.e6_p3_final_2026 --mode analyze
```

출력: results/e6-p3-final-2026-v1/gpt-6-sol/.
상위 live/analysis의 condition_summary.csv와 error_comparison.csv에서 평균·표준편차와 문제별 오답 빈도를 비교한다.
각 E6/P3 하위에는 원문 응답, 프롬프트, 예시, 회차별 결과가 저장된다.

```bash
git add results/e6-p3-final-2026-v1/gpt-6-sol
git commit -m "results: compare original E6 and P3 on 2026 cases"
git push origin feat/e6-p3-final-2026
```
