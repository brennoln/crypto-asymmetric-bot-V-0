import asyncio
import os
import sys

import aiosqlite
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analytics.analytics import calculate_tick_metrics  # noqa: E402

DB_PATH = os.path.join(PROJECT_ROOT, "data", "trading_history.db")


async def main():
    if not os.path.exists(DB_PATH):
        print(f"Erro: Banco de dados não encontrado no caminho: {DB_PATH}")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Busca os tokens que possuem pelo menos 10 ticks registrados
        token_query = """
            SELECT token_address, token_symbol, COUNT(*) as cnt
            FROM market_ticks
            GROUP BY token_address
            HAVING cnt >= 10
            ORDER BY MAX(id) DESC
            LIMIT 5
        """
        async with db.execute(token_query) as cursor:
            tokens = await cursor.fetchall()

        if not tokens:
            print("Nenhum token com pelo menos 10 ticks encontrado ainda.")
            return

        cols_to_show = [
            "price_usd",
            "vol_m5_usd",
            "volatility",
            "volume_zscore",
            "order_imbalance",
        ]

        for token_addr, symbol, cnt in tokens:
            query = """
                SELECT timestamp, price_usd, vol_m5_usd, buys_m5, sells_m5
                FROM market_ticks
                WHERE token_address = ?
                ORDER BY id DESC LIMIT 50
            """
            async with db.execute(query, (token_addr,)) as cursor:
                rows = await cursor.fetchall()
                cols = [description[0] for description in cursor.description]
                df = pd.DataFrame(rows, columns=cols)

            df = df.iloc[::-1].reset_index(drop=True)
            df_analyzed = calculate_tick_metrics(df, window=10)

            print(f"\n=== Métricas Estatísticas: {symbol} ({token_addr[:8]}...) [{cnt} ticks] ===")
            print(df_analyzed[cols_to_show].tail(8).to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())