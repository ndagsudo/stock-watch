"""
日次パイプラインのオーケストレーター。

実行内容:
  1. data/watchlist_codes.json に書かれた銘柄コードについて、J-Quants APIから
     価格・決算・配当を取得し data/watchlist.db に保存する。
  2. data/watchlist.db から site/data/watchlist_snapshot.json / companies_master.json
     を生成する（フロントエンドが fetch() で読む公開情報のみのファイル）。

使い方:
    python -m src.main                 # 実データを取得してJSONを再生成
    python -m src.main --skip-fetch     # 取得せず、既存DBからJSONだけ再生成
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings
from src import data_loader, database, export


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def run_pipeline(skip_fetch: bool = False) -> dict:
    database.init_db()
    run_id = _run_id()
    result: dict = {"run_id": run_id}

    codes = export.read_watchlist_codes()
    result["codes"] = codes

    if not skip_fetch:
        if not codes:
            result["fetch"] = {"status": "no_codes", "message": "data/watchlist_codes.json に銘柄コードがありません"}
        else:
            result["fetch"] = data_loader.load_all(run_id, codes)
    else:
        result["fetch"] = {"status": "skipped_by_flag"}

    mode = "live" if settings.JQUANTS_API_KEY else "sample"
    export.write_companies_master()
    snapshot = export.write_snapshot(mode=mode)
    result["companies_in_snapshot"] = len(snapshot["companies"])
    result["mode"] = mode
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="日本株監視アシスタント 日次パイプライン")
    parser.add_argument("--skip-fetch", action="store_true", help="API呼び出しを行わず、既存DBからJSONだけ再生成する")
    args = parser.parse_args()

    result = run_pipeline(skip_fetch=args.skip_fetch)
    print(database.to_json(result))

    if result.get("fetch", {}).get("status") == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
