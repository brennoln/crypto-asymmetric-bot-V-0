from config.settings import settings

class SecurityAuditor:
    @staticmethod
    def audit_token(candidate: dict) -> tuple[bool, str]:
        liq = candidate["liquidity_usd"]
        age_min = candidate["age_minutes"]
        vol_m5 = candidate["vol_m5_usd"]
        buys = candidate["buys_m5"]
        sells = candidate["sells_m5"]

        # 1. Filtros de Liquidez
        if liq < settings.MIN_LIQUIDITY_USD:
            return False, f"Liquidez vulnerável a rugpull (${liq:,.2f} < ${settings.MIN_LIQUIDITY_USD:,.2f})"

        if liq > settings.MAX_LIQUIDITY_USD:
            return False, f"Liquidez excessiva para alvo 100x (${liq:,.2f})"

        # 2. Janela de Idade (Fuga dos primeiros minutos de Snipers)
        if age_min < settings.MIN_POOL_AGE_MINUTES:
            return False, f"Muito novo, sob fogo de sniper bots ({age_min:.1f}m < {settings.MIN_POOL_AGE_MINUTES}m)"

        if age_min > (settings.MAX_POOL_AGE_HOURS * 60):
            return False, f"Pool fora da janela inicial ({age_min / 60:.1f}h)"

        # 3. Ignição Imediata de Volume
        if vol_m5 < settings.MIN_VOLUME_M5_USD:
            return False, f"Sem volume acelerado nos últimos 5m (${vol_m5:,.2f})"

        if buys < settings.MIN_BUYS_M5:
            return False, f"Pouca quantidade de compras em 5m ({buys})"

        # 4. Pressão Compradora
        ratio = buys / max(sells, 1)
        if ratio < settings.MIN_BUY_SELL_RATIO:
            return False, f"Pressão de venda alta (Ratio Compras/Vendas: {ratio:.2f})"

        return True, "Aprovado no filtro de ignição assimétrica"