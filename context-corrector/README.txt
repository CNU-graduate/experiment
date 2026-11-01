문맥 기반 보정기 / context-corrector-v1

기존 threshold-pilot/runs/live에 저장된 GPT 점수 200건을 재사용한다.
새 GPT 요청, API 키, 인터넷 연결이 필요하지 않다.
이 실험은 GPT 단독 방식이 아니라 GPT 점수와 일반 지도학습 분류기의 결합이다.

입력 특징
- GPT 점수(0~100)와 임계값 50의 판정.
- 목적·대상·JMPR·EU 원문에서 단어/문자 TF-IDF 특징.
- 고정된 포합체·이성질체·표현 기준·출처 관련 단순 지표.
- ID, 정답, EFSA 코멘트는 입력 특징에 포함하지 않는다.

학습
개발 100건만 사용하고 농약 그룹 기준 5-fold 교차검증으로 C를 고른다.
C 후보는 0.01, 0.1, 1, 10으로 사전 고정한다.
교차검증마다 TF-IDF도 해당 학습 fold에서만 fit한다.
개발 OOF Macro-F1 최고, 동률이면 정확도, 더 작은 C 순서로 선택한다.
최종 모델은 개발 100건으로만 fit하고 검증 100건은 마지막 평가에만 사용한다.
기존 임계값 71을 다시 조정하거나 검증 결과로 모델을 반복 선택하지 않는다.

저장소 루트에서 입력 확인만:
python context-corrector/run.py --check-only

실험 실행(추가 API 비용 없음):
python context-corrector/run.py

기본 출력: context-corrector/runs/offline-v1/
- summary.txt/json: 기존 GPT 임계값 50 대 보정기의 검증 지표.
- predictions_LOCAL_ONLY.json: 검증 100건의 예측 비교.
- frozen_model_design.json: 개발 교차검증·선택 설정·소스 해시.

기존 프로젝트의 scikit-learn과 numpy를 사용한다.
입력 위치를 따로 지정하려면 --input 경로를 사용한다.
설정이나 코드를 바꾼 실험은 --output에 새로운 경로를 지정한다.

한계
개발 100건은 작아 과적합 가능성이 있다.
검증 100건은 이전 임계값 실험에서 이미 살펴본 자료이므로 새 독립 검증이 아니다.
성능 개선 여부는 이 탐색 결과만으로 확정하지 않으며, 개선이 없으면 그대로 보고한다.
2023년 테스트를 실행하거나 기존 API 실험을 재개하지 않는다.
