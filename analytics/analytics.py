import numpy as np
import pandas as pd

# Mínimo de observações para que um desvio padrão móvel faça sentido.
MIN_WINDOW = 2


def calculate_tick_metrics(ticks_df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Calcula métricas estatísticas em janelas móveis sobre o histórico de ticks.

    Devolve uma cópia do DataFrame de entrada acrescida de ``returns``,
    ``volatility``, ``volume_zscore`` e ``order_imbalance``. Quando a janela não
    possui dispersão suficiente a métrica correspondente é 0 (em vez de inf/NaN).
    """
    if window < MIN_WINDOW:
        raise ValueError(f"window precisa ser >= {MIN_WINDOW} para o desvio padrão")

    df = ticks_df.copy()

    # 1. Retorno percentual entre ticks (infinitos viram NaN, nunca inf)
    df["returns"] = df["price_usd"].pct_change().replace([np.inf, -np.inf], np.nan)

    # 2. Volatilidade móvel (desvio padrão dos retornos)
    df["volatility"] = df["returns"].rolling(window=window).std()

    # 3. Z-score de volume. O divisor recebe NaN onde não há dispersão para que
    #    a divisão não gere inf e o resultado seja zerado no fillna.
    mean_vol = df["vol_m5_usd"].rolling(window=window).mean()
    std_vol = df["vol_m5_usd"].rolling(window=window).std()
    safe_std = std_vol.where(std_vol > 0)
    df["volume_zscore"] = ((df["vol_m5_usd"] - mean_vol) / safe_std).fillna(0.0)

    # 4. Desequilíbrio de ordens (Order Imbalance), limitado a [-1, 1]
    total_orders = df["buys_m5"] + df["sells_m5"]
    safe_total = total_orders.where(total_orders > 0)
    df["order_imbalance"] = ((df["buys_m5"] - df["sells_m5"]) / safe_total).fillna(0.0)

    return df
