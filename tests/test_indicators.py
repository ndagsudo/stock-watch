import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import indicators


def test_calc_per_normal():
    assert indicators.calc_per(1000, 100) == 10.0


def test_calc_per_missing_eps_is_none():
    assert indicators.calc_per(1000, None) is None


def test_calc_per_negative_eps_is_none():
    # 赤字企業のPERは意味を持たないためNone（0や負値を返さない）
    assert indicators.calc_per(1000, -50) is None


def test_calc_pbr_missing_bps_is_none():
    assert indicators.calc_pbr(1000, None) is None


def test_calc_roe_zero_equity_is_none():
    # ゼロ除算はエラーではなくNoneとして扱う
    assert indicators.calc_roe(100, 0) is None


def test_calc_dividend_yield_missing_is_none():
    assert indicators.calc_dividend_yield(None, 1000) is None
    assert indicators.calc_dividend_yield(20, None) is None


def test_calc_growth_rate_normal():
    assert round(indicators.calc_growth_rate(110, 100), 4) == 0.1


def test_calc_growth_rate_missing_previous_is_none():
    assert indicators.calc_growth_rate(110, None) is None


def test_calc_growth_rate_negative_previous_is_none():
    assert indicators.calc_growth_rate(110, -10) is None


def test_calc_peg_requires_positive_growth():
    # PER20倍、EPS成長率10%ならPEG=2.0
    assert indicators.calc_peg(20, 0.10) == 2.0


def test_calc_peg_negative_growth_is_none():
    assert indicators.calc_peg(20, -0.05) is None


def test_calc_drawdown_from_high():
    assert round(indicators.calc_drawdown_from_high(80, 100), 4) == 0.2


def test_calc_drawdown_missing_high_is_none():
    assert indicators.calc_drawdown_from_high(80, None) is None


def test_calc_change_and_pct():
    assert indicators.calc_change(110, 100) == 10
    assert round(indicators.calc_change_pct(110, 100), 4) == 0.1


def test_calc_change_missing_is_none():
    assert indicators.calc_change(None, 100) is None
    assert indicators.calc_change_pct(110, None) is None


def test_build_snapshot_missing_data_returns_none_not_zero(tmp_path):
    """銘柄が一度もDBに存在しない場合、0ではなくNone/取得不可として返ること。"""
    import sqlite3
    from src import database

    db_path = tmp_path / "test.db"
    conn = database.get_connection(db_path)
    conn.executescript(database.SCHEMA)
    conn.commit()

    snap = indicators.build_snapshot(conn, "9999")
    assert snap["price"] is None
    assert snap["per"] is None
    assert snap["sales_growth_yoy"] is None
    assert snap["data_available"]["price"] is False
    assert snap["data_available"]["financials"] is False
    conn.close()
