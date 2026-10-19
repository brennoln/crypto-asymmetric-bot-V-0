import asyncio
from datetime import datetime, timezone

import aiohttp

from config.settings import settings
from src.utils.logger import log

TOKEN_BATCH_SIZE = 30
MAX_CANDIDATES_PER_SCAN = 60


class DexScanner:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _get(self, url: str) -> dict | list | None:
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            log.warning(f"Erro na requisição ({url}): {e}")
        return None

    @staticmethod
    def compute_ignition_score(candidate: dict) -> float:
        """Calcula o score quantitativo de ignição para ranquear as melhores moedas."""
        liq = max(float(candidate.get("liquidity_usd", 0.0) or 0.0), 1.0)
        vol_m5 = float(candidate.get("vol_m5_usd", 0.0) or 0.0)
        vol_h1 = max(float(candidate.get("vol_h1_usd", 0.0) or 0.0), vol_m5, 1.0)
        buys = int(candidate.get("buys_m5", 0) or 0)
        sells = int(candidate.get("sells_m5", 0) or 0)

        turnover_m5 = min(vol_m5 / liq, 3.0)
        baseline_m5 = max(vol_h1 / 12.0, 1.0)
        vol_acceleration = min(vol_m5 / baseline_m5, 5.0)

        total_txns = buys + sells
        imbalance = (buys - sells) / total_txns if total_txns > 0 else 0.0

        score = (
            (turnover_m5 * 40.0)
            + (vol_acceleration * 25.0)
            + (max(imbalance, 0.0) * 25.0)
            + (min(buys, 100) * 0.10)
        )
        return round(score, 2)

    async def _discover_token_addresses(self) -> list[str]:
        """Coleta endereços de múltiplas fontes do DexScreener em paralelo."""
        discovery_urls = [
            settings.DEXSCREENER_PROFILES_URL,
            settings.DEXSCREENER_BOOSTS_LATEST_URL,
            settings.DEXSCREENER_BOOSTS_TOP_URL,
        ]
        responses = await asyncio.gather(
            *(self._get(url) for url in discovery_urls),
            return_exceptions=True,
        )

        unique_addresses: list[str] = []
        seen: set[str] = set()

        for payload in responses:
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                token_addr = (item.get("tokenAddress") or "").strip()
                addr_key = token_addr.lower()
                if token_addr and addr_key not in seen:
                    seen.add(addr_key)
                    unique_addresses.append(token_addr)
                    if len(unique_addresses) >= MAX_CANDIDATES_PER_SCAN:
                        return unique_addresses

        return unique_addresses

    @staticmethod
    def _extract_candidate(token_addr: str, pairs: list[dict], now_utc: datetime) -> dict | None:
        valid_pairs = [p for p in pairs if isinstance(p, dict) and p.get("pairCreatedAt")]
        if not valid_pairs:
            return None

        best_pair = max(
            valid_pairs,
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
        )

        created_ms = best_pair.get("pairCreatedAt")
        if not created_ms:
            return None

        created_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        age_minutes = (now_utc - created_at).total_seconds() / 60.0

        txns_m5 = best_pair.get("txns", {}).get("m5", {}) or {}
        buys = int(txns_m5.get("buys", 0) or 0)
        sells = int(txns_m5.get("sells", 0) or 0)
        vol_m5 = float(best_pair.get("volume", {}).get("m5", 0.0) or 0.0)
        vol_h1 = float(best_pair.get("volume", {}).get("h1", 0.0) or 0.0)

        raw_symbol = (best_pair.get("baseToken", {}).get("symbol") or "UNKNOWN").strip()

        candidate = {
            "chain_id": best_pair.get("chainId"),
            "pair_address": best_pair.get("pairAddress"),
            "token_address": token_addr,
            "name": (best_pair.get("baseToken", {}).get("name") or "Unknown").strip(),
            "symbol": raw_symbol,
            "price_usd": float(best_pair.get("priceUsd", 0) or 0),
            "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
            "vol_h1_usd": vol_h1,
            "vol_m5_usd": vol_m5,
            "buys_m5": buys,
            "sells_m5": sells,
            "age_minutes": age_minutes,
        }
        candidate["ignition_score"] = DexScanner.compute_ignition_score(candidate)
        return candidate

    async def fetch_recent_pairs(self) -> list[dict]:
        """Descobre tokens em múltiplas fontes, consulta pares em lote e deduplica clones."""
        token_addresses = await self._discover_token_addresses()
        if not token_addresses:
            return []

        batches = [
            token_addresses[i : i + TOKEN_BATCH_SIZE]
            for i in range(0, len(token_addresses), TOKEN_BATCH_SIZE)
        ]
        batch_urls = [
            f"{settings.DEXSCREENER_TOKEN_URL}/{','.join(batch)}" for batch in batches
        ]

        batch_responses = await asyncio.gather(
            *(self._get(url) for url in batch_urls),
            return_exceptions=True,
        )

        pairs_by_token: dict[str, list[dict]] = {}
        for data in batch_responses:
            if not isinstance(data, dict):
                continue
            for pair in data.get("pairs") or []:
                if not isinstance(pair, dict):
                    continue
                base_addr = (pair.get("baseToken") or {}).get("address")
                if base_addr:
                    pairs_by_token.setdefault(base_addr.lower(), []).append(pair)

        now_utc = datetime.now(timezone.utc)
        raw_candidates: list[dict] = []

        for token_addr in token_addresses:
            token_pairs = pairs_by_token.get(token_addr.lower())
            if not token_pairs:
                continue
            candidate = self._extract_candidate(token_addr, token_pairs, now_utc)
            if candidate is not None:
                raw_candidates.append(candidate)

        # Ordena pelo maior Ignition Score primeiro
        raw_candidates.sort(key=lambda c: c.get("ignition_score", 0.0), reverse=True)

        # Deduplica clones com o mesmo ticker (symbol) no mesmo ciclo, mantendo o de maior Score
        deduped_candidates: list[dict] = []
        seen_symbols: set[str] = set()
        for cand in raw_candidates:
            sym_key = cand["symbol"].upper()
            if sym_key in seen_symbols:
                continue
            seen_symbols.add(sym_key)
            deduped_candidates.append(cand)

        return deduped_candidates