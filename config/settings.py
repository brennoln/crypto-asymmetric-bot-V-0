from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PAPER_TRADING: bool = True
    POSITION_SIZE_USD: float = 15.0
    MAX_DAILY_LOSS_USD: float = 100.0

    # Capacidade do Portfólio e Rotação
    MAX_ACTIVE_POSITIONS: int = 10          # Limite de moedas simultâneas
    MAX_HOLD_TIME_MINUTES: float = 6.0      # Tempo máximo sem tração antes de podar
    MIN_PROFIT_TO_EXTEND_TIME: float = 0.20 # +20% de lucro concede sobrevida à moeda
    WATCHER_INTERVAL_SEC: float = 4.0

    # Critérios de Entrada (Relaxados para Maior Escaneamento)
    MIN_LIQUIDITY_USD: float = 8_000.0
    MAX_LIQUIDITY_USD: float = 120_000.0
    MIN_POOL_AGE_MINUTES: float = 15.0
    MAX_POOL_AGE_HOURS: float = 8.0
    MIN_VOLUME_M5_USD: float = 1_000.0
    MIN_BUYS_M5: int = 8
    MIN_BUY_SELL_RATIO: float = 1.35

    # Travas de Invalidação Rápida (Anti-Ruína)
    HARD_STOP_LOSS_PCT: float = 0.35        # Drop > 35% descarta imediatamente
    MIN_RUNNING_LIQUIDITY_USD: float = 6_000.0

    # Endpoints
    DEXSCREENER_PROFILES_URL: str = "https://api.dexscreener.com/token-profiles/latest/v1"
    DEXSCREENER_TOKEN_URL: str = "https://api.dexscreener.com/latest/dex/tokens"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()