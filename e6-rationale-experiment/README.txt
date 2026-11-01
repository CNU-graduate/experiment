E6 예시 핵심 근거 추가 실험 / e6-rationale-v1

1. 실험 조건
E6: 저장된 기존 사용자 프롬프트를 그대로 재사용한다.
E6_R: 같은 예시 네 개 각각에 영어 rationale 필드만 추가한다.
시스템 지침, 예시 ID·순서·원문·정답, 테스트 다섯 필드, Yes/No 출력은 동일하다.
E6의 예시를 새로 선정하지 않는다. 연도별 실제 호출 순서를 보존한다.
모델 openai/gpt-6-sol, OpenRouter, max_tokens 1000, timeout 120초,
최대 3시도, 재시도 간격 1·2초, temperature/reasoning 별도 지정 없음.
시스템과 사용자 메시지는 기존 저장소 Provider를 그대로 통해 전송한다.
GPT_MODEL 환경변수로 모델을 교체하지 않는다. 고정된 모델 ID를 사용한다.

2023 평가: Cyprodinil No → Tebuconazole Yes → Thiamethoxam Yes → Fipronil No
2024 평가: Difenoconazole No → Bifenthrin Yes → Fenazaquin Yes → Emamectin benzoate No
2025 평가: Diflubenzuron No → Tetraniliprole Yes → Cyflumetofen Yes → Fluazinam Yes

2. 파일
requests.jsonl: 실제 OpenRouter 요청 body 420개(E6 210개 + E6_R 210개).
  각 줄의 body만 API 요청으로 전송한다. case_id/year/condition은 로컬 메타데이터다.
messages_2023_first_case.json 등: 각 연도의 첫 테스트에 대한 완성된 E6_R 요청 body.
examples_with_rationales.json: 12개 예시 원문, 라벨, 영어·한국어 근거, 검토 메모.
review.csv: 엑셀에서 읽을 수 있는 12개 예시 검토표(UTF-8 BOM).
rationales.json: 근거의 원본 작성 파일. 모델에 보내는 부분은 rationale만이다.
system_prompt.txt: 기존 시스템 프롬프트.
evaluation_key_LOCAL_ONLY.json: 로컬 채점 전용. 모델에 보내지 않는다.
source_snapshot.json: GitHub 커밋, 원본 파일 Git blob 해시, 원래 manifest.
validation.json: 입력 동일성·순서·직접인용·정답 격리 점검 결과.
prepare.py: 기존 저장 결과로부터 패키지를 다시 생성. API 호출 없음.
run.py: 저장소 기존 Provider를 사용한 무료 점검/모의/실제 실행.

3. 실행
이 폴더는 experiment 저장소 루트 바로 아래에 둔다.
기존 실험용 Python 환경에서 저장소 루트를 작업 디렉터리로 사용한다.
실행 준비에는 기존 프로젝트 의존성(openai, python-dotenv)이 필요하다.
OPENROUTER_API_KEY는 기존 환경 또는 저장소 루트 .env에서 읽는다.
키를 프롬프트나 JSON 파일에 넣지 않는다.

무료 실행 계획 확인:
python e6-rationale-experiment/run.py

무료 모의 실행(실제 모델 성능 아님):
python e6-rationale-experiment/run.py --mode mock --repeats 1 --limit 4 --output e6-rationale-experiment/runs/smoke

실제 비교 실험(E6/E6_R 각각 210문제 × 3회 = 1260요청, 재시도 별도):
python e6-rationale-experiment/run.py --mode live --approve-paid-api

E6_R만 3회 실행(630요청, 재시도 별도):
python e6-rationale-experiment/run.py --mode live --condition E6_R --approve-paid-api --output e6-rationale-experiment/runs/treatment-only

2024년만 양 조건 3회 실행(420요청, 재시도 별도):
python e6-rationale-experiment/run.py --mode live --year 2024 --approve-paid-api --output e6-rationale-experiment/runs/2024

