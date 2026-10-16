from app.partners import BURST_FACTOR, RateLimiter


def test_bucket_allows_a_burst_then_refills_at_the_configured_rate():
    lim = RateLimiter()
    rate = 2.0
    burst = int(rate * BURST_FACTOR)
    assert all(lim.allow("rawbank", rate, now=100.0)[0] for _ in range(burst))
    ok, wait = lim.allow("rawbank", rate, now=100.0)
    assert not ok and 0 < wait <= 1 / rate
    assert lim.allow("rawbank", rate, now=100.0 + 1 / rate)[0]        # un jeton regagné


def test_institutions_have_independent_quotas():
    lim = RateLimiter()
    for _ in range(10):
        lim.allow("vodacom", 1.0, now=0.0)
    assert not lim.allow("vodacom", 1.0, now=0.0)[0]
    assert lim.allow("airtel", 1.0, now=0.0)[0]
