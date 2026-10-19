import aiosqlite
import pytest

from data.database import db_manager


def _trade(**overrides) -> dict:
    trade = {
        "token_symbol": "TEST",
        "token_address": "0xabc",
        "chain_id": "solana",
        "pair_address": "PAIR1",
        "entry_price": 0.5,
        "invested_usd": 15.0,
        "realized_pnl_usd": 0.0,
        "opened_at": "2026-01-01T00:00:00+00:00",
        "status": "OPEN",
    }
    trade.update(overrides)
    return trade


async def _fetchall(sql: str):
    async with aiosqlite.connect(db_manager.db_path) as db:
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()


async def test_init_db_creates_both_tables(temp_db):
    await db_manager.init_db()

    tables = {
        row[0]
        for row in await _fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
    }

    assert {"market_ticks", "trade_records"} <= tables


async def test_init_db_is_idempotent(temp_db):
    await db_manager.init_db()
    await db_manager.init_db()

    assert (await _fetchall("SELECT COUNT(*) FROM trade_records"))[0][0] == 0


async def test_log_tick_persists_a_market_observation(temp_db):
    await db_manager.init_db()

    await db_manager.log_tick(
        token_address="0xabc",
        symbol="TEST",
        price=0.5,
        liq=10000.0,
        vol_m5=2500.0,
        buys=30,
        sells=10,
    )

    rows = await _fetchall(
        "SELECT token_address, token_symbol, price_usd, liquidity_usd, vol_m5_usd, "
        "buys_m5, sells_m5 FROM market_ticks"
    )

    assert rows == [("0xabc", "TEST", 0.5, 10000.0, 2500.0, 30, 10)]


async def test_insert_trade_opens_a_position(temp_db):
    await db_manager.init_db()

    await db_manager.insert_trade(_trade())

    rows = await _fetchall("SELECT status, closed_at, exit_reason FROM trade_records")

    assert rows == [("OPEN", None, None)]


async def test_close_trade_settles_the_position(temp_db):
    await db_manager.init_db()
    trade = _trade()
    await db_manager.insert_trade(trade)

    trade["realized_pnl_usd"] = 18.0
    trade["status"] = "CLOSED"
    await db_manager.close_trade(trade, exit_reason="alvo atingido", duration_sec=120.0)

    row = (
        await _fetchall(
            "SELECT status, realized_pnl_usd, hold_duration_sec, exit_reason, closed_at "
            "FROM trade_records"
        )
    )[0]
    status, pnl, duration, reason, closed_at = row

    assert status == "CLOSED"
    assert pnl == pytest.approx(18.0)
    assert duration == pytest.approx(120.0)
    assert reason == "alvo atingido"
    assert closed_at is not None


async def test_two_positions_on_the_same_token_get_distinct_ids(temp_db):
    await db_manager.init_db()

    await db_manager.insert_trade(_trade(opened_at="2026-01-01T00:00:00+00:00"))
    await db_manager.insert_trade(_trade(opened_at="2026-01-02T00:00:00+00:00"))

    count = (await _fetchall("SELECT COUNT(*) FROM trade_records"))[0][0]

    assert count == 2


async def test_connections_enable_write_ahead_logging(temp_db):
    await db_manager.init_db()

    async with aiosqlite.connect(db_manager.db_path) as db:
        async with db.execute("PRAGMA journal_mode") as cursor:
            mode = (await cursor.fetchone())[0]

    assert mode.lower() == "wal"
