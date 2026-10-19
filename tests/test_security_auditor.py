from config.settings import settings
from src.audit.holder_analyzer import SecurityAuditor


def _candidate(**overrides) -> dict:
    """Candidato que passa em todos os filtros; overrides forçam cada rejeição."""
    candidate = {
        "liquidity_usd": settings.MIN_LIQUIDITY_USD * 2,
        "age_minutes": settings.MIN_POOL_AGE_MINUTES * 2,
        "vol_m5_usd": settings.MIN_VOLUME_M5_USD * 2,
        "buys_m5": settings.MIN_BUYS_M5 * 2,
        "sells_m5": settings.MIN_BUYS_M5,
    }
    candidate.update(overrides)
    return candidate


def test_approves_a_candidate_that_clears_every_filter():
    passed, reason = SecurityAuditor.audit_token(_candidate())

    assert passed is True
    assert reason


def test_rejects_liquidity_below_the_lower_bound():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(liquidity_usd=settings.MIN_LIQUIDITY_USD - 1)
    )

    assert passed is False
    assert "Liquidez" in reason


def test_rejects_liquidity_above_the_upper_bound():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(liquidity_usd=settings.MAX_LIQUIDITY_USD + 1)
    )

    assert passed is False
    assert "excessiva" in reason


def test_rejects_a_pool_younger_than_the_sniper_window():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(age_minutes=settings.MIN_POOL_AGE_MINUTES - 1)
    )

    assert passed is False
    assert "sniper" in reason


def test_rejects_a_pool_outside_the_age_window():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(age_minutes=settings.MAX_POOL_AGE_HOURS * 60 + 1)
    )

    assert passed is False
    assert "fora da janela" in reason


def test_rejects_a_candidate_without_volume_ignition():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(vol_m5_usd=settings.MIN_VOLUME_M5_USD - 1)
    )

    assert passed is False
    assert "volume" in reason


def test_rejects_a_candidate_with_too_few_buys():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(buys_m5=settings.MIN_BUYS_M5 - 1)
    )

    assert passed is False
    assert "compras" in reason


def test_rejects_heavy_sell_pressure():
    passed, reason = SecurityAuditor.audit_token(
        _candidate(buys_m5=settings.MIN_BUYS_M5 * 2, sells_m5=settings.MIN_BUYS_M5 * 10)
    )

    assert passed is False
    assert "venda" in reason


def test_avoids_division_by_zero_when_there_are_no_sells():
    passed, _ = SecurityAuditor.audit_token(
        _candidate(buys_m5=settings.MIN_BUYS_M5 + 1, sells_m5=0)
    )

    assert passed is True


def test_rejects_with_a_reason_string_for_every_failure():
    _, reason = SecurityAuditor.audit_token(_candidate(liquidity_usd=0.0))

    assert isinstance(reason, str) and reason
