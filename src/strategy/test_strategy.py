import asyncio
import os
import sys

import aiosqlite
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.strategy.stat_strategy import StatisticalStrategy  # noqa: E402

DB_PATH = os.path.join(PROJECT_ROOT, "data", "trading_history.db")


async def main():
    if not os.path.exists(DB_PATH):
        print("Banco de dados não encontrado.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT id, timestamp, token_address, token_symbol, price_usd, vol_m5_usd, buys_m5, sells_m5
            FROM market_ticks
            ORDER BY id ASC
        """
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            cols = [description[0] for description in cursor.description]
            df = pd.DataFrame(rows, columns=cols)

    if df.empty:
        print("Banco de dados vazio.")
        return

    strategy = StatisticalStrategy(window=10, z_score_threshold=1.2, imbalance_buy_threshold=0.5)

    print("\n--- SIMULAÇÃO DE SINAIS ESTATÍSTICOS NO HISTÓRICO (ISOLADO POR MOEDA) ---")

    signals_found = 0
    for (token_addr, symbol), group_df in df.groupby(["token_address", "token_symbol"], sort=False):
        group_df = group_df.reset_index(drop=True)
        if len(group_df) < strategy.window:
            continue

        for i in range(strategy.window, len(group_df) + 1):
            sub_df = group_df.iloc[:i]
            signal = strategy.generate_signal(sub_df)

            if signal["action"] != "HOLD":
                signals_found += 1
                tick_id = int(sub_df.iloc[-1]["id"])
                print(
                    f"[{symbol}] Tick #{tick_id} ({i}/{len(group_df)}) | "
                    f"Ação: {signal['action']} | Preço: ${signal['price']:.8f} | "
                    f"Z-Score: {signal['z_score']:+.2f} | OFI: {signal['imbalance']:+.2f} | "
                    f"Motivo: {signal['reason']}"
                )

    if signals_found == 0:
        print("Nenhum gatilho extremo (BUY/SELL) isolado por moeda no histórico atual.")


if __name__ == "__main__":
    asyncio.run(main())