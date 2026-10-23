# 실험 결과

폴더 이름은 `모델__실험__대상연도` 형식입니다. 사전 점검은 `preflight__실행일`로 구분합니다.

| 폴더 | 모델 | 내용 |
|---|---|---|
| [claude-opus-5.5__baseline__2023-2025](claude-opus-5.5__baseline__2023-2025/) | Claude Opus 5.5 | 기존 E0~E5 실제 응답 2,940건 |
| [claude-opus-5.5__zero-shot-3-runs__2023-2025](claude-opus-5.5__zero-shot-3-runs__2023-2025/) | Claude Opus 5.5 | 기존 E0 1회와 추가 2회 비교. 추가 실제 응답 각 210건 |
| [claude-opus-5.5__remain-v2__2023-2025](claude-opus-5.5__remain-v2__2023-2025/) | Claude Opus 5.5 | E0·E1·E5·E6 실제 응답 840건 |
| [preflight__2026-10-19](preflight__2026-10-19/) | Claude Opus 5.5 / GPT-6 Sol / Gemini 3.8 Flash | 사전 점검 및 실행 계획. 실제 모델 응답 없음 |

모델 ID는 각 `manifest.json`의 `config.models`에서 확인했습니다. Claude의 저장된 ID는 `anthropic/claude-opus-5.5`입니다.

## 하위 폴더

- `live/round_2`, `live/round_3`: zero-shot 추가 실제 응답.
- `dry-run/`: 실행 계획이며 실제 응답이 아닙니다.
- `analysis/`: 반복 실험 오답 빈도 및 연도별 집계.
- 사전 점검의 `remain-anthropic`, `remain-openai`, `remain-gemini`: 공급자별 실행 계획.

원본 manifest, checkpoint, CSV, 프롬프트는 내용을 변경하지 않고 함께 보존했습니다.

## 이전 경로 → 현재 경로

| 이전 | 현재 |
|---|---|
| `claude-2023-2025/` | `claude-opus-5.5__baseline__2023-2025/` |
| `zero-shot-3-runs/` | `claude-opus-5.5__zero-shot-3-runs__2023-2025/` |
| `remain-v2/claude/` | `claude-opus-5.5__remain-v2__2023-2025/` |
| `preflight-20261019/` | `preflight__2026-10-19/` |
