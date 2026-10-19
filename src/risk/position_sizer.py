from datetime import date, datetime, timezone

from config.settings import settings


class RiskManager:
    """Guardrails de portfólio: sizing de unidade fixa e circuit breaker de perda diária."""

    def __init__(self):
        self._current_day: date = self._utc_day()
        self.daily_realized_pnl_usd: float = 0.0

    @staticmethod
    def _utc_day() -> date:
        return datetime.now(timezone.utc).date()

    def _roll_day_if_needed(self) -> None:
        """Zera os acumuladores quando o dia UTC muda."""
        today = self._utc_day()
        if today != self._current_day:
            self._current_day = today
            self.daily_realized_pnl_usd = 0.0

    @property
    def daily_drawdown_usd(self) -> float:
        """Perda líquida acumulada no dia (sempre >= 0)."""
        return max(0.0, -self.daily_realized_pnl_usd)

    def register_trade_result(self, net_pnl_usd: float) -> None:
        """Contabiliza o resultado de uma operação encerrada no acumulado do dia."""
        self._roll_day_if_needed()
        self.daily_realized_pnl_usd += net_pnl_usd

    def can_open_position(self) -> bool:
        """Circuit breaker para não ultrapassar perda máxima diária."""
        self._roll_day_if_needed()
        return self.daily_drawdown_usd < settings.MAX_DAILY_LOSS_USD

    def calculate_position_size(self, price_usd: float) -> float:
        """Calcula a quantidade de tokens para alocar o valor fixo por trade."""
        if price_usd <= 0:
            return 0.0
        return settings.POSITION_SIZE_USD / price_usd
