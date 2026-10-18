"""
J-Quants API から取得した生データを SQLite に取り込むオーケストレーション層。

方針（stock-screener プロジェクトと同じ方針を踏襲）:
  - 存在しないデータを推測して埋めない（0 とデータなしを混同しない）。
  - 1銘柄の取得失敗がパイプライン全体を止めないよう、銘柄ごとに例外を
    握りつぶし errors テーブルに記録して処理を継続する。
  - APIコール数を抑えるため、銘柄マスタ（全銘柄、検索用）は1回のバルク呼び出しで
    取得し、価格履歴・決算・配当は「監視登録されている銘柄コードだけ」を対象に
    1銘柄ずつ取得する（J-Quants V2は銘柄×期間を指定すれば1コールで履歴全体を
    返すため、1銘柄あたり3コールで済む）。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings
from src import database
from src.jquants_client import JQuantsClient, JQuantsAPIError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value) -> Optional[float]:
    """J-Quantsは未確定・非開示の数値項目を null ではなく文字列 "-" や空文字で
    返すことがある。そのまま float 演算に渡すと例外になるため、ここで
    一括して数値かNoneに正規化する。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in ("", "-", "－", "―"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_company_master(client: JQuantsClient, conn: sqlite3.Connection, run_id: str) -> int:
    """全銘柄マスタ（コード・企業名・市場区分）を取得する。検索・登録用に使う。
    1回のバルク呼び出しのみで、価格・決算は含まない。"""
    try:
        records = client.get_listed_info()
    except JQuantsAPIError as exc:
        database.log_error(conn, run_id, "load_company_master", str(exc))
        return 0

    rows = []
    for r in records:
        code = r.get("Code")
        if not code:
            continue
        rows.append(
            {
                "code": code,
                "name": r.get("CoName", ""),
                "name_en": r.get("CoNameEn"),
                "sector17_name": r.get("S17Nm"),
                "sector33_name": r.get("S33Nm"),
                "market_name": r.get("MktNm"),
                "last_updated_date": _now_iso(),
            }
        )
    database.upsert(conn, "companies", rows, ["code"])
    return len(rows)


def _quotes_to_rows(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        code = r.get("Code")
        date = r.get("Date")
        if not code or not date:
            continue
        mkt_cap = _to_float(r.get("MktCap"))
        rows.append(
            {
                "code": code,
                "date": date,
                "open": _to_float(r.get("O")),
                "high": _to_float(r.get("H")),
                "low": _to_float(r.get("L")),
                "close": _to_float(r.get("C")),
                "adj_close": _to_float(r.get("AdjC")),
                "volume": _to_float(r.get("Vo")),
                # J-QuantsのMktCapは百万円単位で返るため円単位に変換する
                "market_cap": (mkt_cap * 1_000_000) if mkt_cap is not None else None,
            }
        )
    return rows


def load_price_history(
    client: JQuantsClient, conn: sqlite3.Connection, run_id: str, code: str, days: int = None
) -> int:
    days = days or settings.PRICE_HISTORY_DAYS
    to_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    try:
        records = client.get_daily_quotes(code=code, from_date=from_date, to_date=to_date)
    except JQuantsAPIError as exc:
        database.log_error(conn, run_id, "load_price_history", str(exc), code=code)
        return 0
    rows = _quotes_to_rows(records)
    database.upsert(conn, "prices", rows, ["code", "date"])
    return len(rows)


def load_financials(client: JQuantsClient, conn: sqlite3.Connection, run_id: str, code: str) -> int:
    try:
        records = client.get_financial_summary(code=code)
    except JQuantsAPIError as exc:
        database.log_error(conn, run_id, "load_financials", str(exc), code=code)
        return 0
    rows = []
    for r in records:
        disc_date = r.get("DiscDate")
        if not disc_date:
            continue
        rows.append(
            {
                "code": code,
                "disclosure_date": disc_date,
                "period_type": r.get("CurPerType") or "NA",
                "period_end": r.get("CurPerEn"),
                "sales": _to_float(r.get("Sales")),
                "operating_profit": _to_float(r.get("OP")),
                "ordinary_profit": _to_float(r.get("OdP")),
                "net_profit": _to_float(r.get("NP")),
                "eps": _to_float(r.get("EPS")),
                "total_assets": _to_float(r.get("TA")),
                "equity": _to_float(r.get("Eq")),
                "equity_ratio": _to_float(r.get("EqAR")),
                "bps": _to_float(r.get("BPS")),
                "roe": _to_float(r.get("ROE")),
                "forecast_sales": _to_float(r.get("FSales")),
                "forecast_operating_profit": _to_float(r.get("FOP")),
                "forecast_net_profit": _to_float(r.get("FNP")),
                "forecast_eps": _to_float(r.get("FEPS")),
                "shares_outstanding": _to_float(r.get("ShOutFY")),
            }
        )
    database.upsert(conn, "financials", rows, ["code", "disclosure_date", "period_type"])
    return len(rows)


def load_dividends(client: JQuantsClient, conn: sqlite3.Connection, run_id: str, code: str) -> int:
    try:
        records = client.get_dividends(code=code)
    except JQuantsAPIError as exc:
        database.log_error(conn, run_id, "load_dividends", str(exc), code=code)
        return 0
    rows = []
    for r in records:
        ref_no = r.get("RefNo")
        if not ref_no:
            continue
        rows.append(
            {
                "code": code,
                "ref_no": ref_no,
                "pub_date": r.get("PubDate"),
                "div_rate": r.get("DivRate"),
            }
        )
    database.upsert(conn, "dividends", rows, ["code", "ref_no"])
    return len(rows)


def load_all(run_id: str, codes: list[str], api_key: Optional[str] = None) -> dict:
    """監視登録されている銘柄コードについてデータ取得パイプラインを実行する。
    戻り値は取得件数・成功/失敗のサマリ（自動更新の成否表示に使う）。"""
    started_at = _now_iso()
    client = JQuantsClient(api_key=api_key or settings.JQUANTS_API_KEY)
    summary = {
        "configured": client.is_configured,
        "codes_requested": len(codes),
        "codes_succeeded": 0,
        "errors": [],
    }
    if not client.is_configured:
        summary["status"] = "skipped_no_api_key"
        return summary

    with database.connect() as conn:
        summary["company_master"] = load_company_master(client, conn, run_id)

        for code in codes:
            try:
                p = load_price_history(client, conn, run_id, code)
                f = load_financials(client, conn, run_id, code)
                d = load_dividends(client, conn, run_id, code)
                if p or f:
                    summary["codes_succeeded"] += 1
            except Exception as exc:  # noqa: BLE001 — 1銘柄の予期せぬ例外で全体を止めない
                database.log_error(conn, run_id, "load_all", str(exc), code=code)

        error_rows = conn.execute(
            "SELECT stage, code, message FROM errors WHERE run_id = ?", (run_id,)
        ).fetchall()
        summary["errors"] = [dict(r) for r in error_rows]

        finished_at = _now_iso()
        status = "ok" if summary["codes_succeeded"] > 0 or not codes else "no_codes"
        if summary["errors"] and summary["codes_succeeded"] == 0 and codes:
            status = "failed"
        conn.execute(
            """INSERT OR REPLACE INTO updates
               (run_id, started_at, finished_at, status, codes_requested, codes_succeeded, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                started_at,
                finished_at,
                status,
                len(codes),
                summary["codes_succeeded"],
                database.to_json({"error_count": len(summary["errors"])}),
            ),
        )
        summary["status"] = status

    return summary
