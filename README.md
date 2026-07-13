# shot_bot

> **연구/모의검증 전용입니다.** 이 프로젝트는 주문을 전송하거나 브로커 계정을 연결하지 않습니다. 과거 성과는 미래 수익을 보장하지 않으며, 실거래 전에는 별도의 독립 검증·법률/세무 검토·모의거래가 필요합니다.

기존 Colab 전략에서 발견된 핵심 편향을 줄이기 위한 단타 전략 연구 기반입니다.

## 반영한 개선

- **미래 라벨 오염 방지:** 관측되지 않은 미래 가격은 0이 아니라 `NaN`으로 유지합니다.
- **Purged split:** 10일 등 겹치는 forward label이 학습/검증/테스트 경계를 넘지 않도록 embargo를 적용합니다.
- **상대 랭킹 타깃:** 절대 상승확률 임계값 대신, 매 거래일의 종목별 forward return 순위를 모델 타깃으로 사용할 수 있습니다. LightGBM 사용 시 날짜를 group으로 한 `LGBMRanker(objective="lambdarank")`를 권장합니다.
- **보수적 일봉 체결:** 손절/익절이 한 일봉 안에 동시에 닿으면 손절을 우선합니다. 갭 하락 손절은 도달 불가능한 stop 가격이 아니라 `min(open, stop)`으로 처리합니다. 새 고점으로 갱신한 trailing stop은 다음 봉부터만 유효합니다.
- **위험 예산 sizing:** ATR 기반 주당 위험과 포지션 명목금액 상한 중 작은 값으로 수량을 제한합니다.
- **유동성/과매수 필터:** 달러 거래대금과 RSI 필터를 통과한 종목만 score 순으로 선택합니다.

## 설치 및 테스트

```bash
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev,research]"
.venv/Scripts/python.exe -m pytest -q
```

## 현재 모듈

- `labels.py` — 관측 가능한 forward label 생성
- `splits.py` — purge/embargo 적용 시간 분할
- `signals.py` — 날짜별 상대수익 랭킹 타깃 및 top-k 선택
- `risk.py` — ATR 기반 위험 예산 수량 계산
- `backtest.py` — 보수적 일봉 exit 규칙
- `snapshot.py` — CSV 스냅샷과 SHA-256 메타데이터 기록
- `ranking.py` / `research.py` — 날짜 그룹 LightGBM LambdaRank 및 expanding walk-forward 점수 생성
- `scripts/run_research.py` — 주문 없이 시세 스냅샷·점수·최신 후보를 생성하는 CLI

## 연구 실행 예시

```bash
.venv/Scripts/python.exe scripts/run_research.py \
  --tickers AAPL,MSFT,NVDA,AMZN \
  --period 1y --horizon 5 --min-train-dates 80 --rebalance-every 20
```

결과는 로컬 `data/snapshots/`(원시/점수 데이터와 SHA-256 메타데이터) 및 `reports/latest_candidates.csv`에 저장됩니다. 이 파일들은 재현 연구 데이터이므로 Git에는 기본적으로 포함하지 않습니다.

## 다음 연구 단계

1. 고정된 데이터 스냅샷(Parquet)과 데이터 해시를 저장해 재현성을 확보합니다.
2. 역사적 유니버스·상장폐지 데이터를 적용해 생존자 편향을 줄입니다.
3. 날짜 group 기반 LightGBM 랭커를 expanding walk-forward 방식으로 학습합니다.
4. 수수료·스프레드·슬리피지·ADV 참여율·실적일 리스크를 비용 모델에 반영합니다.
5. 비용 후 top-k 초과수익, rank IC, turnover, MDD, block-bootstrap 신뢰구간을 보고합니다.
6. 최소 수 주 이상의 paper trading 검증 전에는 주문 실행 모듈을 추가하지 않습니다.
