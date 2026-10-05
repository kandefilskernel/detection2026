"""Relances du scoring : échecs transitoires retentés (le scoring est idempotent), autres échecs non."""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "integration-layer")]

from app import main  # noqa: E402
from shared.schemas.unified_transaction import UnifiedTransaction  # noqa: E402

TX = UnifiedTransaction(transaction_id="T1", timestamp=datetime(2025, 11, 2, 10, 0), user_id="U1", channel="MOBILE_MONEY",
                        operator="VODACOM", tx_type="P2P_SEND", access_channel="APP", amount=5.0, currency="USD",
                        amount_usd=5.0, balance_before_usd=50.0, device_id="D1", location_province="Kinshasa")


def run_with(responses):
    calls = []

    def handler(request):
        calls.append(1)
        r = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r, json={"ok": True})

    async def go():
        main.state["http"] = httpx.AsyncClient(base_url="http://scoring", transport=httpx.MockTransport(handler))
        try:
            return await main.post_with_retries(TX)
        finally:
            await main.state["http"].aclose()
    try:
        return asyncio.run(go()).status_code, len(calls)
    except httpx.HTTPError as e:
        return type(e).__name__, len(calls)


def test_transient_503_is_retried_then_succeeds():
    assert run_with([503, 503, 200]) == (200, 3)


def test_network_error_is_retried():
    assert run_with([httpx.ConnectError("refus"), 200]) == (200, 2)


def test_retries_are_bounded_then_the_error_reaches_the_fallback_policy():
    status, calls = run_with([503])
    assert status == "HTTPStatusError" and calls == main.settings.SCORING_RETRIES + 1


def test_client_errors_and_internal_errors_are_not_retried():
    assert run_with([422]) == ("HTTPStatusError", 1)
    assert run_with([500]) == ("HTTPStatusError", 1)         # erreur interne : pas de relance aveugle
