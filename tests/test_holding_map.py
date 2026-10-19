import pytest

from src.strategy.holding_map import HoldingMap


def test_targets_liquidate_the_full_original_position():
    holding_map = HoldingMap()

    assert sum(target.sell_percent for target in holding_map.targets) == pytest.approx(1.0)


def test_targets_are_sorted_by_multiplier():
    multipliers = [target.multiplier for target in HoldingMap().targets]

    assert multipliers == sorted(multipliers)


def test_first_target_is_the_two_x_de_risking_step():
    first_target = HoldingMap().targets[0]

    assert first_target.multiplier == pytest.approx(2.0)
    assert first_target.sell_percent == pytest.approx(0.5)


def test_last_target_is_the_asymmetric_moonbag():
    last_target = HoldingMap().targets[-1]

    assert last_target.multiplier == pytest.approx(100.0)


def test_evaluate_exit_is_empty_for_a_non_positive_entry_price():
    holding_map = HoldingMap()

    assert holding_map.evaluate_exit(entry_price=0.0, current_price=10.0) == []
    assert holding_map.evaluate_exit(entry_price=-1.0, current_price=10.0) == []


def test_evaluate_exit_is_empty_below_the_first_target():
    assert HoldingMap().evaluate_exit(entry_price=1.0, current_price=1.9) == []


def test_evaluate_exit_reports_every_reached_target():
    actions = HoldingMap().evaluate_exit(entry_price=1.0, current_price=12.0)

    assert len(actions) == 2  # 2x e 10x


def test_evaluate_exit_reports_all_targets_on_a_full_parabolic_run():
    actions = HoldingMap().evaluate_exit(entry_price=1.0, current_price=150.0)

    assert len(actions) == len(HoldingMap().targets)
