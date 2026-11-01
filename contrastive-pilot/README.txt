E6와 독립적인 제로샷 대조 진단 예비 실험

가설: 동일 의미의 제시 형식 변경에는 판정이 유지되고, 잔류정의의 실질적 차이를
추가/제거하면 판정이 올바른 방향으로 바뀌어야 한다.

20개 원본(Yes 10, No 10), 원본별 3종 입력 = 60개, 3회 반복 = 180요청.
original: 기존 remain 행의 원문과 EFSA 라벨.
preserved: 원문 필드값은 그대로 두고 JSON 필드 순서와 들여쓰기만 변경. 라벨 유지.
substantive: 한쪽 정의의 성분 범위/포합체/표현 기준 한 요인을 변경. 예상 라벨 반전.
완성 세트는 Yes 30개, No 30개로 균형을 맞췄다.
분류 지침은 모든 요청에서 같고 예시·근거·테스트 정답·EFSA 코멘트를 보내지 않는다.
매 문제 독립 API 요청. 회차와 문제 사이에 이전 결과를 누적하지 않는다.

중요한 구분
변형된 정의는 실제 규제 정의가 아니다. 가상의 추가 대사산물과 염을 포함할 수 있다.
변형 후 정답은 EFSA 공식 판정이 아닌 사전 정의한 변형 규칙에 따른 연구용 예상값이다.
전문가 독립 검증은 아직 완료하지 않았다. 이번 실행은 탐색적 진단이다.
포합체를 제외하거나 표현 기준을 맞춘 합성 사례에 대한 Yes 가정도 검토 대상이다.
source 원문과 변경 전후는 review.txt 및 transformations_review.json에서 검토할 수 있다.
preserved는 단순한 형식 불변성 시험이며 의미를 재서술하는 강한 패러프레이즈 시험이 아니다.
HYP 표기가 답의 단서가 될 수 있어 합성 사례 고득점을 도메인 이해 증거로 단정하지 않는다.
20개 명확한 사례를 목적 선정했으므로 전체 EFSA 문제에 대한 대표 성능이 아니다.
같은 원본의 3변형·3회 결과는 서로 종속적이며 독립 표본 수는 20개다.

실행 위치: experiment 저장소 루트. 기존 Python 의존성과 OPENROUTER_API_KEY 사용.
무료 검증:
python contrastive-pilot/run.py

무료 모의 실행(모델 성능 아님):
python contrastive-pilot/run.py --mode mock --repeats 1 --limit 6 --output contrastive-pilot/runs/smoke

실제 실험: 모델 openai/gpt-6-sol, OpenRouter, 180요청, 자동 재시도 없음.
python contrastive-pilot/run.py --mode live --approve-paid-api

분석:
python contrastive-pilot/analyze.py

기본 결과: contrastive-pilot/runs/live/
checkpoint.sqlite, predictions.csv, metrics.json, contrastive_summary.json/txt.
정상 완료 요청은 재개 시 건너뛴다. 응답이 불확실한 started 요청은 자동 재전송하지 않는다.
원본/형식변형 정확도, 판정 불변성, 실질변형 탐지, 원본-변형 쌍 정답률을 따로 본다.
원본 EFSA-label 정확도와 합성 rule-label 정확도를 혼합해 E6보다 개선됐다고 보고하지 않는다.
단일 가족이 여러 번 틀린 경우와 여러 가족에서 틀린 경우도 구별한다.