기본은 dry-run이며 SDK 클라이언트를 만들거나 API를 호출하지 않는다.
live는 위 live 명령을 직접 실행할 때만 시작된다.
양 조건을 같은 시기에 재실행하는 것이 권장된다. 과거 단일 E6 결과와
새 E6_R 3회 평균을 비교하는 것만으로 반복·실행 시점 효과를 분리할 수 없다.
양 조건 요청은 각 문제에서 E6 → E6_R 순서로 교차 실행된다.
순서 자체는 무작위화하지 않았으므로 이 설계를 기록한다.

4. 저장과 재개
기본 출력은 e6-rationale-experiment/runs/live 이다.
checkpoint.sqlite에 요청 시작·완료·응답·usage·요청 ID를 기록한다.
같은 명령과 출력 경로로 재실행하면 성공한 요청은 건너뛴다.
입력·계획·모드·실행 코드가 바뀌면 다른 출력 경로를 사용해야 한다.
예상치 못한 중단으로 started 상태가 남으면 자동으로 재전송하지 않는다.
실행 중 run.lock으로 동시 실행을 막는다. 프로세스가 종료된 것이 확인된
경우에만 중단으로 남은 lock을 제거한다. SQLite의 started 요청도 먼저 확인한다.
정상 종료 또는 처리된 오류에서는 lock이 자동 제거된다.
predictions.csv는 응답, metrics.json은 회차별·연도별 및 전체 지표다.
통신·형식 실패는 오답으로 바꾸지 않는다. coverage와 complete를 함께 확인한다.
모의 결과는 실제 성능으로 사용하지 않는다.

5. 근거의 지위와 검토 대상
근거는 동결된 예시 원문에서 재구성한 연구용 설명이다.
EFSA가 직접 작성한 설명도, 전문가 검증 완료 주석도 아니다.
기존 EFSA 라벨은 변경하지 않았다. 테스트 오답을 보고 근거를 수정하지 않았다.
선정 태그를 판정 근거로 복사하지 않았고, 예시 CSV의 EFSA 코멘트에만 있는
정보(환산계수, 독성, 추가 평가 배경 등)는 모델 설명에 추가하지 않았다.
한국어 번역, 인용 구절 목록, ID, 검토 메모는 모델에 보내지 않는다.

조건부 해석을 명시한 예시:
- 2022-22-02 Thiamethoxam: 법적 정의 대응과 별도 취급; 가금류 범위까지 같다는 뜻 아님.
- 2023-23-01 Fenazaquin: 법적 집행 정의 대응; 모든 작물 적용 범위 동일을 뜻하지 않음.
- 2024-23-04 Cyflumetofen: 모화합물/B-1/표현 기준 대응; 암묵적 이성질체 범위 검토 필요.
- 2024-29-01 Fluazinam: 원물·법적 정의 대응; 잠정 가공품 정의까지 같다는 뜻 아님.
이 네 예시를 임의로 빼거나 교체하면 동일 E6에 근거만 추가한 조건이 아니게 된다.
원래 라벨과 적용 범위의 해석 한계는 review.csv에서 추적한다.

6. 출처와 평가 한계
GitHub snapshot: 391ea081a7707a60eeeba25e46d88bab8f0581aa
https://github.com/CNU-graduate/experiment/tree/391ea081a7707a60eeeba25e46d88bab8f0581aa/results/remain-v2/gpt-6-sol/2023-2025
로컬 원본은 해당 GitHub blob과 대조했다(필요 시 checkout CRLF→LF 정규화).
모델 입력은 저장된 prompts.jsonl에서 가져오므로 CSV를 다시 해석해 만들지 않았다.
테스트 정답은 원본 predictions.csv에서 분리한 로컬 채점 파일에만 있다.
같은 210문제가 기존 분석에 사용되었으므로 이번 비교도 탐색적 실험이다.
성능 향상은 별도 미검토 자료에서 추가 검증해야 한다.
이번 패키지 작성·검증 중 유료 API 호출은 0건이다.
