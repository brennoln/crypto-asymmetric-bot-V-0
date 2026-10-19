import pandas as pd
from analytics.analytics import calculate_tick_metrics


class StatisticalStrategy:
    def __init__(
        self,
        window: int = 10,
        z_score_threshold: float = 1.2,
        imbalance_buy_threshold: float = 0.5,
        imbalance_sell_threshold: float = -0.3,
    ):
        """
        Estratégia Quantitativa baseada em Anomalia de Volume (Z-Score)
        e Desequilíbrio de Ordens (Order Imbalance).
        """
        self.window = window
        self.z_score_threshold = z_score_threshold
        self.imbalance_buy_threshold = imbalance_buy_threshold
        self.imbalance_sell_threshold = imbalance_sell_threshold

    def generate_signal(self, ticks_df: pd.DataFrame) -> dict:
        """
        Processa os ticks e retorna a decisão estatística para o último tick capturado.
        """
        if len(ticks_df) < self.window:
            return {"action": "HOLD", "reason": "Poucos dados para janela móvel"}

        # 1. Calcula as métricas estatísticas
        df_analyzed = calculate_tick_metrics(ticks_df, window=self.window)
        latest = df_analyzed.iloc[-1]

        z_score = latest["volume_zscore"]
        imbalance = latest["order_imbalance"]
        volatility = latest["volatility"]
        current_price = latest["price_usd"]

        # 2. Regra de Entrada (Gatilho Estatístico Comprador)
        # Volume atípico (Z-Score alto) + Pressão compradora forte (Imbalance alto)
        if z_score >= self.z_score_threshold and imbalance >= self.imbalance_buy_threshold:
            return {
                "action": "BUY",
                "price": current_price,
                "z_score": round(z_score, 2),
                "imbalance": round(imbalance, 2),
                "volatility": round(volatility, 4),
                "reason": f"Surto estatístico de volume (Z={z_score:.2f}) e agressão compradora ({imbalance:.2f})",
            }

        # 3. Regra de Saída/Venda (Agressão vendedora ou exaustão)
        elif imbalance <= self.imbalance_sell_threshold:
            return {
                "action": "SELL",
                "price": current_price,
                "z_score": round(z_score, 2),
                "imbalance": round(imbalance, 2),
                "volatility": round(volatility, 4),
                "reason": f"Forte pressão vendedora detectada (Imbalance={imbalance:.2f})",
            }

        return {
            "action": "HOLD",
            "price": current_price,
            "z_score": round(z_score, 2),
            "imbalance": round(imbalance, 2),
            "volatility": round(volatility, 4),
            "reason": "Condições estatísticas neutras",
        }