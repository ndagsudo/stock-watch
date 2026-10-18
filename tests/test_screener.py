import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import screener


def _snapshot(**overrides):
    base = {
        "code": "0000",
        "name": "テスト株式会社",
        "price": 1000,
        "per": 10.0,
        "pbr": 0.9,
        "roe": 0.12,
        "peg": 0.8,
        "sales_growth_yoy": 0.10,
        "operating_profit_growth_yoy": 0.12,
        "operating_margin": 0.10,
        "equity_ratio": 0.4,
        "drawdown_from_52w_high": 0.2,
        "latest_disclosure_date": "2026-08-01",
        "price_date": "2026-10-01",
    }
    base.update(overrides)
    return base


def test_evaluate_undervalued_growth_stock_gets_positive_reasons():
    snap = _snapshot()
    result = screener.evaluate(snap)
    assert result["data_sufficient"] is True
    assert result["score"] > 0
    assert any("PEG" in r for r in result["notable_reasons"])


def test_evaluate_missing_required_fields_is_data_insufficient():
    snap = _snapshot(per=None, sales_growth_yoy=None)
    result = screener.evaluate(snap)
    assert result["data_sufficient"] is False
    assert "per" in result["missing_fields"]
    assert result["score"] is None


def test_evaluate_declining_company_shows_concerns():
    snap = _snapshot(sales_growth_yoy=-0.15, operating_profit_growth_yoy=-0.2, peg=None, per=25.0)
    result = screener.evaluate(snap)
    assert any("減少" in c for c in result["concerns"])


def test_rank_puts_insufficient_data_after_sufficient():
    good = _snapshot(code="1111")
    bad = _snapshot(code="2222", per=None, sales_growth_yoy=None, operating_profit_growth_yoy=None)
    ranked = screener.rank([bad, good])
    assert ranked[0]["code"] == "1111"
    assert ranked[0]["data_sufficient"] is True
    assert ranked[-1]["code"] == "2222"
    assert ranked[-1]["data_sufficient"] is False


def test_rank_sorts_by_score_descending():
    high = _snapshot(code="1111", peg=0.5, sales_growth_yoy=0.3, operating_profit_growth_yoy=0.3, roe=0.2)
    low = _snapshot(code="2222", peg=None, per=28.0, sales_growth_yoy=0.08, operating_profit_growth_yoy=0.08)
    ranked = screener.rank([low, high])
    assert ranked[0]["code"] == "1111"
    assert ranked[0]["score"] >= ranked[1]["score"]
