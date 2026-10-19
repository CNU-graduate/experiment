# 검증 보고서

검증일: 2026-10-10 (Asia/Seoul 기준).

## 실제 데이터

GitHub `CNU-graduate/experiment`의 CSV 21개를 읽었습니다. 파일 bytes의 Git blob
SHA-1이 GitHub 제공 SHA와 모두 일치합니다. CSV를 수정하지 않았습니다.
연도: 2018, 2019, 2021, 2022, 2023, 2024, 2025. 테스트 총 490건(연도당 70건).
라벨 오류, 중복 ID, 테스트/정답지 ID 및 입력 불일치 없음.
연도별 건수·분포는 README와 결과의 validation.csv에 있습니다.
2020년 데이터 부족은 오류를 보충하지 않고 조건별 제외로 기록했습니다.

## 실행 검증

- `python -m pytest -q`: **31 passed**.
- 전체 dry-run: 20,580개 계획, 13,230개 planned, 7,350개 excluded, API 호출 0회.
- 전체 Mock: 13,230개 성공, 7,350개 excluded. 유료 API 호출 0회.
- 같은 전체 Mock 명령 재실행: 호출 이력 증가 없음(13,230개 유지).
- 공식 SDK 어댑터 테스트: 실제 SDK를 import하고 클라이언트 네트워크 메서드를 Mock으로 교체.
- 입력 allowlist, 라벨·메타데이터의 유사도 배제, TF-IDF 순위·동점 처리 검증.
- E0~E5의 개수·라벨·연도, seed 재현성, 모델 간 동일 예시 검증.
- 오류 재시도·로그 비밀문자열 배제, Ctrl+C 후 계획 분모·재개 검증.
- 데이터 충돌/잘못된 라벨/정답지 불일치 및 과거 데이터 부족 검증.
- 정확한 혼동행렬·Accuracy·Precision·Recall·Macro-F1 계산 검증.
- 완료 반복만 평균에 포함하는 처리 및 live 승인·키 요구 조건 검증.

Mock 예측은 해시 기반 임의의 Yes/No입니다. 결과 수치는 실제 LLM 성능이나
연구 결론으로 사용할 수 없습니다. 실제 모델 가용성 및 유료 엔드포인트 호출은 검증하지 않았습니다.
모델 ID는 설정 파일에서 공란으로 남겨 실행 시점의 최신 공식 모델을 지정하게 했습니다.

## 검증 환경

Python 3.11+, scikit-learn 1.8.0, python-dotenv 1.2.2, pytest 9.1.1.
OpenAI SDK 2.54.0, Anthropic SDK 0.125.0, Google Gen AI SDK 1.75.0.
공식 SDK에 인증된 네트워크 요청을 보내지 않았습니다.

## 준비된 변경 파일

- residue_experiment/data.py: 원본 읽기와 검증, 테스트 정답 결합, 후보 중복 제거.
- residue_experiment/selection.py: E0~E5 및 TF-IDF/cosine 선택.
- residue_experiment/prompt.py: 입력 필드 제한, 분류 기준, 엄격한 응답 파싱.
- residue_experiment/providers.py: 세 회사 공식 SDK와 키 없는 Mock.
- residue_experiment/runner.py: 전체 계획·호출 체크포인트, 재시도·재개, CSV 내보내기.
- residue_experiment/evaluation.py: 지표·혼동행렬·반복 평균/표준편차.
- residue_experiment/cli.py, __init__.py: CLI 및 패키지.
- tests/test_experiment.py: 31개 검증.
- config.json, .env.example, .gitignore, pyproject.toml: 설정·키 분리와 설치.
- README.md, TEST_REPORT.md: 실행·해석·GitHub 반영 방법과 검증 결과.

사용자 요청에 따라 검증된 구현 파일을 GitHub 저장소에 반영합니다. 원본 CSV, .env,
가상환경 및 결과 체크포인트는 업로드 대상에서 제외합니다. 유료 API 호출은 실행하지 않았습니다.

## 2026-10-12 OpenRouter 추가 검증

OpenRouter 백엔드, 단일 API 키, .env 모델 ID 연결을 추가했습니다.
공식 API 회귀 테스트와 세 OpenRouter 모델 경로의 Mock 요청, CLI 환경값 반영을 검증했습니다.
실제 유료 API 호출 없이 36개 테스트 통과. 원본 CSV 변경 없음.
