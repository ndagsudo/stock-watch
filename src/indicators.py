"""
財務・株価指標の計算。

このモジュールの純粋関数群 (calc_*) は DB に一切依存せず、数値だけを受け取り
数値だけを返す。欠損値は必ず None として扱い、0 と混同しない
（例: 前期利益が None なら成長率は None であって 0% ではない）。

build_snapshot() だけが DB にアクセスし、銘柄ごとに必要な生データを集めて
上記の純粋関数へ渡す「配線」を行う。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

Number = Optional[float]


def _safe_div(numerator: Number, denominator: Number) -> Number:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def calc_per(price: Number, eps: Number) -> Number:
    if price is None or eps is None or eps <= 0:
        return None
    return price / eps


def calc_pbr(price: Number, bps: Number) -> Number:
    if price is None or bps is None or bps <= 0:
        return None
    return price / bps


def calc_roe(net_profit: Number, equity: Number) -> Number:
    return _safe_div(net_profit, equity)


def calc_operating_margin(operating_profit: Number, sales: Number) -> Number:
    return _safe_div(operating_profit, sales)


def calc_equity_ratio(equity: Number, total_assets: Number) -> Number:
    return _safe_div(equity, total_assets)


def calc_dividend_yield(annual_dividend_per_share: Number, price: Number) -> Number:
    if annual_dividend_per_share is None or price is None or price <= 0:
        return None
    return annual_dividend_per_share / price


def calc_growth_rate(current: Number, previous: Number) -> Number:
    """単純な期間成長率 (current/previous - 1)。previousが0以下なら計算不能。"""
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous) - 1.0


def calc_peg(per: Number, eps_growth_rate: Number) -> Number:
    """PEG = PER / (EPS成長率 x 100)。成長率が0以下ならPEGは意味を持たないためNone。"""
    if per is None or eps_growth_rate is None or eps_growth_rate <= 0:
        return None
    growth_pct = eps_growth_rate * 100.0
    return per / growth_pct


def calc_drawdown_from_high(price: Number, high_52w: Number) -> Number:
    """52週高値からの下落率（正の値＝高値からどれだけ下がっているか）。"""
    if price is None or high_52w is None or high_52w <= 0:
        return None
    return 1.0 - (price / high_52w)


def calc_change(price: Number, prev_close: Number) -> Number:
    if price is None or prev_close is None:
        return None
    return price - prev_close


def calc_change_pct(price: Number, prev_close: Number) -> Number:
    return calc_growth_rate(price, prev_close)


def _to_float_or_none(v) -> Number:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def build_snapshot(conn: sqlite3.Connection, code: str) -> dict:
    """
    銘柄について、DBに蓄積された最新データから監視アプリ表示用の指標一式を
    組み立てる。欠損データは None のまま返し、画面側で「取得不可」と表示する。
    """
    company = conn.execute("SELECT * FROM companies WHERE code = ?", (code,)).fetchone()

    price_rows = conn.execute(
        "SELECT * FROM prices WHERE code = ? ORDER BY date ASC", (code,)
    ).fetchall()
    fin_rows = conn.execute(
        "SELECT * FROM financials WHERE code = ? ORDER BY disclosure_date ASC", (code,)
    ).fetchall()

    snapshot: dict = {
        "code": code,
        "name": company["name"] if company else None,
        "market_name": company["market_name"] if company else None,
        "sector33_name": company["sector33_name"] if company else None,
        "data_available": {
            "price": bool(price_rows),
            "financials": bool(fin_rows),
        },
    }

    latest_price_row = price_rows[-1] if price_rows else None
    prev_price_row = price_rows[-2] if len(price_rows) >= 2 else None
    price = (latest_price_row["adj_close"] or latest_price_row["close"]) if latest_price_row else None
    prev_close = (prev_price_row["adj_close"] or prev_price_row["close"]) if prev_price_row else None

    snapshot["price"] = price
    snapshot["price_date"] = latest_price_row["date"] if latest_price_row else None
    snapshot["prev_close"] = prev_close
    snapshot["change"] = calc_change(price, prev_close)
    snapshot["change_pct"] = calc_change_pct(price, prev_close)
    snapshot["market_cap"] = latest_price_row["market_cap"] if latest_price_row else None

    closes = [r["adj_close"] or r["close"] for r in price_rows if (r["adj_close"] or r["close"]) is not None]
    dates = [r["date"] for r in price_rows]
    if dates:
        last_date = datetime.strptime(dates[-1][:10].replace("/", "-"), "%Y-%m-%d")
        one_year_ago = (last_date - timedelta(days=365)).strftime("%Y-%m-%d")
    else:
        one_year_ago = "0000-00-00"
    window_closes = [c for d, c in zip(dates, closes) if d >= one_year_ago]
    high_52w = max(window_closes, default=None)
    snapshot["high_52w"] = high_52w
    snapshot["drawdown_from_52w_high"] = calc_drawdown_from_high(price, high_52w)

    fy_rows = [r for r in fin_rows if (r["period_type"] or "").upper() in ("FY", "4Q")]
    latest_fy = fy_rows[-1] if fy_rows else None
    prev_fy = fy_rows[-2] if len(fy_rows) >= 2 else None
    latest_any = fin_rows[-1] if fin_rows else None

    def _f(row, col):
        return row[col] if row is not None else None

    snapshot["latest_disclosure_date"] = _f(latest_any, "disclosure_date")
    eps = _f(latest_fy, "eps") if latest_fy else _f(latest_any, "eps")
    bps = _f(latest_fy, "bps") if latest_fy else _f(latest_any, "bps")
    sales = _f(latest_fy, "sales")
    operating_profit = _f(latest_fy, "operating_profit")
    net_profit = _f(latest_fy, "net_profit")
    total_assets = _f(latest_fy, "total_assets")
    equity = _f(latest_fy, "equity")

    snapshot["eps"] = eps
    snapshot["bps"] = bps
    snapshot["sales"] = sales
    snapshot["operating_profit"] = operating_profit
    snapshot["net_profit"] = net_profit

    snapshot["per"] = calc_per(price, eps)
    snapshot["pbr"] = calc_pbr(price, bps)
    snapshot["roe"] = _f(latest_fy, "roe") or calc_roe(net_profit, equity)
    snapshot["operating_margin"] = calc_operating_margin(operating_profit, sales)
    snapshot["equity_ratio"] = _f(latest_fy, "equity_ratio") or calc_equity_ratio(equity, total_assets)

    snapshot["sales_growth_yoy"] = calc_growth_rate(sales, _f(prev_fy, "sales"))
    snapshot["operating_profit_growth_yoy"] = calc_growth_rate(
        operating_profit, _f(prev_fy, "operating_profit")
    )
    eps_growth_yoy = calc_growth_rate(eps, _f(prev_fy, "eps"))
    snapshot["eps_growth_yoy"] = eps_growth_yoy
    snapshot["peg"] = calc_peg(snapshot["per"], eps_growth_yoy)

    div_rows = conn.execute(
        "SELECT * FROM dividends WHERE code = ? ORDER BY pub_date DESC LIMIT 4", (code,)
    ).fetchall()
    total_div = 0.0
    has_div = False
    for r in div_rows:
        v = _to_float_or_none(r["div_rate"])
        if v is not None:
            total_div += v
            has_div = True
    snapshot["dividend_yield"] = calc_dividend_yield(total_div if has_div else None, price)

    return snapshot
