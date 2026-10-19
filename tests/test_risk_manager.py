from datetime import date

import pytest

from config.settings import settings
from src.risk.position_sizer import RiskManager

FUTURE_DAY = date(2099, 1, 1)


def test_position_size_allocates_the_fixed_unit_bet():
    expected = settings.POSITION_SIZE_USD / 2.0

    assert RiskManager().calculate_position_size(price_usd=2.0) == pytest.approx(expected)


def test_position_size_is_zero_for_a_non_positive_price():
    risk = RiskManager()

    assert risk.calculate_position_size(price_usd=0.0) == 0.0
    assert risk.calculate_position_size(price_usd=-5.0) == 0.0


def test_circuit_breaker_starts_open():
    assert RiskManager().can_open_position() is True


def test_circuit_breaker_trips_after_the_max_daily_loss():
    risk = RiskManager()

    risk.register_trade_result(-settings.MAX_DAILY_LOSS_USD)

    assert risk.can_open_position() is False
    assert risk.daily_drawdown_usd == pytest.approx(settings.MAX_DAILY_LOSS_USD)


def test_circuit_breaker_stays_open_below_the_max_daily_loss():
    risk = RiskManager()

    risk.register_trade_result(-(settings.MAX_DAILY_LOSS_USD - 1))

    assert risk.can_open_position() is True


def test_profits_offset_realized_losses():
    risk = RiskManager()

    risk.register_trade_result(-60.0)
    risk.register_trade_result(50.0)

    assert risk.daily_drawdown_usd == pytest.approx(10.0)
    assert risk.daily_realized_pnl_usd == pytest.approx(-10.0)


def test_drawdown_is_never_negative_on_a_profitable_day():
    risk = RiskManager()

    risk.register_trade_result(500.0)

    assert risk.daily_drawdown_usd == 0.0


def test_counters_reset_when_the_utc_day_rolls_over(monkeypatch):
    risk = RiskManager()
    risk.register_trade_result(-settings.MAX_DAILY_LOSS_USD)
    assert risk.can_open_position() is False

    monkeypatch.setattr(RiskManager, "_utc_day", staticmethod(lambda: FUTURE_DAY))

    assert risk.can_open_position() is True
    assert risk.daily_realized_pnl_usd == 0.0
    assert risk.daily_drawdown_usd == 0.0
