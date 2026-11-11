# E6＋보완 지침: 2026년 86문제 전체 최종 평가

원본 86문제 전부를 3회 평가한다(258 정상 요청, 오류 재시도 별도).
2026-14-01·2026-22-01도 포함하며, 과거 자료와 입력 중복임을 결과에 명시한다.
기존 E6＋보완 지침 시스템 프롬프트는 변경하지 않는다.
E6 예시는 2025년 remain의 12개 후보에서 기존 목적×대상 우선순위 로직과 seed 42로 선정한다.
누락되어 있던 2025년 태그는 `priority_annotations.2025-final.json`에 별도로 작성했다.
태그는 2025년의 입력 정의만을 바탕으로 작성했고 2026년 정답·오답을 보고 선정하지 않았다.
이 태그와 예시 선정 결과는 live 전에 plan.json으로 고정하며 평가 후 수정하지 않는다.

## 정답 분리

모델 요청의 test 객체에는 substance, purpose, commodity, JMPR, EU만 포함한다.
2026년 EFSA 정답, efsa_comments, 출처 URL, 섹션·표 번호, ID, 연도는 보내지 않는다.
예시 4개에는 2025년 정답을 포함한다(few-shot 방식). 2026년 정답은 로컬 채점에만 사용한다.
모델에 도구·브라우저·파일 접근을 제공하지 않는다. 정의 본문에 이미 포함된 표현은 원본대로 유지한다.
새 86건 로더는 2026년 파일에만 적용하고 기존 70건 검증은 유지한다.

## 실행

```bash
git fetch origin
git switch feat/e6-guided-final-2026
git pull --ff-only origin feat/e6-guided-final-2026
python -m residue_experiment.e6_final_2026 --mode dry-run
python -m residue_experiment.e6_final_2026 --mode live --approve-paid-api
```

live는 기존 `.env`의 OPENROUTER_API_KEY를 사용한다. 키를 채팅이나 GitHub에 올리지 않는다.
기존 모델 `openai/gpt-6-sol` 및 요청 설정을 그대로 사용한다. 키가 없으면 유료 호출 전에 중단한다.
중단 후 같은 live 명령으로 재개하면 저장된 완료 응답은 재사용한다. 중단 시 처리 중이던 요청은 중복 과금 가능하다.
동시에 두 번 실행하지 않는다. 평가 중 코드·입력·태그를 변경하지 않는다.

저장된 결과만 재분석(API 호출 없음):

```bash
python -m residue_experiment.e6_final_2026 --mode analyze
```

출력: `results/e6-guided-final-2026-v1/gpt-6-sol/`.
plan.json에 데이터·코드·태그 해시와 예시 ID를 기록한다. live/analysis에 회차별 지표, 평균·표준편차, 오답 빈도를 저장한다.
SQLite는 재개용이며 Git에 올리지 않는다.

```bash
git add results/e6-guided-final-2026-v1/gpt-6-sol
git commit -m "results: add E6 guided final evaluation on all 86 cases from 2026"
git push origin feat/e6-guided-final-2026
```

입력·정답지의 형식 일치 검증은 정답 자체의 독립적인 전문 검증을 의미하지 않는다.
86건은 독립 입력 기준 84건의 신규 입력과 2건의 과거 입력 중복을 포함한다.
