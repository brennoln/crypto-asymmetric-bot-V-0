import asyncio
import time
from collections import deque

import aiohttp
import pandas as pd

from config.settings import settings
from data.database import db_manager
from src.audit.holder_analyzer import SecurityAuditor
from src.execution.paper_client import PaperExecutionClient
from src.risk.position_sizer import RiskManager
from src.scanner.dex_scanner import DexScanner
from src.strategy.holding_map import HoldingMap
from src.strategy.stat_strategy import StatisticalStrategy
from src.utils.logger import log

MAX_SEEN_TOKENS = 5_000

CIRCUIT_BREAKER_COOLDOWN_SEC = 60.0
FULL_SLOTS_COOLDOWN_SEC = 6.0
SCAN_INTERVAL_SEC = 10.0
PORTFOLIO_SUMMARY_INTERVAL_SEC = 60.0

MAX_PAIRS_PER_REQUEST = 25

# Parâmetros de Trailing Stop Dinâmico (Proteção de Topo / High-Water Mark)
TRAILING_ACTIVATION_RATIO = 1.40  # Ativa proteção de lucro após +40% de alta
TRAILING_DROP_FROM_PEAK = 0.25    # Realiza se cair 25% a partir do preço máximo atingido


async def position_watcher(
    session: aiohttp.ClientSession,
    execution_client: PaperExecutionClient,
    holding_map: HoldingMap,
    stat_strategy: StatisticalStrategy | None = None,
):
    """Monitor de alto desempenho com deduplicação de ticks, Trailing Stop e estratégia estatística."""
    if stat_strategy is None:
        stat_strategy = StatisticalStrategy(
            window=settings.STAT_WINDOW_TICKS,
            z_score_threshold=settings.STAT_ZSCORE_THRESHOLD,
            imbalance_buy_threshold=settings.STAT_IMBALANCE_BUY,
            imbalance_sell_threshold=settings.STAT_IMBALANCE_SELL,
        )

    tick_buffers: dict[str, deque[dict]] = {}
    last_signals: dict[str, dict] = {}
    stop_confirmation_counts: dict[str, int] = {}
    max_buffer_len = max(stat_strategy.window * 3, 30)
    last_summary_ts = time.time()

    while True:
        execution_client.prune_closed_positions()
        active_trades = [p for p in execution_client.positions if p["status"] == "OPEN"]

        active_addrs = {t["token_address"] for t in active_trades}
        for addr in list(tick_buffers.keys()):
            if addr not in active_addrs:
                tick_buffers.pop(addr, None)
                last_signals.pop(addr, None)
                stop_confirmation_counts.pop(addr, None)

        if active_trades:
            by_chain: dict[str, list[dict]] = {}
            for trade in active_trades:
                by_chain.setdefault(trade["chain_id"], []).append(trade)

            for chain_id, trades in by_chain.items():
                pairs_str = ",".join([t["pair_address"] for t in trades[:MAX_PAIRS_PER_REQUEST]])
                url = f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pairs_str}"

                try:
                    async with session.get(url, timeout=5) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                    pairs_info = {p.get("pairAddress"): p for p in data.get("pairs", []) if p}
                    ticks_to_persist: list[dict] = []

                    for trade in trades:
                        if trade["status"] != "OPEN":
                            continue

                        pair_data = pairs_info.get(trade["pair_address"])
                        if not pair_data:
                            continue

                        current_price = float(pair_data.get("priceUsd", 0) or 0)
                        current_liq = float(pair_data.get("liquidity", {}).get("usd", 0) or 0)
                        vol_m5 = float(pair_data.get("volume", {}).get("m5", 0) or 0)
                        txns_m5 = pair_data.get("txns", {}).get("m5", {}) or {}
                        buys = int(txns_m5.get("buys", 0) or 0)
                        sells = int(txns_m5.get("sells", 0) or 0)

                        # 0. Rugpull absoluto: liquidez drenada e sem cotação válida.
                        if current_price <= 0 and current_liq < settings.MIN_RUNNING_LIQUIDITY_USD:
                            await execution_client.close_position_loss(
                                trade=trade,
                                reason=f"Liquidez drenada (${current_liq:,.2f}) sem cotação válida",
                            )
                            continue

                        if current_price <= 0:
                            continue

                        token_addr = trade["token_address"]
                        now_ts = time.time()

                        buf = tick_buffers.setdefault(
                            token_addr, deque(maxlen=max_buffer_len)
                        )

                        # Deduplicação de Tick: Só registra no buffer e no banco se o mercado mudou
                        is_new_market_tick = (
                            not buf
                            or buf[-1]["price_usd"] != current_price
                            or buf[-1]["vol_m5_usd"] != vol_m5
                            or buf[-1]["buys_m5"] != buys
                            or buf[-1]["sells_m5"] != sells
                        )

                        if is_new_market_tick:
                            ticks_to_persist.append(
                                {
                                    "token_address": token_addr,
                                    "symbol": trade["token_symbol"],
                                    "price": current_price,
                                    "liq": current_liq,
                                    "vol_m5": vol_m5,
                                    "buys": buys,
                                    "sells": sells,
                                }
                            )
                            buf.append(
                                {
                                    "timestamp": now_ts,
                                    "price_usd": current_price,
                                    "vol_m5_usd": vol_m5,
                                    "buys_m5": buys,
                                    "sells_m5": sells,
                                }
                            )

                        trade["current_price"] = current_price
                        peak_price = max(trade.get("peak_price", trade["entry_price"]), current_price)
                        trade["peak_price"] = peak_price

                        ratio = (
                            current_price / trade["entry_price"]
                            if trade["entry_price"] > 0
                            else 0
                        )
                        peak_ratio = (
                            peak_price / trade["entry_price"]
                            if trade["entry_price"] > 0
                            else 0
                        )
                        trade_age_min = (now_ts - trade["opened_timestamp"]) / 60.0

                        # 1. Poda por Dreno de Liquidez
                        if current_liq < settings.MIN_RUNNING_LIQUIDITY_USD:
                            await execution_client.drop_dead_position(
                                trade=trade,
                                reason=f"Liquidez drenada para ${current_liq:,.2f}",
                                current_price=current_price,
                            )
                            continue

                        # 2. Poda por Queda (>35%) com filtro anti-wick
                        if ratio <= (1.0 - settings.HARD_STOP_LOSS_PCT):
                            strikes = stop_confirmation_counts.get(token_addr, 0) + 1
                            stop_confirmation_counts[token_addr] = strikes

                            if ratio < 0.20 and strikes < 2 and current_liq >= settings.MIN_LIQUIDITY_USD:
                                log.warning(
                                    f"⚠️ [ANTI-WICK] {trade['token_symbol']} reportou queda atípica ({(1 - ratio) * 100:.1f}%) "
                                    f"com liquidez intacta (${current_liq:,.0f}). Aguardando confirmação (1/2)..."
                                )
                                continue

                            await execution_client.drop_dead_position(
                                trade=trade,
                                reason=f"Queda abrupta de {(1 - ratio) * 100:.1f}% detectada",
                                current_price=current_price,
                            )
                            continue
                        else:
                            stop_confirmation_counts[token_addr] = 0

                        # 3. Realização de Alvos Parciais do Holding Map (Checado antes do Trailing Stop)
                        for target in holding_map.targets:
                            if trade["status"] != "OPEN":
                                break
                            if (
                                ratio >= target.multiplier
                                and target.multiplier not in trade["executed_targets"]
                            ):
                                await execution_client.execute_partial_sell(
                                    trade=trade,
                                    multiplier=target.multiplier,
                                    sell_pct=target.sell_percent,
                                    current_price=current_price,
                                )

                        if trade["status"] != "OPEN":
                            continue

                        # 4. Trailing Stop Dinâmico (Protege lucros após atingir >= 1.40x)
                        if peak_ratio >= TRAILING_ACTIVATION_RATIO:
                            drawdown_from_peak = (peak_price - current_price) / peak_price
                            if drawdown_from_peak >= TRAILING_DROP_FROM_PEAK and ratio > 1.05:
                                await execution_client.drop_dead_position(
                                    trade=trade,
                                    reason=(
                                        f"Trailing Stop: recuo de {drawdown_from_peak * 100:.1f}% "
                                        f"desde o topo ({peak_ratio:.2f}x -> {ratio:.2f}x)"
                                    ),
                                    current_price=current_price,
                                )
                                continue

                        # 5. Poda por Inércia (Time-Stop) — Posições que já bateram 2x (Risk-Free) têm tempo estendido
                        is_risk_free = 2.0 in trade["executed_targets"]
                        if (
                            not is_risk_free
                            and trade_age_min >= settings.MAX_HOLD_TIME_MINUTES
                            and ratio < (1.0 + settings.MIN_PROFIT_TO_EXTEND_TIME)
                        ):
                            await execution_client.drop_stagnant_position(
                                trade=trade,
                                age_min=trade_age_min,
                                current_price=current_price,
                            )
                            continue

                        # 6. Avaliação da StatisticalStrategy (Apenas recalculada quando chega tick novo)
                        stat_tag = ""
                        if len(buf) >= stat_strategy.window:
                            if is_new_market_tick or token_addr not in last_signals:
                                ticks_df = pd.DataFrame(list(buf))
                                last_signals[token_addr] = stat_strategy.generate_signal(ticks_df)

                            signal = last_signals[token_addr]
                            stat_tag = (
                                f" | Z: {signal['z_score']:+.2f} | "
                                f"OFI: {signal['imbalance']:+.2f} ({signal['action']})"
                            )

                            if (
                                signal["action"] == "SELL"
                                and trade_age_min >= settings.STAT_MIN_AGE_FOR_EXIT_MIN
                                and ratio < 1.50
                            ):
                                await execution_client.drop_dead_position(
                                    trade=trade,
                                    reason=f"Exaustão estatística: {signal['reason']}",
                                    current_price=current_price,
                                )
                                continue

                        # Log enxuto: mostra sempre que o mercado atualizar na API
                        if is_new_market_tick:
                            pnl_pct = (ratio - 1.0) * 100
                            log.info(
                                f"📊 [TRACKING] {trade['token_symbol']} | Preço: ${current_price:.8f} | "
                                f"Variação: {pnl_pct:+.1f}% ({ratio:.2f}x | Topo: {peak_ratio:.2f}x){stat_tag}"
                            )

                    if ticks_to_persist:
                        await db_manager.log_ticks_batch(ticks_to_persist)

                except Exception as e:
                    log.warning(f"Falha na checagem em lote ({chain_id}): {e}")

        now_check = time.time()
        if now_check - last_summary_ts >= PORTFOLIO_SUMMARY_INTERVAL_SEC:
            last_summary_ts = now_check
            open_now = [p for p in execution_client.positions if p["status"] == "OPEN"]
            unrealized_pnl = sum(
                (p["remaining_amount"] * p["current_price"]) + p["realized_pnl_usd"] - p["invested_usd"]
                for p in open_now
            )
            realized_day = (
                execution_client.risk_manager.daily_realized_pnl_usd
                if execution_client.risk_manager
                else 0.0
            )
            log.info(
                f"📈 [RESUMO CARTEIRA] Ativas: {len(open_now)}/{settings.MAX_ACTIVE_POSITIONS} | "
                f"PnL Aberto (Não-Realizado): ${unrealized_pnl:+.2f} | "
                f"PnL Fechado (Dia): ${realized_day:+.2f} | "
                f"Balanço Total: ${(unrealized_pnl + realized_day):+.2f}"
            )

        await asyncio.sleep(settings.WATCHER_INTERVAL_SEC)


