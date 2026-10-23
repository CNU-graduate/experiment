# 테스트

| 파일 | 검증 범위 |
|---|---|
| `test_experiment.py` | 데이터·예시 선정·평가·공급자 어댑터·공통 실행기 |
| `test_zero_shot_repeats.py` | E0 반복 집계·CSV baseline·경로 이동·프롬프트 일치 |
| `test_e7.py` | E7 고정 예시와 3회 실행 계획 |

전체 테스트는 프로젝트 루트에서 실행합니다.

```powershell
python -m pip install -e ".[test]"
python -m pytest tests -q
```

unittest 기반 반복 실험 테스트만 실행할 수도 있습니다.

```powershell
python -m unittest discover -s tests -p test_zero_shot_repeats.py -v
python -m unittest discover -s tests -p test_e7.py -v
```

유료 API 대신 모의 호출과 실행 계획으로 검증합니다. 임시 파일은 시스템 임시 경로에 만들고 테스트 종료 시 삭제합니다. `results/`를 테스트 임시 경로로 사용하지 않습니다. baseline 통합 검증에는 저장소의 기존 결과를 읽기 전용으로 사용합니다.

전문가 검토 웹사이트 테스트는 별도 `website/tests/`에 있습니다.
