# 실험 결과

결과는 `실험 종류/모델/대상 연도/` 순서로 정리합니다. 모델 ID는 각 `manifest.json`의 `config.models`에서 확인할 수 있습니다.

```text
results/
├── baseline/
│   ├── claude-opus-5.5/2023-2025/
│   └── gpt-6-sol/2023-2025/
├── remain-v2/
│   ├── claude-opus-5.5/2023-2025/
│   ├── gpt-6-sol/2023-2025/
│   └── gemini-3.8-flash/2023-2025/
├── zero-shot-repeats/
│   └── claude-opus-5.5/2023-2025/
│       ├── live/round-02/, round-03/
│       ├── dry-run/round-02/, round-03/
│       └── analysis/
└── preflight/
    └── 2026-10-19/
```

## 실제 응답

| 경로 | 조건 | 저장된 응답 수 |
|---|---|---:|
| [baseline/claude-opus-5.5/2023-2025/](baseline/claude-opus-5.5/2023-2025/) | E0, E1, E2, E3, E4, E5 | 2,940 |
| [baseline/gpt-6-sol/2023-2025/](baseline/gpt-6-sol/2023-2025/) | E0, E1, E2, E3, E4, E5 | 2,940 |
| [remain-v2/claude-opus-5.5/2023-2025/](remain-v2/claude-opus-5.5/2023-2025/) | E0, E1, E5, E6 | 840 |
| [remain-v2/gemini-3.8-flash/2023-2025/](remain-v2/gemini-3.8-flash/2023-2025/) | E0, E1, E5, E6 | 840 |
| [remain-v2/gpt-6-sol/2023-2025/](remain-v2/gpt-6-sol/2023-2025/) | E0, E1, E5, E6 | 840 |
| [zero-shot-repeats/claude-opus-5.5/2023-2025/live/round-02/](zero-shot-repeats/claude-opus-5.5/2023-2025/live/round-02/) | E0 | 210 |
| [zero-shot-repeats/claude-opus-5.5/2023-2025/live/round-03/](zero-shot-repeats/claude-opus-5.5/2023-2025/live/round-03/) | E0 | 210 |

`baseline`은 기존 E0~E5 실험, `remain-v2`는 E0·E1·E5·E6 실험입니다. `zero-shot-repeats`는 baseline의 E0를 1회차로 사용하고 추가 2·3회차와 비교합니다. 집계는 해당 폴더의 `analysis/`에 있습니다.

## 저장 규칙

- 모델은 `claude-opus-5.5`, `gpt-6-sol`, `gemini-3.8-flash`처럼 버전까지 표시합니다.
- 대상 데이터 연도는 `2023-2025`, 실행 날짜는 `2026-10-19` 형식입니다.
- `live/`는 실제 응답, `dry-run/`은 실행 계획, `mock/`은 모의 실행입니다. 기존 baseline과 remain-v2의 실제 결과는 연도 폴더 바로 아래에 있습니다. 새로 모드를 구분해 실행할 때는 연도 아래에 모드 폴더를 둡니다.
- `preflight/2026-10-19/`는 사전 점검과 실행 계획이며 실제 모델 응답이 아닙니다. 하위 공급자 폴더와 zero-shot 계획을 함께 보존했습니다.
- `predictions.csv`, `metrics.csv`, `comparison.csv`, `manifest.json` 등 결과 파일 이름과 내용은 유지합니다.
- `checkpoint.sqlite`는 재개·반복 분석에 필요하지만 Git에서 제외됩니다. 기존 로컬 체크포인트도 해당 실험의 새 폴더로 옮겨야 합니다.

루트 README의 실행 예제도 같은 경로 규칙을 사용합니다. 실행 시 실제 모델 ID와 출력 경로의 모델명을 일치시키세요.
