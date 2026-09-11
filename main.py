import time
import asyncio
import aiohttp
from config.settings import settings
from src.scanner.dex_scanner import DexScanner
from src.audit.holder_analyzer import SecurityAuditor
from src.strategy.holding_map import HoldingMap
from src.risk.position_sizer import RiskManager
from src.execution.paper_client import PaperExecutionClient
from src.utils.logger import log

async def position_watcher(session: aiohttp.ClientSession, execution_client: PaperExecutionClient, holding_map: HoldingMap):
    """Monitor de alta performance: batch query + liquidacao a mercado por inercia e stop."""
    while True:
        # Filtra apenas posicoes ativas
        active_trades = [p for p in execution_client.positions if p["status"] == "OPEN"]
        
        if active_trades:
            # Agrupa tokens por blockchain para Batch Request
            by_chain = {}
            for t in active_trades:
                by_chain.setdefault(t["chain_id"], []).append(t)

            for chain_id, trades in by_chain.items():
                pairs_str = ",".join([t["pair_address"] for t in trades[:25]])
                url = f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pairs_str}"

                try:
                    async with session.get(url, timeout=5) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        pairs_info = {p.get("pairAddress"): p for p in data.get("pairs", []) if p}

                        for trade in trades:
                            pair_data = pairs_info.get(trade["pair_address"])
                            if not pair_data:
                                continue

                            current_price = float(pair_data.get("priceUsd", 0) or 0)
                            current_liq = float(pair_data.get("liquidity", {}).get("usd", 0) or 0)

                            if current_price <= 0:
                                continue

                            trade["current_price"] = current_price
                            ratio = current_price / trade["entry_price"] if trade["entry_price"] > 0 else 0
                            trade_age_min = (time.time() - trade["opened_timestamp"]) / 60.0

                            # 1. Poda por Queda Excessiva (>35%) - Vende a mercado o saldo restante
                            if ratio <= (1.0 - settings.HARD_STOP_LOSS_PCT):
                                execution_client.drop_dead_position(
                                    trade=trade,
                                    reason=f"Queda abrupta de {(1 - ratio)*100:.1f}% detectada",
                                    current_price=current_price
                                )
                                continue

                            # 2. Poda por Dreno de Liquidez - Vende a mercado antes de zerar total
                            if current_liq < settings.MIN_RUNNING_LIQUIDITY_USD:
                                execution_client.drop_dead_position(
                                    trade=trade,
                                    reason=f"Liquidez drenada para ${current_liq:,.2f}",
                                    current_price=current_price
                                )
                                continue

                            # 3. Poda por Inercia / Falta de Volatilidade (Time-Stop) - Liquidacao a mercado
                            if trade_age_min >= settings.MAX_HOLD_TIME_MINUTES and ratio < (1.0 + settings.MIN_PROFIT_TO_EXTEND_TIME):
                                execution_client.drop_stagnant_position(
                                    trade=trade,
                                    age_min=trade_age_min,
                                    current_price=current_price
                                )
                                continue

                            # 4. Ativo com Momentum: Log e checagem da escadinha do Holding Map
                            pnl_pct = (ratio - 1.0) * 100
                            log.info(f"📊 [TRACKING] {trade['token_symbol']} | Preço: ${current_price:.8f} | Variação: {pnl_pct:+.1f}% ({ratio:.2f}x)")

                            for target in holding_map.targets:
                                if ratio >= target.multiplier and target.multiplier not in trade["executed_targets"]:
                                    execution_client.execute_partial_sell(
                                        trade=trade,
                                        multiplier=target.multiplier,
                                        sell_pct=target.sell_percent,
                                        current_price=current_price
                                    )

                except Exception as e:
                    log.warning(f"Falha na checagem em lote ({chain_id}): {e}")

        await asyncio.sleep(settings.WATCHER_INTERVAL_SEC)

async def market_scanner(session: aiohttp.ClientSession, execution_client: PaperExecutionClient, risk_engine: RiskManager):
    """Varredura continua de novos ativos respeitando a lotacao de slots."""
    scanner = DexScanner(session)
    seen_tokens = set()

    while True:
        if not risk_engine.can_open_position():
            log.warning("Circuit breaker ativado. Pausando entradas...")
            await asyncio.sleep(60)
            continue

        active_count = len([p for p in execution_client.positions if p["status"] == "OPEN"])
        
        # Trava de ocupacao de slots
        if active_count >= settings.MAX_ACTIVE_POSITIONS:
            log.info(f"Slots cheios ({active_count}/{settings.MAX_ACTIVE_POSITIONS}). Aguardando rotatividade...")
            await asyncio.sleep(6)
            continue

        available_slots = settings.MAX_ACTIVE_POSITIONS - active_count
        log.info(f"Buscando novos tokens... ({available_slots} slots livres)")
        candidates = await scanner.fetch_recent_pairs()

        for candidate in candidates:
            # Para de avaliar candidatos se encher a carteira durante o loop
            if len([p for p in execution_client.positions if p["status"] == "OPEN"]) >= settings.MAX_ACTIVE_POSITIONS:
                break

            token_addr = candidate["token_address"]
            if token_addr in seen_tokens:
                continue

            seen_tokens.add(token_addr)
            passed, reason = SecurityAuditor.audit_token(candidate)

            if passed:
                log.info(f"✅ Token aprovado: {candidate['name']} ({candidate['symbol']}) - {reason}")
                
                token_amount = risk_engine.calculate_position_size(candidate["price_usd"])
                execution_client.open_position(
                    candidate=candidate,
                    token_amount=token_amount,
                    invested_usd=settings.POSITION_SIZE_USD
                )

        await asyncio.sleep(12)

async def main():
    log.info("Iniciando Bot Assimétrico com Monitor em Lote e Rotação Dinâmica...")
    
    risk_engine = RiskManager()
    execution_client = PaperExecutionClient()
    holding_map = HoldingMap()

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            market_scanner(session, execution_client, risk_engine),
            position_watcher(session, execution_client, holding_map)
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot finalizado pelo usuário.")