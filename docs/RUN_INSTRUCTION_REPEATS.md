# P1/P2 지침 개선 실험: P0 재실행 없음

## 실험 설계

- 대상: 2023~2025년 각70개, 총210개 동일 문제.
- 예시: 없음. 원래 입력5필드만 전송하며 EFSA 정답·코멘트·ID·연도는 제외.
- P1: 기존 시스템 지침 + 공통 비교 절차.
- P2: P1 + 담당 모델의 반복 오답을 보완하는 지침.
- 각 조건3회 독립 호출. 같은 지침·입력·순서를 반복하며 random-example seed를 바꾸는 실험이 아님.
- P0는 실행하지 않음. results/zero-shot-repeats/<model>/2023-2025의 기존3회 E0를 읽기 전용 기준선으로 사용.
- 모델당 210×2×3=1,260건. 세 모델 합계3,780건이며 오류 재시도는 별도.
- 모델 ID는 config.openrouter.instructions.json에 고정. GPT_MODEL/CLAUDE_MODEL/GEMINI_MODEL 환경변수로 덮어쓰지 않음.
- 기본 출력 토큰1000, timeout120초, 최대3시도. temperature 등의 기존 미지정 설정은 새로 추가하지 않음.

## 지침과 정답 격리

실제 영어 문구는 residue_experiment/instruction_prompts.py에 버전 instruction-v1으로 고정.
P1은 세 모델 공통이며 P2는 모델별로 다름. 기존 prompt.py의 SYSTEM은 수정하지 않음.
테스트 정답이나 반복 오답 ID를 프롬프트에 넣지 않으며, 기준선 정답은 로컬 검증·분석에만 사용.
각 문제는 독립 요청이며 이전 응답·정답·채점 결과를 다음 요청에 누적하지 않음.
user prompt의 examples는 항상 빈 배열. P1/P2 차이는 system prompt에만 있음.
Provider에 명시적으로 system prompt를 전달하고 manifest와 API 요청에 같은 문구를 사용함.
기존 few-shot/E7 실행의 기본 시스템 지침은 유지함.

## 세 담당자가 실행

저장소 최신 브랜치를 받고 가상환경에서 설치 후 테스트:

```bash
python -m pip install -e ".[api,test]"
python -m pytest -q tests
```

각자 .env에는 본인의 OPENROUTER_API_KEY만 필요. 모델ID는 설정 파일에서 확인.
먼저 무료 계획 검증을 실행:

```bash
# GPT
python -m residue_experiment.instruction_repeats --provider openai --mode dry-run
# Claude
python -m residue_experiment.instruction_repeats --provider anthropic --mode dry-run
# Gemini
python -m residue_experiment.instruction_repeats --provider gemini --mode dry-run
```

각 명령은 담당 모델의 P1/P2를 각각3회 계획함. 최종 출력 cases1260, calls0.
모델ID와 지침은 출력 폴더의 plan.json, system_prompts.json에서 확인.
dry-run은 실제 예측·성능이 없고 API 클라이언트도 만들지 않음.
가상 응답 검증은 같은 명령에서 --mode mock 사용. Mock 점수는 실제 모델 성능이 아님.

실제 과금 실험을 하기로 결정한 뒤:

```bash
python -m residue_experiment.instruction_repeats --provider openai --mode live --approve-paid-api
python -m residue_experiment.instruction_repeats --provider anthropic --mode live --approve-paid-api
python -m residue_experiment.instruction_repeats --provider gemini --mode live --approve-paid-api
```

실제 모델 호출은 개발 검증에서 수행하지 않음.
다른 담당 모델은 호출하지 않으며 P0 호출 경로도 없음.
P0는 기존기준선과 시행시점이 달라질 수 있으므로 서비스측 모델 변경 영향을 한계에 기록.

## 일부만 실행하거나 재개

```bash
# P1 1회차만 실행
python -m residue_experiment.instruction_repeats --provider openai --mode dry-run --condition P1 --round 1
# 기존 live 결과를 API 호출 없이 다시 집계
python -m residue_experiment.instruction_repeats --provider openai --mode analyze
```

--round는 1/2/3, --condition은 P1/P2만 허용.
전체실행이 중단되면 같은 명령·같은 출력폴더로 재개. 성공응답은 재호출하지 않음.
--output으로 별도 루트 지정 가능. --baseline으로 기존zero-shot-repeats의 모델 루트 지정 가능.
기본 출력은 results/instruction-v1/<model>/2023-2025.
예: GPT는 results/instruction-v1/gpt-6-sol/2023-2025.
실제 하위결과는 live/P1/round-01, live/P1/round-02, ..., live/P2/round-03.
dry-run/mock/live 하위폴더와 분석은 분리됨. 한 폴더에는 한 프로세스만 실행.
기존 baseline/remain-v2/E7 결과폴더에 덮어쓰지 않음.
코드·모델·데이터·기준선·지침 변경 시 기존 체크포인트나 계획과 혼합하지 않도록 중단.
--mode analyze는 기존 live 결과만 집계하며 누락된 응답을 새로 호출하지 않음.

## 사전검증

기존기준선은 210개 고유ID·동일정답·3개 정상응답이 있어야 함.
기존 E0 2/3회차 manifest의 모델·backend·설정·기본system이 현재 비교설정과 일치해야 함.
2/3회차의 predictions.csv와 집계표 예측도 대조함.
기존입력 프롬프트 해시를 현재데이터로 재계산하며 LF/CRLF 차이만 허용.
기준선 부재·미완료·다른 모델·변경된 입력은 API 호출 전에 거부함.
API 실패를 오답이나 성공으로 처리하지 않음. 4xx 치명오류/지속오류는 기존runner처럼 저장 후 중단.

## 결과 파일

각 회차 폴더에는 기존 runner 결과(metrics.csv, predictions.csv, prompts.jsonl,
api_calls.csv, api_errors.csv, manifest.json, checkpoint.sqlite 등)를 저장.
manifest의 system_prompt와 prompt_sha256으로 실제 지침·입력 재현 가능.

모드별 analysis 폴더에는 다음을 저장:
- round_metrics.csv: 조건×회차×연도 및 전체210건의 Accuracy, Precision, Recall, Macro-F1, FP/FN, coverage.
- condition_summary.csv: 완료된 회차만의 평균·표본 표준편차. repeats_complete를 함께 확인.
- P1_error_frequency.csv / P2_error_frequency.csv: 문제별 새3회 예측·오답빈도와 기존 E0 빈도.
- P1_core_errors.csv / P2_core_errors.csv: 새3회 모두 틀린 문제.
- P1_new_errors.csv / P2_new_errors.csv: 기존3회 정답이었으나 새 지침에서 틀린 문제.
- baseline_comparison.csv: 기존핵심오답, 완전해결(3→0), 부분해결(3→1/2), 기존안정정답 훼손 수.

세 회차가 모인 문제만 해결/훼손으로 확정. 미완료·dry-run을 해결로 계산하지 않음.
부분 실행 결과의 수치도 전체완료결과로 해석하지 말 것.
기존 E0와 새 P1/P2의 원본은 수정하지 않으며 분석 파일을 별도 생성.

## 연구 해석

P2는 모델별 문구가 다르므로 주효과는 모델 간 순위가 아니라 각 모델의 P1/P2 개선량으로 비교.
기존에 본210문제는 지침개발·검증 자료임. 일반화는 별도 미검토 자료로 검증해야 함.
TDM 등 유사구조에 서로 다른라벨이 있는 경우 원문맥락/비교단위 확인이 필요하며,
새 프롬프트는 새로운 규제적 정답기준을 발명하거나 정답을 변경하지 않음.
