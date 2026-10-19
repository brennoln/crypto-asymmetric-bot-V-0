import pandas as pd

from src.strategy.stat_strategy import StatisticalStrategy

WINDOW = 5
ROWS = 12


def _flat(value, length=ROWS):
    """Série constante, sem dispersão."""
    return [value] * length


def _spike(baseline, peak, length=ROWS):
    """Série constante que termina em um pico no último tick."""
    return [baseline] * (length - 1) + [peak]


def _frame(volumes, buys, sells):
    return pd.DataFrame(
        {
            "timestamp": [float(i) for i in range(len(volumes))],
            "price_usd": [1.0] * len(volumes),
            "vol_m5_usd": volumes,
            "buys_m5": buys,
            "sells_m5": sells,
        }
    )


def test_default_window_comes_from_the_constructor():
    assert StatisticalStrategy().window == 10


def test_holds_when_there_are_fewer_ticks_than_the_window():
    short = WINDOW - 1
    frame = _frame(_flat(10.0, short), _flat(5, short), _flat(5, short))

    signal = StatisticalStrategy(window=WINDOW).generate_signal(frame)

    assert signal["action"] == "HOLD"
    assert "Poucos dados" in signal["reason"]


def test_holds_on_neutral_conditions():
    frame = _frame(_flat(10.0), _flat(5), _flat(5))

    signal = StatisticalStrategy(window=WINDOW).generate_signal(frame)

    assert signal["action"] == "HOLD"
    assert "neutras" in signal["reason"]


def test_buys_on_a_volume_burst_with_buy_aggression():
    frame = _frame(_spike(10.0, 100.0), _spike(5, 20), _spike(5, 0))

    signal = StatisticalStrategy(window=WINDOW).generate_signal(frame)

    assert signal["action"] == "BUY"
    assert signal["z_score"] >= 1.2
    assert signal["imbalance"] >= 0.5


def test_sells_on_sustained_sell_aggression():
    frame = _frame(_flat(10.0), _flat(5), _spike(5, 15))

    signal = StatisticalStrategy(window=WINDOW).generate_signal(frame)

    assert signal["action"] == "SELL"
    assert signal["imbalance"] <= -0.3


def test_signal_payload_carries_the_decision_inputs():
    frame = _frame(_flat(10.0), _flat(5), _flat(5))

    signal = StatisticalStrategy(window=WINDOW).generate_signal(frame)

    for key in ("action", "price", "z_score", "imbalance", "volatility", "reason"):
        assert key in signal


def test_custom_z_score_threshold_suppresses_the_buy_signal():
    frame = _frame(_spike(10.0, 100.0), _spike(5, 20), _spike(5, 0))
    strategy = StatisticalStrategy(window=WINDOW, z_score_threshold=99.0)

    signal = strategy.generate_signal(frame)

    assert signal["action"] != "BUY"


def test_flat_prices_produce_zero_volatility():
    frame = _frame(_flat(10.0), _flat(5), _flat(5))

    signal = StatisticalStrategy(window=WINDOW).generate_signal(frame)

    assert signal["volatility"] == 0.0
