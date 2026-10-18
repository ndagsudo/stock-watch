"""
SQLite のデータから、フロントエンド（PWA）が fetch() で読み込む
静的JSONファイル（site/data/watchlist_snapshot.json）を生成する。

このJSONには「公開情報（株価・財務指標）」のみを含み、購入検討価格・メモ・
アラート条件などの個人データは一切含めない（個人データはブラウザの
localStorageのみに保存される）。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings
from src import database, indicators, screener


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SOURCE_INFO = {
    "provider": "J-Quants API (JPX総研)",
    "provider_url": "https://jpx-jquants.com/",
    "price_data": {
        "kind": "日次株価（四本値・調整後終値・売買高・時価総額）",
        "update_frequency": "平日1日1回（取得元の確定タイミングに依存。当日分が翌営業日になることがある）",
        "terms": "J-Quants利用規約に基づく。契約プランにより取得可能な範囲・レート制限が異なる",
        "free_tier_limit": "Freeプラン: 5リクエスト/分",
    },
    "financial_data": {
        "kind": "決算情報（売上高・営業利益・EPS・BPS等）・配当情報",
        "update_frequency": "各企業の決算発表のタイミングに依存（四半期ごと）",
        "terms": "J-Quants利用規約に基づく。契約プランにより取得可能な範囲・レート制限が異なる",
        "free_tier_limit": "Freeプラン: 5リクエスト/分",
    },
}


def build_snapshot_json(conn: sqlite3.Connection, codes: list[str], mode: str = "live") -> dict:
    companies: dict = {}
    snapshots_for_screening = []

    for code in codes:
        snap = indicators.build_snapshot(conn, code)
        snap["is_sample"] = False
        snap["updated_at"] = _now_iso()
        snapshots_for_screening.append(snap)
        companies[code] = snap

    ranked = screener.rank(snapshots_for_screening)
    screening_by_code = {r["code"]: r for r in ranked}
    for code, snap in companies.items():
        snap["screening"] = screening_by_code.get(code)

    return {
        "generated_at": _now_iso(),
        "mode": mode,
        "source_info": SOURCE_INFO,
        "companies": companies,
    }


def write_snapshot(output_path: Optional[Path] = None, mode: str = "live") -> dict:
    output_path = output_path or (settings.SITE_DATA_DIR / "watchlist_snapshot.json")
    codes = read_watchlist_codes()
    with database.connect() as conn:
        payload = build_snapshot_json(conn, codes, mode=mode)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(database.to_json(payload), encoding="utf-8")
    return payload


def write_companies_master(output_path: Optional[Path] = None) -> int:
    """検索・登録用に、全上場銘柄のコード・企業名・市場区分を書き出す
    （個人データなし。登録前の銘柄コード検索に使う）。"""
    output_path = output_path or (settings.SITE_DATA_DIR / "companies_master.json")
    with database.connect() as conn:
        rows = conn.execute("SELECT code, name, market_name, sector33_name FROM companies").fetchall()
    data = {r["code"]: dict(r) for r in rows}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(database.to_json(data), encoding="utf-8")
    return len(data)


def read_watchlist_codes() -> list[str]:
    path = settings.WATCHLIST_CODES_PATH
    if not path.exists():
        return []
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    if isinstance(data, dict):
        data = data.get("codes", [])
    return [str(c).strip() for c in data if str(c).strip()]
