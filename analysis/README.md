# 현재 분석 자료

| 폴더 | 내용 |
|---|---|
| [compact_10_type_classification](reports/compact_10_type_classification/report.html) | 729건·10개 유형 분류표와 유형/연도/라벨 분포 |
| [prompt_clarity_audit](reports/prompt_clarity_audit/report.html) | 실제 프롬프트 입력과 명확·조건부 사례 비교 |

`current_classification.json`이 최신 분류표 위치를 가리킵니다.
실제 모델 응답과 추가 zero-shot 결과는 `../results/`에 있습니다.
과거 중간 분류표와 보고서는 `../archive/`에 보관합니다.

`reports/`는 완료된 분류·프롬프트 검토 산출물입니다. `current_classification.json`의 경로는 이 analysis 폴더를 기준으로 해석합니다. 반복 실험의 실제 응답과 최종 집계는 `results/`에서 관리합니다.
