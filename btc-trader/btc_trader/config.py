"""설정 로딩.

비밀키는 코드나 설정 파일이 아니라 환경변수에서만 읽는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# 업비트 원화마켓 수수료 (2024 기준 0.05%). 본인 등급에 맞게 조정하세요.
UPBIT_FEE_RATE = 0.0005


@dataclass
class FeeModel:
    """거래 비용 모델.

    백테스트에서 이걸 빼먹으면 성과가 심하게 부풀려진다.
    특히 단타 전략일수록 치명적이다.
    """

    fee_rate: float = UPBIT_FEE_RATE
    # 슬리피지: 시장가 체결 시 불리한 방향으로 밀리는 정도 (bp 단위, 10bp = 0.1%)
    slippage_bp: float = 5.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bp / 10_000.0


@dataclass
class RiskConfig:
    """리스크 한도. 전략보다 이쪽이 훨씬 중요하다."""

    # 1회 진입에 쓸 자본 비율 (0.3 = 자본의 30%)
    position_pct: float = 0.3
    # 손절 폭 (0.03 = -3%)
    stop_loss_pct: float | None = 0.03
    # 익절 폭 (None이면 익절 안 함)
    take_profit_pct: float | None = None
    # ATR 기반 손절을 쓸 경우의 배수 (stop_loss_pct보다 우선)
    atr_stop_multiplier: float | None = None
    # 하루 누적 손실이 이 비율을 넘으면 당일 신규 진입 중단
    daily_loss_limit_pct: float | None = 0.05
    # 최소 주문 금액 (업비트 원화마켓은 5,000원)
    min_order_krw: float = 5_000.0


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    fees: FeeModel = field(default_factory=FeeModel)
    risk: RiskConfig = field(default_factory=RiskConfig)
    # 연율화 계수 계산에 쓰는, 1년치 봉 개수
    bars_per_year: float = 365.0


def get_upbit_keys() -> tuple[str | None, str | None]:
    """업비트 API 키를 환경변수에서 읽는다.

    절대 파일에 저장하거나 로그에 출력하지 말 것.
    페이퍼 트레이딩만 할 거면 키가 없어도 된다(공개 시세 API는 인증 불필요).
    """
    return os.getenv("UPBIT_ACCESS_KEY"), os.getenv("UPBIT_SECRET_KEY")


def mask_key(key: str | None) -> str:
    """로그에 찍어도 되는 형태로 키를 가린다."""
    if not key:
        return "(미설정)"
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-2:]} (len {len(key)})"
