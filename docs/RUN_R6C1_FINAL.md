# R6C1의 2023~2025년 고정 지침 평가

8라운드에서 조기 종료된 연장 탐색의 최종 지침 R6C1을 사용한다.
P0와 R6C1 각각 연도별 70문제에 대해 3회 평가한다. 후보 생성이나 추가 최적화는 하지 않는다.
기존 R4C2 평가 결과와 별도 폴더에 저장한다.

계획 준비(유료 호출 없음, 현재 준비 완료):

```powershell
python -m residue_experiment.prompt_transfer prepare --source results/prompt-search-v2-continued-patience2 --output results/prompt-search-r6c1-eval-2023-2025 --years 2023 2024 2025 --repeats 3
```

유료 실행:

```powershell
python -m residue_experiment.prompt_transfer run --output results/prompt-search-r6c1-eval-2023-2025 --mode live --max-calls 1260
```

총 70 × 3년 × 2지침 × 3반복 = 1,260회. 기존 실험의 P0 응답은 가져오지 않고 이번 평가에서 새로 실행한다.
동일 출력 폴더에서 재개할 때는 완료된 응답을 재사용한다. 미완료 호출이나 잘못된 응답이 있으면 확인 후 복구해야 한다.
실행 중 동일 명령을 중복 실행하거나 잠금 파일을 삭제하지 않는다.

전체 요약: `results/prompt-search-r6c1-eval-2023-2025/live/summary.json`
연도별 예측·지표·신규 오답: 같은 폴더의 `2023`, `2024`, `2025` 아래 `test_predictions.csv`, `test_metrics.csv`, `test_changes.csv`, `test_summary.json`.

과거 분석에 사용한 평가 자료이므로 완전히 미사용한 평가 자료로 기술하지 않는다.
계획의 입력 중복 검사에서 2025-11-01, 2025-21-01은 개발/선택 자료와 동일한 입력으로 표시됐다. 기존 평가와의 비교를 위해 유지하며 결과 해석에 명시한다.
