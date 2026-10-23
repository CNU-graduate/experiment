# Gemini 제로샷 3회 반복 결과

2023~2025년 각 70문제, 총 210문제를 회차마다 평가했습니다. 모델 ID는 `google/gemini-3.8-flash`입니다.

- `live/round-01/`: 기존 `results/remain-v2/gemini-3.8-flash/2023-2025` 실험에서 E0 응답 210건과 E0 지표만 추출했습니다. manifest.json은 원본 전체 E0·E1·E5·E6 실행의 메타데이터를 그대로 보존하므로 응답 파일의 범위보다 넓습니다.
- `live/round-02/`, `live/round-03/`: 로컬 `results/zero-shot-3-runs-gemini/live/round_2`, `round_3`의 실제 응답 및 실행 기록입니다.
- `analysis/`: 위 세 회차의 문제별 오답 빈도 및 연도별 집계입니다.

세 회차 모두 210건의 유효 응답이 있습니다. 3회 연속 오답은 8개(2023년 2개, 2024년 4개, 2025년 2개), 2회 오답은 4개(각 2개, 1개, 1개)입니다.

1회차는 `remain-v2/gemini-3.8-flash/2023-2025`의 E0 응답과 동일합니다. 이 반복 집계의 기준 응답은 이 폴더의 round-01입니다. SQLite 체크포인트는 저장소 규칙에 따라 제외했습니다.

