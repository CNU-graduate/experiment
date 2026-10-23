# E7: 오류 분석 기반 고정 4-shot, 3회 반복

기존 E0~E6와 기존 config/result는 유지합니다. E7은 과거에 제안했던
유사도 제약 조건이 아니라, 최종 합의한 수작업 N1/N2/Y1/Y2 선정 조건입니다.

## 고정 순서와 예시

모든 문제·회차에 N1 → Y1 → N2 → Y2 순서로 원본 입력과 정답만 제공합니다.
선정 이유·역할·ID·예시 연도는 감사용이며 모델 입력에는 넣지 않습니다.

| 평가 연도 | N1 (No) | Y1 (Yes) | N2 (No) | Y2 (Yes) |
|---|---|---|---|---|
| 2023 | 2022-16-03 | 2022-22-03 | 2022-02-02 | 2022-13-02 |
| 2024 | 2023-20-02 | 2023-10-02 | 2023-21-02 | 2023-15-02 |
| 2025 | 2024-03-04 | 2024-01-04 | 2024-21-04 | 2024-23-04 |

선정 목록은 `residue_experiment/e7_examples.py`에 고정합니다. 후보의 누락·중복·연도·
정답 불일치는 자동 보충하지 않고 오류로 처리합니다. 원문은 전년도 remain에서 읽습니다.

## API 호출 없이 630건 계획

```powershell
python -m residue_experiment.e7_repeats --mode dry-run
```

별도 설정 `config.openrouter.e7.json`은 Claude의 고정 모델 ID와 E7만 지정합니다.
회차당 210건(3년×70건), 3회 합계 630건입니다. seed로 예시를 바꾸지 않고 독립 회차 폴더에 저장합니다.

出力: `results/error-informed/claude-opus-5.5/2023-2025/`

- `plan.json`: 설정·순서·총수
- `plan_by_year.csv`: 연도별 건수
- `selected_examples.json`, `selected_examples.csv`: 원문·정답·역할·선정 이유 12건
- `dry-run/round-01/` ~ `round-03/`: 각 210건의 manifest, checkpoint, prompts, examples 등

`--mode live --approve-paid-api`는 유료 API를 실행하므로 별도 실행 지시가 있을 때만 사용합니다.
live는 같은 루트 아래 `live/round-01/` ~ `round-03/`에 저장하며 dry-run과 구분합니다.
기존 실험의 출력 폴더는 지정하지 마세요. 코드 변경 후 이전 체크포인트 재개는
구현 fingerprint에 의해 거부될 수 있습니다. 호환성 검사는 완화하지 않았습니다.

## 검증

```powershell
python -m unittest discover -s tests -p test_e7.py -v
```

## 해석

2023~2025년 테스트 오답을 보고 선정한 탐색적 개선 실험이며 일반화 검증과 구분합니다.
정확도, Macro-F1, 기존 반복 오답의 개선, 기존 정답의 신규 오답, 응답 안정성을 비교합니다.
dry-run에서는 성능을 측정하지 않습니다.
