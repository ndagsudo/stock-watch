"""
SQLite アクセス層。

常駐サーバーがないため、data/watchlist.db は Git リポジトリにコミットされ、
GitHub Actions の実行のたびに更新・コミットされる。これにより、watchlist.db
自体には銘柄コード・価格・財務データ（公開情報）のみを保持し、購入検討価格・
メモ・アラート条件などの「個人の投資記録」は一切保存しない
（それらはブラウザのlocalStorageのみに保存される設計）。
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings

SCHEMA = """
-- 銘柄マスタ（コード・企業名・市場区分など公開情報のみ）
CREATE TABLE IF NOT EXISTS companies (
    code TEXT PRIMARY KEY,
    name TEXT,
    name_en TEXT,
    sector17_name TEXT,
    sector33_name TEXT,
    market_name TEXT,
    last_updated_date TEXT
);

-- 日次株価（四本値・調整後・時価総額）
CREATE TABLE IF NOT EXISTS prices (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    adj_close REAL,
    volume REAL,
    market_cap REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_code_date ON prices(code, date);

-- 決算情報（開示単位で1行、履歴として積み上げる）
CREATE TABLE IF NOT EXISTS financials (
    code TEXT NOT NULL,
    disclosure_date TEXT NOT NULL,
    period_type TEXT,
    period_end TEXT,
    sales REAL,
    operating_profit REAL,
    ordinary_profit REAL,
    net_profit REAL,
    eps REAL,
    total_assets REAL,
    equity REAL,
    equity_ratio REAL,
    bps REAL,
    roe REAL,
    forecast_sales REAL,
    forecast_operating_profit REAL,
    forecast_net_profit REAL,
    forecast_eps REAL,
    shares_outstanding REAL,
    PRIMARY KEY (code, disclosure_date, period_type)
);
CREATE INDEX IF NOT EXISTS idx_financials_code ON financials(code, disclosure_date);

-- 配当情報
CREATE TABLE IF NOT EXISTS dividends (
    code TEXT NOT NULL,
    ref_no TEXT NOT NULL,
    pub_date TEXT,
    div_rate TEXT,
    PRIMARY KEY (code, ref_no)
);

-- 実行ログ（成功/失敗が分かるように残す。削除しない）
CREATE TABLE IF NOT EXISTS updates (
    run_id TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    codes_requested INTEGER,
    codes_succeeded INTEGER,
    notes TEXT
);

-- エラーログ（非致命的エラーを記録し、処理は止めない。削除しない）
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    stage TEXT,
    code TEXT,
    message TEXT,
    created_at TEXT
);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or settings.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: Optional[Path] = None):
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert(conn: sqlite3.Connection, table: str, rows: Iterable[dict], key_columns: list[str]) -> int:
    """辞書のリストを指定テーブルに INSERT OR REPLACE する汎用ヘルパー。"""
    rows = list(rows)
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(columns))
    col_str = ",".join(columns)
    sql = f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})"
    values = [tuple(row.get(c) for c in columns) for row in rows]
    conn.executemany(sql, values)
    return len(rows)


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def log_error(conn: sqlite3.Connection, run_id: str, stage: str, message: str, code: Optional[str] = None) -> None:
    from datetime import datetime, timezone

    conn.execute(
        "INSERT INTO errors (run_id, stage, code, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (run_id, stage, code, str(message)[:2000], datetime.now(timezone.utc).isoformat()),
    )
