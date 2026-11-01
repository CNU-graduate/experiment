# P0 / B / C 오류 보완성 예비 실험

기존 v1의 개발 326개 / 선택 140개 분할과 P0를 그대로 복사한다.
개발 자료 전체를 P0로 새로 판정한 뒤, P0에서 각각 B와 C를 한 번씩 생성한다.
선택 자료에서 세 지침을 각각 한 번 평가한다. 앙상블, 반복 라운드, 2023년 최종 평가는 없다.
기존 실험 파일은 수정하지 않으며, 이 실험의 성공 호출은 재실행 시 재사용한다.
기존 v1의 다른 지침으로 푼 개발 기록이나 요청 검증이 불가능한 과거 출력은 가져오지 않는다.

## 실행

프로젝트 루트의 PowerShell에서:

```powershell
python -m residue_experiment.error_diversity prepare
python -m residue_experiment.error_diversity run --mode mock --max-calls 748
```

mock은 실행 흐름 검증만을 위한 합성 출력이며 성능 결과가 아니다.
실제 호출에는 `.env`의 `OPENROUTER_API_KEY`가 필요하다.
모델 설정은 `config.error-diversity.json`에 있으며 기본값은 기존 실험과 같은
`openai/gpt-6-sol`이다. 모델 변경은 prepare 전에 한다. plan 생성 후 설정을 변경하려면
새로운 `--output` 디렉터리에서 prepare와 run을 실행한다.

전체 유료 실행:

```powershell
python -m residue_experiment.error_diversity run --mode live --max-calls 748
```

먼저 개발 결과만 확인하려면:

```powershell
python -m residue_experiment.error_diversity baseline --mode live --max-calls 326
```

이후 위 run 명령으로 이어가면 개발 326회는 다시 호출하지 않는다.
예산은 해당 출력 폴더·mode의 누적 호출 상한이다. 326회 개발 + 2회 생성 +
420회 선택 평가 = 최대 748회. 토큰 사용량에 따라 비용은 달라진다.
오류/중단 상태의 호출은 자동 재시도하지 않는다. 로그를 검토해야 한다.
동시 실행은 mode별 잠금 파일로 막는다. 강제 종료로 잠금이 남으면 실행 중인
프로세스가 없는지와 calls 기록을 확인한 후 해당 잠금 파일만 제거한다.

## 수정용 사례 구성

- B: 정답 No/P0 Yes인 오류 + P0가 맞힌 Yes 사례.
- C: 정답 Yes/P0 No인 오류 + P0가 맞힌 No 사례.
- 양쪽 모두 같은 수 k의 오류와 k개의 반례를 받는다. k는 설정 상한 10과
  네 집단의 사례 수 중 최솟값이다. 따라서 후보별 최대 20개를 제공한다.
- 오류는 ID 순서로 선택한다. 반례는 목적 일치, 품목 일치, JMPR/EU 원문 단어의
  Jaccard 유사도 순으로 선택하며 후보 내부에서 중복 사용하지 않는다.
  이는 자동 검색 휴리스틱이며 의미적 반례임을 보장하지 않는다.
- 필요한 집단이 비어 있으면 개발 결과를 저장한 뒤 생성 전에 중단한다.
  부족한 사례를 선택 자료에서 가져오거나 임의로 만들어 넣지 않는다.
- B/C 생성 요청의 구조와 사례 수는 같지만 내용 및 토큰 수까지 동일하지는 않다.
- 수정용 LLM에는 개발 사례만 전달한다. 판정용 LLM은 완성된 지침과 문제 하나만
  받고 정답·개발 예시는 받지 않는다. B/C가 동일하면 재생성 없이 중단한다.

## 결과

`results/error-diversity-2023/live/`:

- `development_P0.csv`, `development_metrics.json`: 개발 결과.
- `evidence.json`: 선택한 오류·반례 및 이용 가능한 오류 수.
- `B_optimizer_input.json`, `C_optimizer_input.json`: 생성에 전달한 정확한 입력.
- `B_candidate.json`, `C_candidate.json`, `prompts.json`: 생성 출력과 실제 지침.
- `selection_P0.csv`, `selection_B.csv`, `selection_C.csv`: 문제별 예측.
- `metrics.csv`: 정확도, Macro-F1, FP(No→Yes), FN(Yes→No).
- `summary.json`: 개별 성능, 후보 쌍별 공통 오류 ID, 교정·악화 ID, 답변 불일치 수.
- `calls/`: 요청, 응답, 사용량, 성공·오류 상태.

오류의 차이만으로 성공을 선언하지 않는다. 목표 오류 감소, 반대 오류 증가,
전체 정확도와 상호 보완성을 함께 해석한다. 재사용한 선택 자료에서의 단회 결과이므로
일반화 또는 통계적 유의성의 근거가 아니다. 전체 오류 기반 수정 조건 A는 이번 범위에 없다.
