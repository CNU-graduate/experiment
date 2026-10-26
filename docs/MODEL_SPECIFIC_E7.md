# GPT·Gemini 개별 제로샷 오류에 기반한 E7

## 기존 계획과의 차이

기존 `results/error-informed/`의 GPT·Gemini 계획은 Claude에서 도출한 예시를 공통 사용했다.
이 문서와 `results/error-informed-personalized/`는 모델별 제로샷 결과에서 새로 선정한 별도 조건이다.
Claude 코드·예시·결과와 기존 공통 계획은 변경하지 않는다. 유료 API는 실행하지 않았다.

## 실제 근거

- GPT: baseline E0를 1회차로, zero-shot-repeats의 round-02/03을 2·3회차로 사용.
  각 210건 성공. 3회 오답 11문제 중 No→Yes 1문제, Yes→No 10문제.
  2회 오답 4문제, 1회 오답 4문제, 항상 정답 191문제.
- Gemini: zero-shot-repeats의 round-01/02/03을 사용. baseline을 중복 추가하지 않음.
  각 210건 성공. 3회 오답 8문제 중 No→Yes 2문제, Yes→No 6문제.
  2회 오답 4문제, 1회 오답 2문제, 항상 정답 196문제.

완성된 세 회차의 predictions를 직접 집계하고 원본 경로·SHA256을 계획에 저장한다.
각 모델의 2023~2025 전체 오류로 방향을 정하므로 탐색적 사후 개선 실험이다.

## 모델별 선정 논리

GPT 핵심 오류는 출처·적용 범위에 의존하는 Yes 5개, 명칭·코드·이성질체 대응 Yes 4개,
Mancozeb No 1개, 근거 검토가 필요한 Tebuconazole Yes 1개다.
따라서 Yes 두 개는 출처·범위와 표현 대응을 교정하는 직접 사례로 구성한다.
추가 성분 No는 GPT 핵심 오류의 빈번한 유형이라고 주장하지 않고 Yes 편향 방지용으로 둔다.

Gemini 핵심 오류는 출처·적용 범위 Yes 4개, 포합체 범위 No 1개, Mancozeb No 1개,
조건부 명칭 대응 Yes 1개, 검토 필요 Tebuconazole Yes 1개다.
따라서 출처 의존 Yes를 우선하며 포합체 No도 반영한다.
2024년 remain에는 해당 포합체 차이를 직접 보여주는 적합 No가 없어 2025년용은
추가 대사체 집합 차이로 대체하고 직접 대응하지 못한 점을 기록한다.

기존 Claude의 Y1(복합 정의 대응)을 그대로 유지한 동일 선정 규칙은 아니다.
두 모델에서는 Y1을 출처·적용 범위·현재 상태를 구별하는 대응 Yes로 재정의했다.
조건부 사례를 제외하면 주된 오류를 대표하지 못하므로 명확한 한정 범위를 기록한 채 사용한다.
이는 전문가 검증 완료를 의미하지 않는다. 기존 원본 라벨을 바꾸지 않는다.

## 고정 예시: N1 → Y1 → N2 → Y2

각 모델·연도별 Yes 2개·No 2개, 전년도 remain에서 서로 다른 사례 4개를 고른다.
ID를 다르게 만들기 위해 다른 후보를 강제하지 않는다. 오류가 겹치면 선정도 겹칠 수 있다.

| 모델 | 평가 연도 | N1 No | Y1 Yes | N2 No | Y2 Yes |
|---|---|---|---|---|---|
| GPT | 2023 | 2022-16-03 Difenoconazole | 2022-17-04 Mandipropamid | 2022-10-03 Fipronil | 2022-13-02 Trifloxystrobin |
| GPT | 2024 | 2023-20-02 Flupyradifurone | 2023-09-02 Famoxadone | 2023-21-02 Quinclorac | 2023-08-01 Bifenthrin |
| GPT | 2025 | 2024-03-04 Thiophanate-methyl | 2024-06-04 Zeta-cypermethrin | 2024-21-04 Cyantraniliprole | 2024-01-04 Pyrethrins |
| Gemini | 2023 | 2022-16-03 Difenoconazole | 2022-20-04 Clothianidin | 2022-25-04 Bixafen | 2022-09-02 Fenbuconazole |
| Gemini | 2024 | 2023-20-02 Flupyradifurone | 2023-09-02 Famoxadone | 2023-21-02 Quinclorac | 2023-15-02 Mandipropamid |
| Gemini | 2025 | 2024-08-03 Diflubenzuron | 2024-06-04 Zeta-cypermethrin | 2024-21-04 Cyantraniliprole | 2024-23-04 Cyflumetofen |

역할과 이유의 전체 정의는 `scripts/model_specific_e7.json`에 저장한다.
출력의 `selected_examples.json`에는 원문 다섯 필드·정답·이유를 저장한다.
모델에는 원문 다섯 필드와 정답만 제공하고, 이유·역할·ID는 제공하지 않는다.

## 한계

- Mancozeb의 독성등가 가중과 별도 평가를 완전히 재현하지 못하며 구조적 유사 예시를 사용한다.
- Tebuconazole 2025-15-03은 원본 Yes이나 검토 필요다. 예시에서 제외하고, 평가 시 별도 구분이 필요하다.
- GPT의 Pyrethrins, 두 모델의 Famoxadone 등은 동일 물질의 연도 간 전이를 포함한다. 일반화와 구분한다.
- Maleic hydrazide의 free 표기와 이성질체 표기는 같은 화학적 차이가 아니다. 간접적인 표현 대응 예시다.
- 모델별 예시가 다르므로 동일 예시를 사용한 모델 성능 비교와 구분한다.

## 재실행: dry-run

```powershell
python -m scripts.run_model_specific_e7 --provider openai --mode dry-run
python -m scripts.run_model_specific_e7 --provider gemini --mode dry-run
```

각 모델 630건(210건×3회)을 별도 폴더에 저장한다.
`plan.json`, `zero_shot_analysis.json`, `selected_examples.json` 및 회차별 체크포인트를 참조한다.
전용 실행기는 해당 프로세스 안에서만 선정기를 교체하며 공유 residue_experiment 소스는 변경하지 않는다.
따라서 기존 Claude의 구현 fingerprint를 변경하지 않는다. 전용 실행기 해시와 선정 내용은 새 계획에 고정한다.
live는 별도 승인 후 `--mode live --approve-paid-api`를 사용한다. 이번에는 실행하지 않는다.
