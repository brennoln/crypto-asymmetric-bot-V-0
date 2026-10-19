import time
from datetime import datetime, timezone

from data.database import db_manager
from src.utils.logger import log


class PaperExecutionClient:
    """Simulated order management system.

    Tracks open positions in memory and mirrors every state transition into
    SQLite so that closed trades are always reconcilable.
    """

    def __init__(self, risk_manager=None):
        self.risk_manager = risk_manager
        self.positions: list[dict] = []

    def _net_pnl(self, trade: dict) -> float:
        return trade["realized_pnl_usd"] - trade["invested_usd"]

    def _settle(self, trade: dict) -> float:
        """Registra o resultado financeiro no RiskManager e devolve o PnL líquido."""
        net_pnl = self._net_pnl(trade)
        if self.risk_manager is not None:
            self.risk_manager.register_trade_result(net_pnl)
        return net_pnl

    def prune_closed_positions(self, max_closed_history: int = 100) -> None:
        """Evita vazamento de memória mantendo todas as OPEN e apenas as últimas fechadas."""
        open_trades = [p for p in self.positions if p["status"] == "OPEN"]
        closed_trades = [p for p in self.positions if p["status"] != "OPEN"]
        if len(closed_trades) > max_closed_history:
            closed_trades = closed_trades[-max_closed_history:]
        self.positions = open_trades + closed_trades

    async def open_position(self, candidate: dict, token_amount: float, invested_usd: float) -> dict:
        trade = {
            "token_symbol": candidate["symbol"],
            "token_address": candidate["token_address"],
            "chain_id": candidate["chain_id"],
            "pair_address": candidate["pair_address"],
            "entry_price": candidate["price_usd"],
            "current_price": candidate["price_usd"],
            "initial_amount": token_amount,
            "remaining_amount": token_amount,
            "invested_usd": invested_usd,
            "realized_pnl_usd": 0.0,
            "executed_targets": set(),
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "opened_timestamp": time.time(),
            "status": "OPEN",
        }

        self.positions.append(trade)
        await db_manager.insert_trade(trade)

        score_info = (
            f" | Score: {candidate['ignition_score']:.1f}"
            if "ignition_score" in candidate
            else ""
        )
        log.info(
            f"🚀 [COMPRA PAPER] {candidate['symbol']} | "
            f"Preço: ${candidate['price_usd']:.8f} | "
            f"Alocação: ${invested_usd:.2f} | "
            f"Tokens: {token_amount:,.2f}{score_info}"
        )
        return trade

    async def execute_partial_sell(
        self, trade: dict, multiplier: float, sell_pct: float, current_price: float
    ):
        """Executa a liquidação parcial programada pelo Holding Map."""
        tokens_to_sell = min(trade["initial_amount"] * sell_pct, trade["remaining_amount"])
        revenue_usd = tokens_to_sell * current_price

        trade["remaining_amount"] -= tokens_to_sell
        trade["realized_pnl_usd"] += revenue_usd
        trade["executed_targets"].add(multiplier)

        log.info(
            f"💰 [TAKE PROFIT {multiplier:.1f}x] {trade['token_symbol']} atingiu {multiplier:.1f}x! "
            f"Vendido {sell_pct * 100:.0f}% ({tokens_to_sell:,.2f} tokens) por ${revenue_usd:.2f} | "
            f"Retorno acumulado: ${trade['realized_pnl_usd']:.2f} (Entrada: ${trade['invested_usd']:.2f})"
        )

        if trade["remaining_amount"] <= 1e-6:
            trade["remaining_amount"] = 0.0
            trade["status"] = "CLOSED"
            duration_sec = time.time() - trade["opened_timestamp"]
            await db_manager.close_trade(
                trade,
                exit_reason="Todos os alvos do Holding Map realizados",
                duration_sec=duration_sec,
            )
            net_pnl = self._settle(trade)
            log.info(
                f"🏁 [POSIÇÃO ENCERRADA] {trade['token_symbol']} realizou todos os alvos. "
                f"PnL Líquido: {net_pnl:+.2f}"
            )
        else:
            await db_manager.update_trade_partial(trade)

    async def drop_stagnant_position(self, trade: dict, age_min: float, current_price: float):
        """Vende a mercado o saldo restante de moedas que estagnaram para liberar o slot."""
        remaining = trade["remaining_amount"]
        recovered_usd = remaining * current_price

        trade["realized_pnl_usd"] += recovered_usd
        trade["remaining_amount"] = 0.0
        trade["status"] = "STAGNANT"

        duration_sec = time.time() - trade["opened_timestamp"]
        await db_manager.close_trade(
            trade, exit_reason="Time-Stop / Inércia", duration_sec=duration_sec
        )

        net_pnl = self._settle(trade)
        ratio = current_price / trade["entry_price"] if trade["entry_price"] > 0 else 0
        var_pct = (ratio - 1.0) * 100

        if net_pnl >= 0:
            log.info(
                f"⏳ [ROTAÇÃO / VENDA] {trade['token_symbol']} liquidado a mercado após {age_min:.1f}m. "
                f"Variação: {var_pct:+.1f}% | Recuperado: ${recovered_usd:.2f} | Lucro: +${net_pnl:.2f}"
            )
        else:
            log.warning(
                f"⏳ [ROTAÇÃO / VENDA] {trade['token_symbol']} liquidado a mercado após {age_min:.1f}m. "
                f"Variação: {var_pct:+.1f}% | Recuperado: ${recovered_usd:.2f} | Prejuízo: -${abs(net_pnl):.2f}"
            )

    async def drop_dead_position(self, trade: dict, reason: str, current_price: float):
        """Vende a mercado o saldo restante ao disparar stop técnico, fluxo ou dreno de liquidez."""
        remaining = trade["remaining_amount"]
        recovered_usd = remaining * current_price

        trade["realized_pnl_usd"] += recovered_usd
        trade["remaining_amount"] = 0.0
        trade["status"] = "DROPPED"

        duration_sec = time.time() - trade["opened_timestamp"]
        await db_manager.close_trade(trade, exit_reason=reason, duration_sec=duration_sec)

        net_pnl = self._settle(trade)
        log.warning(
            f"🚫 [STOP A MERCADO] {trade['token_symbol']} liquidado. "
            f"Motivo: {reason} | Recuperado: ${recovered_usd:.2f} | PnL Líquido: {net_pnl:+.2f}"
        )

    async def close_position_loss(self, trade: dict, reason: str):
        """Encerra a posição em caso de rugpull absoluto (onde a liquidez zerou por completo)."""
        trade["status"] = "DEAD"
        trade["remaining_amount"] = 0.0

        duration_sec = time.time() - trade["opened_timestamp"]
        await db_manager.close_trade(trade, exit_reason=reason, duration_sec=duration_sec)

        net_pnl = self._settle(trade)
        log.warning(
            f"💀 [RUGPULL / PERDA TOTAL] {trade['token_symbol']} zerado. "
            f"Motivo: {reason} | Prejuízo: -${abs(net_pnl):.2f}"
        )