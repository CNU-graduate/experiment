# v2 최종 지침의 2024·2025년 평가

v2 live에서 확정된 R4C2와 원래 P0를 고정하여 두 연도의 70문제를 각각 3회 평가한다.
프롬프트 생성·탐색은 하지 않는다. 모델과 호출 설정은 v2 실행 계획에서 가져온다.
기존 2023년 결과와 호출 기록은 수정하지 않는다.

프로젝트 루트 PowerShell:

```powershell
python -m residue_experiment.prompt_transfer prepare
python -m residue_experiment.prompt_transfer run --mode live --max-calls 840
```

prepare는 API를 호출하지 않는다. v2의 최종 지침이 마지막 라운드의 승자와 같은지
확인하고 P0·최종 지침·평가 자료·모델 설정을 새 plan.json에 고정한다.
동일 계획으로 prepare를 다시 실행할 수 있지만 계획이 달라지면 새 출력 폴더가 필요하다.
실제 실행은 `.env`의 OPENROUTER_API_KEY를 사용한다.

추가 호출은 70문제 × 2지침 × 3회 × 2년 = 840회이며, 이전 3,370회와 별도 예산이다.
동일 run 명령을 다시 실행하면 성공한 호출을 재사용한다. 오류나 중단된 호출은
자동 재시도하지 않는다. 동시 실행은 mode별 잠금으로 차단한다.
로그를 확인하지 않고 오류 호출 기록을 삭제하면 중복 과금될 수 있다.

오프라인 전체 흐름 확인:

```powershell
python -m residue_experiment.prompt_transfer run --mode mock --max-calls 840
```

mock과 live는 폴더·캐시가 분리되며 mock 정확도는 실제 성능이 아니다.

결과 위치는 `results/prompt-search-v2-transfer-2024-2025/live/`이다.
`2024/`, `2025/` 폴더에 각각 `test_predictions.csv`, `test_metrics.csv`,
`test_changes.csv`, `test_summary.json`을 저장한다. 최상위 `summary.json`에는
연도별 평균 정확도·Macro-F1, FP/ FN 합계를 저장하고 `calls/`에는 호출 기록을 남긴다.
연도·조건·반복마다 독립 호출하며 정답은 채점에만 사용한다.

한 번씩 예비 평가하려면 별도 계획을 만든다:

```powershell
python -m residue_experiment.prompt_transfer prepare --repeats 1 --output results/prompt-search-v2-transfer-once
python -m residue_experiment.prompt_transfer run --output results/prompt-search-v2-transfer-once --mode live --max-calls 280
```

`--years`, `--repeats`, `--source`는 prepare 단계에서 지정하며 run은 저장된 계획을 사용한다.
연도 하나만 지정하려면 prepare에 `--years 2024` 또는 `--years 2025`를 전달하고 새 출력 폴더를 쓴다.

현재 자료 기준 2024년에는 과거 개발·선택 자료와 완전히 같은 입력이 없고,
2025년에는 2025-11-01, 2025-21-01 두 문제가 겹친다. plan.json의 past_input_overlap에 기록한다.
전체 70개는 유지한다. 입력 중복과 다른 실험에서 해당 연도를 사용한 이력을 고려하여
완전히 미사용한 독립 평가라고 단정하지 않는다.
