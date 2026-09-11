import aiohttp
from datetime import datetime, timezone
from config.settings import settings
from src.utils.logger import log

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

    async def fetch_recent_pairs(self) -> list[dict]:
        candidates = []
        profiles = await self._get(settings.DEXSCREENER_PROFILES_URL)
        if not profiles or not isinstance(profiles, list):
            return candidates

        for item in profiles[:12]:
            token_addr = item.get("tokenAddress")
            if not token_addr:
                continue

            token_data = await self._get(f"{settings.DEXSCREENER_TOKEN_URL}/{token_addr}")
            if not token_data or "pairs" not in token_data or not token_data["pairs"]:
                continue

            best_pair = max(
                token_data["pairs"],
                key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0)
            )

            created_ms = best_pair.get("pairCreatedAt")
            if not created_ms:
                continue

            created_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
            age_minutes = (datetime.now(timezone.utc) - created_at).total_seconds() / 60.0

            txns_m5 = best_pair.get("txns", {}).get("m5", {})
            buys = int(txns_m5.get("buys", 0) or 0)
            sells = int(txns_m5.get("sells", 0) or 0)
            vol_m5 = float(best_pair.get("volume", {}).get("m5", 0.0) or 0.0)

            candidates.append({
                "chain_id": best_pair.get("chainId"),
                "pair_address": best_pair.get("pairAddress"),
                "token_address": token_addr,
                "name": best_pair.get("baseToken", {}).get("name"),
                "symbol": best_pair.get("baseToken", {}).get("symbol"),
                "price_usd": float(best_pair.get("priceUsd", 0) or 0),
                "liquidity_usd": float(best_pair.get("liquidity", {}).get("usd", 0) or 0),
                "vol_h1_usd": float(best_pair.get("volume", {}).get("h1", 0) or 0),
                "vol_m5_usd": vol_m5,
                "buys_m5": buys,
                "sells_m5": sells,
                "age_minutes": age_minutes,
            })
        return candidates