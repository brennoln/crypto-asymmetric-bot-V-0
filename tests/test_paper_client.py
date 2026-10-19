import aiosqlite
import pytest

from data.database import db_manager
from src.execution.paper_client import PaperExecutionClient
from src.risk.position_sizer import RiskManager

# Escada do HoldingMap: (multiplier, sell_pct, preço no gatilho)
LADDER = ((2.0, 0.50, 2.0), (10.0, 0.20, 10.0), (30.0, 0.15, 30.0), (100.0, 0.15, 100.0))
UNIT_SIZE = 10.0


def _candidate(**overrides) -> dict:
    candidate = {
        "symbol": "TEST",
        "token_address": "0xabc",
        "chain_id": "solana",
        "pair_address": "PAIR1",
        "price_usd": 1.0,
    }
    candidate.update(overrides)
    return candidate


async def _trade_row():
    async with aiosqlite.connect(db_manager.db_path) as db:
        async with db.execute(
            "SELECT status, exit_reason, closed_at FROM trade_records"
        ) as cursor:
            return await cursor.fetchone()


async def test_open_position_records_the_trade_in_the_database(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()

    trade = await client.open_position(
        _candidate(), token_amount=UNIT_SIZE, invested_usd=UNIT_SIZE
    )

    assert trade["status"] == "OPEN"
    assert trade["remaining_amount"] == pytest.approx(UNIT_SIZE)
    assert await _trade_row() == ("OPEN", None, None)


async def test_opened_at_carries_the_full_utc_timestamp(temp_db):
    await db_manager.init_db()

    trade = await PaperExecutionClient().open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    assert "T" in trade["opened_at"]
    assert trade["opened_at"].endswith("+00:00")


async def test_partial_sell_keeps_the_position_open_while_size_remains(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.execute_partial_sell(trade, multiplier=2.0, sell_pct=0.50, current_price=2.0)

    assert trade["status"] == "OPEN"
    assert trade["remaining_amount"] == pytest.approx(5.0)
    assert await _trade_row() == ("OPEN", None, None)


async def test_the_two_x_step_makes_the_position_risk_free(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.execute_partial_sell(trade, multiplier=2.0, sell_pct=0.50, current_price=2.0)

    assert trade["realized_pnl_usd"] == pytest.approx(UNIT_SIZE)
    assert trade["realized_pnl_usd"] - trade["invested_usd"] == pytest.approx(0.0)


async def test_full_ladder_persists_the_closed_status(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    for multiplier, sell_pct, price in LADDER:
        await client.execute_partial_sell(trade, multiplier, sell_pct, current_price=price)

    assert trade["status"] == "CLOSED"
    assert trade["remaining_amount"] == 0.0

    status, exit_reason, closed_at = await _trade_row()
    assert status == "CLOSED"
    assert exit_reason
    assert closed_at is not None


async def test_a_fully_realized_position_settles_exactly_once(temp_db):
    await db_manager.init_db()
    risk = RiskManager()
    client = PaperExecutionClient(risk_manager=risk)
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    for multiplier, sell_pct, price in LADDER:
        await client.execute_partial_sell(trade, multiplier, sell_pct, current_price=price)

    # Receita: 10 + 20 + 45 + 150 = 225 -> líquido 215, contabilizado uma única vez.
    assert risk.daily_realized_pnl_usd == pytest.approx(215.0)


async def test_drop_dead_position_persists_the_stop(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.drop_dead_position(trade, reason="stop técnico", current_price=0.5)

    assert trade["status"] == "DROPPED"
    assert trade["realized_pnl_usd"] == pytest.approx(5.0)

    status, exit_reason, closed_at = await _trade_row()
    assert status == "DROPPED"
    assert exit_reason == "stop técnico"
    assert closed_at is not None


async def test_drop_stagnant_position_persists_the_rotation(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.drop_stagnant_position(trade, age_min=6.0, current_price=1.2)

    assert trade["status"] == "STAGNANT"

    status, exit_reason, closed_at = await _trade_row()
    assert status == "STAGNANT"
    assert exit_reason == "Time-Stop / Inércia"
    assert closed_at is not None


async def test_close_position_loss_persists_a_rugpull(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.close_position_loss(trade, reason="Liquidez drenada")

    assert trade["status"] == "DEAD"
    assert trade["remaining_amount"] == 0.0

    status, exit_reason, closed_at = await _trade_row()
    assert status == "DEAD"
    assert exit_reason == "Liquidez drenada"
    assert closed_at is not None


async def test_a_losing_close_is_reported_to_the_risk_manager(temp_db):
    await db_manager.init_db()
    risk = RiskManager()
    client = PaperExecutionClient(risk_manager=risk)
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.drop_dead_position(trade, reason="stop técnico", current_price=0.5)

    assert risk.daily_realized_pnl_usd == pytest.approx(-5.0)
    assert risk.daily_drawdown_usd == pytest.approx(5.0)


async def test_a_winning_close_does_not_add_to_the_drawdown(temp_db):
    await db_manager.init_db()
    risk = RiskManager()
    client = PaperExecutionClient(risk_manager=risk)
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.drop_dead_position(trade, reason="alvo atingido", current_price=3.0)

    assert risk.daily_realized_pnl_usd == pytest.approx(20.0)
    assert risk.daily_drawdown_usd == 0.0


async def test_execution_client_works_without_a_risk_manager(temp_db):
    await db_manager.init_db()
    client = PaperExecutionClient()
    trade = await client.open_position(_candidate(), UNIT_SIZE, UNIT_SIZE)

    await client.drop_dead_position(trade, reason="stop técnico", current_price=0.5)

    assert trade["status"] == "DROPPED"
