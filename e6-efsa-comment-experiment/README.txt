실제 EFSA 코멘트를 근거로 한 E6 부분 설명 추가 실험

source_review.txt에서 예시 12개의 원문 코멘트, 요약, 출처, 범위 한계를 확인한다.
source_examples.json은 같은 정보를 담은 구조화 파일이다.
comment_annotations.json의 영어 rationale만 모델에 추가한다.
null인 예시는 추론으로 설명을 보충하지 않고 원래 예시 그대로 유지한다.

설명 추가 가능 6개:
2022-11-04 Cyprodinil / 2022-22-02 Thiamethoxam / 2022-10-03 Fipronil
2023-23-01 Fenazaquin / 2023-16-02 Emamectin benzoate
2024-08-03 Diflubenzuron (부분 근거이며 차 품목의 동일성 진술을 함께 보존)

E6 예시 네 개씩의 선정·순서·원문·정답을 유지한다.
E6_EFSA는 사용 가능한 코멘트가 있는 예시에만 rationale을 추가한다.
평가 연도 2023/2024/2025별 설명 예시 수는 각각 3/2/1개다.
따라서 이 조건은 4개 모두에 설명을 붙인 조건이 아니라 부분 추가 조건이다.
2023·2024년 문헌의 8개 예시는 Europe PMC 원문 XML의 비교표와 대조했다.
2022년 4개는 저장소의 EFSA 코멘트 전사본 기반이며 전체 원문 대조는 완료하지 못했다.
2022년 Thiamethoxam 코멘트는 Wiley 원문 검색 색인에서도 확인했다.
source_examples.json에서 독립 원문 대조와 저장소 전사본을 구분한다.
코멘트 요약 문장은 연구용 요약이며 EFSA가 작성한 문장 자체는 아니다.
기존 LLM 재구성 설명 패키지 e6-rationale-experiment와 별도 조건이다.

저장소 루트에서 무료 점검:
python e6-efsa-comment-experiment/run.py

양 조건 각 210문제 × 3회, 총 1260요청(재시도 별도)의 실제 실행:
python e6-efsa-comment-experiment/run.py --mode live --approve-paid-api

E6_EFSA만 630요청 실행:
python e6-efsa-comment-experiment/run.py --mode live --condition E6_EFSA --approve-paid-api --output e6-efsa-comment-experiment/runs/treatment-only

실제 요청은 requests.jsonl 각 줄의 body이다.
한국어 설명, 검토 메모, 원문 코멘트 전체와 테스트 채점 파일은 API에 보내지 않는다.
OPENROUTER_API_KEY는 기존 저장소 루트 .env 또는 환경에서 읽는다.
기존 저장소의 Provider와 Python 의존성을 사용한다.
동일 출력 경로에서는 성공 요청을 재사용하며 입력·코드가 바뀌면 새 경로가 필요하다.
metrics.json의 coverage와 complete를 확인하고 mock 결과를 모델 성능으로 쓰지 않는다.
작성·검증 중 유료 API 호출 0건.
