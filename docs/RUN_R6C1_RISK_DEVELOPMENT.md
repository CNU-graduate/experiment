# R6C1 위험평가용 개발 자료 추가 평가

목적: 2018~2022년 개발 위험평가용 147개 중 R6C1의 기존 유효 응답 68개를 재사용하고, 나머지 79개만 한 번 평가한다. 후보 생성·지침 수정·선택·최종 테스트는 하지 않는다.

준비(현재 완료, 유료 호출 없음):

```powershell
python -m residue_experiment.risk_development prepare
```

실행:

```powershell
python -m residue_experiment.risk_development run --mode live --max-calls 79
```

결과는 `results/r6c1-risk-development/live/` 아래 저장한다.

- `predictions.csv`: 147개 전체 입력·정답·예측·재사용 여부
- `errors.csv`: 오답 목록
- `summary.json`: 전체 집계와 호출 수
- `calls/`: 추가 평가 요청·응답 기록

기존 R6C1과 모델·입력·호출 설정이 같은 유효 응답만 재사용한다. 계획에 재사용 응답과 출처·해시를 고정한다. 같은 출력 폴더에서 재개하면 완료된 추가 응답도 재사용한다. 미완료 호출·잘못된 응답은 자동 재시도하지 않으며 임의로 정답 처리하지 않는다. 기존 실험 결과는 변경하지 않는다.

실행 중 문제별 진행 상황을 출력한다. 중복 실행은 잠금으로 차단한다. 이 집계는 과거 응답을 재사용한 개발 자료 분석이며, 미사용 테스트 성능이나 동일 시점의 반복 평가 결과가 아니다.
