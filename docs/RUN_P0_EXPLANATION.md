# P0 설명 출력 실험 — GPT, 2023년

기존 P0의 비교 지시는 유지하고 마지막 출력 제한만 상세한 근거 설명과
`Final label: Yes/No` 형식으로 교체한다. 내부 사고 기록이 아닌 출력된 판단 설명을 분석한다.
2023년 시험 데이터 70건, 예시 0개, GPT 한 모델, 1회 실행이다.
기존 P0 결과와 프롬프트는 변경하지 않는다.

기본 설정은 기존 GPT 실험과 같은 OpenRouter의 `openai/gpt-6-sol`이다.
프로젝트 `.env`에 `OPENROUTER_API_KEY`가 필요하다. 공식 API를 쓰려면
설정 파일의 `api_backend`를 `official`, 모델을 공식 모델 ID로 변경하고
`OPENAI_API_KEY`를 설정한다. 출력 한도는 설명을 위해 4000토큰으로 설정했다.

프로젝트 루트에서 실행:

```powershell
python -m residue_experiment.explanation_2023 --mode dry-run
python -m residue_experiment.explanation_2023 --mode mock
python -m residue_experiment.explanation_2023 --mode live --approve-paid-api
```

`dry-run`과 `mock`은 API를 호출하지 않는다. mock 설명과 라벨은 검증용 가짜 값이다.
각 모드의 출력은 `results/p0-explanation/gpt/2023/<mode>`에 저장된다.
같은 명령을 재실행하면 성공한 문항은 건너뛰고 재개한다.
독립 재실험은 `--output`으로 새 디렉터리를 지정한다.

- `predictions.csv`: 정답, 예측, 설명(`explanation`), 전체 응답(`response`), 상태
- `api_calls.csv`: 실패를 포함한 각 시도의 원문 응답과 사용량
- `metrics.csv`: 정확도와 F1
- `manifest.json`, `prompts.jsonl`: 시스템 지시와 실제 입력 재현 자료

마지막 라벨이 없거나 설명이 없으면 응답 오류로 처리한다. 잘린 응답은
`api_errors.csv`에서 확인한다. 설정을 변경한 재실험은 새 출력 경로를 사용한다.
프롬프트와 출력 형식이 달라졌으므로 기존 P0 오답의 내부 원인을 그대로 재현한
것으로 해석하지 않는다.
