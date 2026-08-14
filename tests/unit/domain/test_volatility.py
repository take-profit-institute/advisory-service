from advisory_service.domain.services.volatility import annualized_volatility


def test_annualized_volatility_is_zero_for_flat_prices():
    assert annualized_volatility([100, 100, 100]) == 0.0


def test_annualized_volatility_requires_three_positive_closes():
    assert annualized_volatility([100, 101]) is None
    assert annualized_volatility([100, 0, 101]) is None


def test_annualized_volatility_returns_annualized_percentage():
    result = annualized_volatility([100, 102, 101, 105])
    assert result is not None
    assert result > 0
