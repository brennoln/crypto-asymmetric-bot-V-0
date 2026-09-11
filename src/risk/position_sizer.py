from config.settings import settings

class RiskManager:
    def __init__(self):
        self.daily_drawdown_usd = 0.0

    def can_open_position(self) -> bool:
        """Circuit breaker para não ultrapassar perda máxima diária."""
        return self.daily_drawdown_usd < settings.MAX_DAILY_LOSS_USD

    def calculate_position_size(self, price_usd: float) -> float:
        """Calcula a quantidade de tokens para alocar o valor fixo por trade."""
        if price_usd <= 0:
            return 0.0
        return settings.POSITION_SIZE_USD / price_usd