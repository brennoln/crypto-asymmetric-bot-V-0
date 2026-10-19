import pandas as pd
import pytest

from analytics.analytics import calculate_tick_metrics


def _frame() -> pd.DataFrame:
    """Quatro ticks com volume crescente e pressão compradora decrescente."""
    return pd.DataFrame(
        {
            "timestamp": [1.0, 2.0, 3.0, 4.0],
            "price_usd": [100.0, 110.0, 121.0, 133.1],
            "vol_m5_usd": [10.0, 20.0, 30.0, 40.0],
            "buys_m5": [10, 10, 10, 5],
            "sells_m5": [0, 0, 0, 5],
        }
    )


def test_adds_the_expected_metric_columns():
    result = calculate_tick_metrics(_frame(), window=3)

    for column in ("returns", "volatility", "volume_zscore", "order_imbalance"):
        assert column in result.columns


def test_returns_are_percentage_change_of_price():
    result = calculate_tick_metrics(_frame(), window=3)

    assert pd.isna(result["returns"].iloc[0])
    assert result["returns"].iloc[1] == pytest.approx(0.1)


def test_volume_zscore_uses_the_rolling_window():
    # Última janela: [20, 30, 40] -> média 30, desvio amostral 10 -> z = 1.0
    result = calculate_tick_metrics(_frame(), window=3)

    assert result["volume_zscore"].iloc[-1] == pytest.approx(1.0)


def test_volume_zscore_is_zero_when_there_is_no_dispersion():
    frame = _frame()
    frame["vol_m5_usd"] = 100.0

    result = calculate_tick_metrics(frame, window=3)

    assert (result["volume_zscore"] == 0.0).all()


def test_order_imbalance_reflects_buy_and_sell_pressure():
    result = calculate_tick_metrics(_frame(), window=3)

    assert result["order_imbalance"].iloc[0] == pytest.approx(1.0)
    assert result["order_imbalance"].iloc[-1] == pytest.approx(0.0)


def test_order_imbalance_is_zero_when_no_orders_exist():
    frame = _frame()
    frame["buys_m5"] = 0
    frame["sells_m5"] = 0

    result = calculate_tick_metrics(frame, window=3)

    assert (result["order_imbalance"] == 0.0).all()


def test_does_not_mutate_the_input_frame():
    frame = _frame()
    original = frame.copy()

    calculate_tick_metrics(frame, window=3)

    pd.testing.assert_frame_equal(frame, original)


def test_price_change_to_zero_does_not_produce_infinite_returns():
    frame = _frame()
    frame["price_usd"] = [1.0, 0.0, 0.0, 0.0]

    result = calculate_tick_metrics(frame, window=3)

    assert not result["returns"].isin([float("inf"), float("-inf")]).any()


def test_rejects_a_window_smaller_than_two():
    with pytest.raises(ValueError):
        calculate_tick_metrics(_frame(), window=1)