async def market_scanner(
    session: aiohttp.ClientSession,
    execution_client: PaperExecutionClient,
    risk_engine: RiskManager,
):
    """Varredura multi-fonte contínua com reavaliação dinâmica de candidatos jovens."""
    scanner = DexScanner(session)
    seen_tokens: set[str] = set()
    seen_order: deque[str] = deque()

    def _mark_seen(addr_key: str) -> None:
        if addr_key not in seen_tokens:
            seen_tokens.add(addr_key)
            seen_order.append(addr_key)
            if len(seen_order) > MAX_SEEN_TOKENS:
                seen_tokens.discard(seen_order.popleft())

    while True:
        if not risk_engine.can_open_position():
            log.warning("Circuit breaker ativado. Pausando entradas...")
            await asyncio.sleep(CIRCUIT_BREAKER_COOLDOWN_SEC)
            continue

        open_positions = [p for p in execution_client.positions if p["status"] == "OPEN"]
        if len(open_positions) >= settings.MAX_ACTIVE_POSITIONS:
            log.info(
                f"Slots cheios ({len(open_positions)}/{settings.MAX_ACTIVE_POSITIONS}). "
                f"Aguardando saídas..."
            )
            await asyncio.sleep(FULL_SLOTS_COOLDOWN_SEC)
            continue

        open_addresses = {p["token_address"].lower() for p in open_positions}
        open_symbols = {p["token_symbol"].upper() for p in open_positions}
        available_slots = settings.MAX_ACTIVE_POSITIONS - len(open_positions)
        log.info(f"Buscando novos tokens em múltiplas fontes... ({available_slots} slots livres)")

        try:
            candidates = await scanner.fetch_recent_pairs()
        except Exception as e:
            log.warning(f"Falha na varredura de pares: {e}")
            await asyncio.sleep(SCAN_INTERVAL_SEC)
            continue

        approved_batch: list[tuple[dict, str]] = []
        for candidate in candidates:
            token_addr = (candidate.get("token_address") or "").strip()
            addr_key = token_addr.lower()
            sym_key = (candidate.get("symbol") or "").strip().upper()

            if (
                not token_addr
                or addr_key in seen_tokens
                or addr_key in open_addresses
                or sym_key in open_symbols
            ):
                continue

            # Se a pool já passou da idade máxima (>8h), nunca mais será válida: descarta em definitivo
            if candidate.get("age_minutes", 0.0) > (settings.MAX_POOL_AGE_HOURS * 60):
                _mark_seen(addr_key)
                continue

            passed, reason = SecurityAuditor.audit_token(candidate)
            if not passed:
                # Não adiciona em seen_tokens caso seja apenas jovem (<15m) ou ainda ganhando liquidez/volume,
                # permitindo que seja comprada nos ciclos seguintes assim que atingir os gatilhos!
                continue

            approved_batch.append((candidate, reason))

        approved_batch.sort(
            key=lambda item: item[0].get("ignition_score", 0.0), reverse=True
        )

        for candidate, reason in approved_batch:
            if len(open_positions) >= settings.MAX_ACTIVE_POSITIONS:
                break

            sym_key = (candidate.get("symbol") or "").strip().upper()
            addr_key = candidate["token_address"].lower()
            if sym_key in open_symbols or addr_key in open_addresses:
                continue

            score = candidate.get("ignition_score", 0.0)
            log.info(
                f"✅ Token aprovado: {candidate['name']} ({candidate['symbol']}) | "
                f"Ignition Score: {score:.1f} - {reason}"
            )

            token_amount = risk_engine.calculate_position_size(candidate["price_usd"])
            if token_amount <= 0:
                log.warning(f"Preço inválido para {candidate['symbol']}. Entrada ignorada.")
                _mark_seen(addr_key)
                continue

            await execution_client.open_position(
                candidate=candidate,
                token_amount=token_amount,
                invested_usd=settings.POSITION_SIZE_USD,
            )

            _mark_seen(addr_key)
            new_trade = execution_client.positions[-1]
            open_positions.append(new_trade)
            open_addresses.add(addr_key)
            open_symbols.add(sym_key)

        await asyncio.sleep(SCAN_INTERVAL_SEC)


async def main():
    log.info("Iniciando Bot Assimétrico Multi-Fonte com Estratégia Estatística Ativa...")
    await db_manager.init_db()

    risk_engine = RiskManager()
    execution_client = PaperExecutionClient(risk_manager=risk_engine)
    holding_map = HoldingMap()
    stat_strategy = StatisticalStrategy(
        window=settings.STAT_WINDOW_TICKS,
        z_score_threshold=settings.STAT_ZSCORE_THRESHOLD,
        imbalance_buy_threshold=settings.STAT_IMBALANCE_BUY,
        imbalance_sell_threshold=settings.STAT_IMBALANCE_SELL,
    )

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            market_scanner(session, execution_client, risk_engine),
            position_watcher(session, execution_client, holding_map, stat_strategy),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot finalizado pelo usuário.")