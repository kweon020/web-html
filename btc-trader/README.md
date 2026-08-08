# btc-trader

업비트 비트코인 규칙 기반 자동매매 — **백테스트 + 페이퍼 트레이딩**

실제 주문을 내는 코드는 **일부러 넣지 않았습니다.** 먼저 전략이 통계적으로
살아남는지 확인하고, 실시간에서 안정적으로 도는지 본 다음에 붙이는 게 맞습니다.

---

## 시작하기

```bash
cd btc-trader
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1) 데이터 없이 엔진부터 확인
python scripts/run_backtest.py --synthetic --compare

# 2) 실제 시세 받기 (API 키 불필요)
python scripts/fetch_data.py --interval 1d --bars 1500

# 3) 실제 데이터로 백테스트
python scripts/run_backtest.py --csv data/KRW-BTC_1d.csv --compare

# 4) 실시간 페이퍼 트레이딩 (주문 안 나감)
python scripts/run_paper.py --strategy ma_cross --interval 60m
```

테스트:
```bash
python -m pytest tests/ -v
```

---

## 구조

```
btc_trader/
  indicators.py          SMA/EMA/RSI/볼린저/ATR/MACD
  config.py              수수료·리스크 설정, 키는 환경변수에서만
  data/
    upbit.py             업비트 공개 시세 API (재시도 + rate limit 대응)
    synthetic.py         네트워크 없이 엔진 테스트용 합성 데이터
  strategies/
    base.py              전략 인터페이스 (여기 상속해서 새로 만들면 됨)
    ma_cross.py          이동평균 교차 (추세추종)
    rsi_reversion.py     RSI 과매도 반등 (평균회귀)
    bb_breakout.py       볼린저 돌파 + 단순보유 기준선
  backtest/
    engine.py            이벤트 기반 백테스터
    metrics.py           CAGR/MDD/샤프/승률/손익비
  broker/
    paper.py             페이퍼 브로커 (재시작해도 포지션 유지)
  live/
    paper_runner.py      실시간 루프
```

---

## 백테스트가 거짓말하지 않게 만든 부분

대부분의 자동매매 백테스트가 실전보다 훨씬 좋게 나오는 이유는 정해져 있습니다.
이 엔진은 그 함정들을 구조적으로 막아뒀습니다.

**1. 미래를 훔쳐보지 않는다 (look-ahead 방지)**

봉 `t`의 종가로 만든 신호는 봉 `t+1`의 **시가**에 체결합니다. 종가를 보고
그 종가에 사는 건 현실에서 불가능합니다. `test_signal_executes_on_next_bar_not_same_bar`,
`test_only_final_bar_differs_when_truncated`가 이걸 검증합니다 — 뒤에 데이터를
더 붙여도 앞부분 자산곡선이 한 원도 바뀌지 않아야 통과합니다.

**2. 비용을 양쪽에 다 문다**

업비트 수수료 0.05%를 매수·매도 각각, 슬리피지 5bp를 불리한 방향으로 적용합니다.
`test_flat_market_with_fees_loses_money`는 **가격이 전혀 안 움직이는 시장에서
매매하면 반드시 손실**임을 확인합니다. 이 테스트가 통과하지 않는 백테스터는
단타 전략의 성과를 통째로 조작하게 됩니다.

**3. 손절은 봉 내부에서 판정한다**

종가가 아니라 봉의 **저가/고가**로 손절·익절 도달을 확인합니다. 같은 봉에서
둘 다 닿으면 손절을 우선합니다(보수적 가정).

**4. 기준선을 오염시키지 않는다**

`hold`(단순 보유)는 비교 기준선이므로 손절·부분투입을 적용하지 않고
전액 투입으로 따로 돌립니다. 이걸 안 하면 기준선이 33번 매매하는
이상한 결과가 나와 비교 자체가 무의미해집니다.

---

## 전략 만들기

`Strategy`를 상속하고 `generate_signals`만 구현하면 됩니다.
반환값은 목표 포지션(`1.0` = 롱, `0.0` = 현금)입니다.

```python
from btc_trader.strategies.base import Strategy
from btc_trader.indicators import rsi

class MyStrategy(Strategy):
    def __init__(self, period=14):
        self.period = period
        self.warmup = period + 1     # 지표 워밍업에 필요한 봉 수

    def generate_signals(self, df):
        self._validate(df)
        r = rsi(df["close"], self.period)
        return (r < 40).astype("float64")
```

`btc_trader/strategies/__init__.py`의 `STRATEGIES`에 등록하면
`--strategy` 옵션으로 바로 쓸 수 있습니다.

**주의**: `generate_signals`에서 `.shift(-1)`이나 `df.iloc[i+1]` 같은
미래 참조를 쓰면 백테스트가 환상적으로 나오고 실전에서 전액을 잃습니다.
지표는 전부 과거만 봅니다.

---

## 결과를 읽는 법

수익률만 보지 마세요. 같이 봐야 하는 것들:

| 지표 | 의미 | 위험 신호 |
|---|---|---|
| **MDD** | 최고점 대비 최대 낙폭 | -30% 넘으면 실전에서 못 버팁니다 |
| **거래 횟수** | 매매 빈도 | 너무 많으면 수수료로 죽습니다 |
| **샤프** | 위험 대비 수익 | 1 미만이면 재검토 |
| **손익비(PF)** | 총이익 / 총손실 | 1.5 미만이면 마진이 얇습니다 |
| **hold 대비** | 단순 보유와 비교 | **못 이기면 전략을 쓸 이유가 없습니다** |

합성 데이터(`--synthetic`)로 나온 수익률에는 **아무 의미가 없습니다.**
엔진이 제대로 도는지만 확인하는 용도입니다.

---

## 실거래로 넘어가기 전에

이 저장소는 여기까지입니다. 실주문을 붙이려면 최소한 이 순서를 지키세요.

1. **여러 구간에서 백테스트** — 상승장·하락장·횡보장을 각각. 한 구간에서만
   잘 나오는 파라미터는 그 구간에 과최적화된 겁니다.
2. **파라미터를 조금 흔들어 보기** — `fast=10`에서 잘 되는데 `fast=11`에서
   망가지면 그건 우연입니다.
3. **페이퍼 트레이딩 최소 2~4주** — 재시작, 네트워크 끊김, 봉 경계 문제는
   백테스트에서 절대 안 나옵니다.
4. **소액 실거래** — 잃어도 되는 금액으로. 페이퍼와 체결가가 얼마나
   차이나는지 확인하세요.

실거래를 붙일 때:
- 업비트 API 키는 **조회 + 주문만**. **출금 권한은 절대 켜지 마세요.**
- **IP 화이트리스트를 반드시 등록**하세요.
- 키는 `.env`(gitignore 처리됨)나 환경변수에만. 코드에 절대 넣지 마세요.
- 주문 금액 상한, 일일 손실 한도, 킬스위치를 **주문 코드보다 먼저** 만드세요.

---

## 솔직한 이야기

규칙 기반 지표 전략이 비트코인에서 안정적으로 시장을 이긴다는 근거는 약합니다.
이 도구의 가치는 "돈 버는 봇"이 아니라 **당신의 아이디어가 실제로는 안 통한다는
걸 돈 잃기 전에 알려주는 것**에 있습니다. 대부분의 전략은 수수료를 넘지 못합니다.
그걸 백테스트에서 확인하는 게 이 코드의 목적입니다.

전략이 `hold`를 이기지 못한다면, 그건 코드 문제가 아니라 전략 문제입니다.
