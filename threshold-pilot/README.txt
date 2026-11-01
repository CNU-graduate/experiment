GPT 점수 기반 결정 임계값 조정 / threshold-pilot-v1

목표
GPT의 직접 Yes/No 판정과 0~100 비교 가능성 점수를 이용한 분류를 비교한다.
점수는 검증된 확률이 아니다. 모델 파라미터를 학습하거나 fine-tuning하지 않는다.
E6 예시나 P1/P2 보완 지침을 사용하지 않는다.

현재 동결된 예비 설계
- 개발: 2023년 이전 자료 100개(Yes 61, No 39).
- 검증: 2023년 이전 자료 100개(Yes 68, No 32).
- 개발/검증은 정규화한 농약명 기준으로 겹치지 않는다.
- 과거 자료의 중복 입력과 2023~2025 평가 입력에 정확히 대응하는 과거 행을 제외했다.
- 과거 70문제 정답지와 remain을 사용한다. E6의 전년도 remain 제한과는 다른 설계다.
- 평가: 2023년 70문제. 평가와 과거 자료에 같은 농약이 있을 수 있다(13개 이름 겹침).
- 실제 의미상 유사한 정의나 화학 동의어까지 완전히 중복 제거한 것은 아니다.
- 모델: openai/gpt-6-sol / OpenRouter / 최대 출력 1000토큰 / timeout 120초.
- 자동 재시도 없음. 실패 또는 형식 오류가 나면 중단하고 기록한다.

조건
A_direct: 기존 시스템 지침으로 직접 Yes/No 출력.
B_score_50: GPT 점수 >= 50이면 Yes.
C_score_tuned: 같은 점수에 개발 데이터에서 정한 임계값 적용.
B와 C는 정확히 같은 평가 점수 응답을 사용하며 추가 모델 호출이 없다.

순서 및 사전 고정 규칙
1. 개발 100건의 점수를 얻는다.
2. 검증 100건의 점수를 얻는다.
3. 임계값 0~101 중 개발 Macro-F1 최고를 선택한다.
   동률이면 정확도, 50과의 거리, 더 작은 임계값 순이다.
4. 선택한 임계값을 검증 자료에 적용한다. 검증 결과로 임계값을 다시 선택하지 않는다.
5. 고정 50보다 검증 정확도와 Macro-F1이 모두 나쁘지 않으면서 하나 이상 좋아야 통과한다.
6. 검증 통과 시에만 평가 70문제의 직접 판정 70회와 점수 70회를 실행한다.
7. 테스트 정답은 최종 채점에만 쓴다. 임계값은 frozen_threshold.json에 고정한다.

요청 수
개발/검증 점수 200회. 통과하면 평가 140회 추가. 최대 총 340회.
실패한 호출도 누적 예산에 포함하며 자동 재전송하지 않는다.
매 문제는 독립 요청이며 이전 문제 응답이나 점수를 모델에 전달하지 않는다.
requests.jsonl 각 줄의 body가 실제 요청이고 로컬 key/phase/kind는 모델에 보내지 않는다.
정답·농약 그룹·분할은 *_LOCAL_ONLY.json에서 로컬로만 사용한다.

실행 위치: experiment 저장소 루트. 기존 Python 환경과 OPENROUTER_API_KEY 사용.
무료 계획 점검:
python threshold-pilot/run.py

무료 코드 검증:
python threshold-pilot/test_pipeline.py

무료 모의 실행(모델 성능 아님):
python threshold-pilot/run.py --mode mock

실제 실행(개발/검증 후 통과 시 평가까지 자동):
python threshold-pilot/run.py --mode live --approve-paid-api

개발/검증만 실제 실행:
python threshold-pilot/run.py --mode live --phase calibration --approve-paid-api

검증 통과 후 평가만 이어서 실행:
python threshold-pilot/run.py --mode live --phase evaluation --approve-paid-api

출력: threshold-pilot/runs/live/
summary.txt/json: 검증과 평가 결과.
frozen_threshold.json: 개발에서 선택한 임계값과 검증 통과 여부.
development_threshold_curve.json: 개발 임계값별 성능.
evaluation_predictions_LOCAL_ONLY.json: 평가 정답·점수·세 조건 예측(평가 완료 시).
checkpoint.sqlite: 모든 요청의 시작·성공·실패, raw 응답, usage, request ID.
responses.json: 저장된 응답 내보내기.
run.lock: 동시 실행 방지. 프로세스 중단 후 잔류 시 먼저 실제 프로세스 종료를 확인한다.
같은 명령으로 재개하면 완료 응답을 재사용한다. started 요청은 결과 확인 전 재전송하지 않는다.
입력·코드·모드가 다르면 재개를 거부한다. 새 실험은 별도 폴더에 동결해야 한다.

해석
A 대 B: 점수 출력 방식 자체와 직접 판정 방식의 차이.
B 대 C: 동일 응답에서 결정 임계값만 바꾼 효과.
2023~2025는 이전 연구에서 이미 검토한 자료이므로 미검토 전향 평가라고 부르지 않는다.
이번 100/100/70 분할은 작은 탐색 실험이며 임계값 선택 과적합과 실행 변동성이 있을 수 있다.
검증 실패 시 평가를 중단하는 것은 비용 절감용 사전 규칙이며 성능 개선의 증거가 아니다.
검증 통과도 최종 개선을 보장하지 않는다. A/B/C의 오답 해결과 신규 오답을 함께 비교한다.
