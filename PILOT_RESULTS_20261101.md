# 추가 실험 및 결과 (2026-11-01)

| 디렉터리 | 실험 | 실행 상태 및 결과 |
|---|---|---|
| e6-rationale-experiment | E6 예시에 모델이 작성한 핵심 근거 추가 | 실험 코드와 고정 입력 준비. EFSA 원문 설명으로 간주하면 안 됨 |
| e6-efsa-comment-experiment | 실제 EFSA 코멘트에 근거한 요약을 E6 예시에 추가 | 2023년 70개, 조건별 1회: E6 68/70, E6_EFSA 68/70. 오답 1개 수정, 신규 오류 1개 |
| contrastive-pilot | 원본·표현 변화·내용 변화에 대한 판정 진단 | 오프라인 점검 완료. 실제 GPT 성능 결과 없음. 변형 정답은 EFSA 공식 정답이 아님 |
| threshold-pilot | GPT 비교 가능성 점수의 전역 임계값 선택 | 개발 100개에서 71 선택. 검증 100개에서 기준 50은 90%, 기준 71은 89%. 검증 gate 실패로 2023 평가 호출은 실행하지 않음 |
| context-corrector | GPT 점수와 원문 특징을 결합한 로지스틱 회귀 | 기존 GPT 점수 재사용, 추가 API 호출 0. 검증 정확도 90% → 94%, Macro-F1 0.89149 → 0.93316. 오답 4개 수정, 신규 오류 0 |

## 데이터와 해석

개발/검증은 2018·2019·2021·2022년 자료를 농약명 그룹으로 나눈 각 100개다.
연도별 개발/검증 수는 각각 18/36, 26/21, 35/18, 21/25다.
동일한 정규화 농약명 그룹은 양쪽에 중복되지 않지만 화학적 동의어 전체를 통합한 것은 아니다.

보정기는 개발 데이터의 농약 그룹 5-fold 교차검증으로 C를 선택하고 검증 전에 고정했다.
검증 데이터는 이전 임계값 실험에서 이미 확인한 자료이므로 94%는 탐색 결과다.
GPT 단독 또는 E6 대비 개선을 입증한 결과가 아니다. 점수만 사용하는 학습 보정기와의
비교가 아직 없어, 문장 특징 자체의 추가 효과도 확정할 수 없다.
2023~2025년 보정기 평가는 아직 실행하지 않았다.

## 실행 및 보관

저장소 루트에서 다음 명령으로 유료 API 호출 없이 점검/재현할 수 있다.

```powershell
python threshold-pilot/test_pipeline.py
python context-corrector/run.py --check-only
python context-corrector/run.py --output context-corrector/runs/reproduction
```

Python 의존성은 각 실험 README와 기존 프로젝트 설정을 참고한다. 보정기는 numpy와
scikit-learn을 사용한다. 라이브 API 실험은 각 디렉터리 README의 별도 명령을 사용한다.

실제 실행 결과는 e6-efsa-comment-experiment/runs/pilot-2023,
threshold-pilot/runs/live, context-corrector/runs/offline-v1에 보관했다.
선택된 결과/응답 파일만 버전 관리하며 SQLite 체크포인트, 잠금 파일, API 키는 제외한다.
라이브 체크포인트를 제외했으므로 이 결과 파일만으로 유료 실행을 안전하게 재개할 수 있다고
가정하면 안 된다. LOCAL_ONLY는 정답을 API 입력과 분리하기 위한 이름이며 비밀정보 표시는 아니다.
고정 입력의 바이트 해시를 보존하도록 해당 실험 디렉터리의 Git 줄바꿈 변환을 비활성화했다.

자료 부족으로 중단한 fact-rag-pilot은 미완성 초안이며 이 실행 패키지에 포함하지 않았다.
