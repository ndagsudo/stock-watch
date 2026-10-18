"""
ローカル動作確認用のサンプルデータを生成する。

実データ（J-Quants APIから取得したもの）とは明確に区別するため、
ここで生成するデータはすべて "is_sample": true を持ち、画面側は
これを見て「サンプルデータ」バッジを表示する。

使い方:
    python scripts/seed_sample_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings
from src import screener

NOW = datetime.now(timezone.utc).isoformat()

# 実在する企業コード・企業名を「表示イメージが分かりやすいサンプル」として使うが、
# 数値（株価・PERなど）はすべて説明用のダミー値であり、実際の値ではない。
SAMPLE_COMPANIES = {
    "7203": {
        "name": "トヨタ自動車（サンプル）",
        "market_name": "プライム",
        "sector33_name": "輸送用機器",
        "price": 2980.0,
        "prev_close": 2950.0,
        "per": 10.8,
        "pbr": 1.2,
        "roe": 0.112,
        "sales_growth_yoy": 0.06,
        "operating_profit_growth_yoy": 0.09,
        "operating_margin": 0.095,
        "equity_ratio": 0.38,
        "dividend_yield": 0.028,
        "high_52w": 3200.0,
        "latest_disclosure_date": "2026-08-05",
        "price_date": "2026-10-17",
    },
    "6758": {
        "name": "ソニーグループ（サンプル）",
        "market_name": "プライム",
        "sector33_name": "電気機器",
        "price": 3650.0,
        "prev_close": 3700.0,
        "per": 18.2,
        "pbr": 2.5,
        "roe": 0.137,
        "sales_growth_yoy": 0.11,
        "operating_profit_growth_yoy": 0.15,
        "operating_margin": 0.12,
        "equity_ratio": 0.42,
        "dividend_yield": 0.006,
        "high_52w": 3900.0,
        "latest_disclosure_date": "2026-08-08",
        "price_date": "2026-10-17",
    },
    "9984": {
        "name": "ソフトバンクグループ（サンプル）",
        "market_name": "プライム",
        "sector33_name": "情報・通信業",
        # 財務データが未取得・不明なケースのサンプル（取得不可の表示確認用）
        "price": 10250.0,
        "prev_close": 10400.0,
        "per": None,
        "pbr": None,
        "roe": None,
        "sales_growth_yoy": None,
        "operating_profit_growth_yoy": None,
        "operating_margin": None,
        "equity_ratio": None,
        "dividend_yield": 0.005,
        "high_52w": 12800.0,
        "latest_disclosure_date": None,
        "price_date": "2026-10-17",
    },
}


def _calc_change(price, prev):
    if price is None or prev is None:
        return None, None
    change = price - prev
    pct = change / prev if prev else None
    return change, pct


def build_sample_payload() -> dict:
    companies = {}
    snapshots_for_screening = []
    for code, base in SAMPLE_COMPANIES.items():
        snap = dict(base)
        snap["code"] = code
        change, change_pct = _calc_change(snap["price"], snap["prev_close"])
        snap["change"] = change
        snap["change_pct"] = change_pct
        snap["drawdown_from_52w_high"] = (
            1.0 - (snap["price"] / snap["high_52w"]) if snap.get("high_52w") else None
        )
        snap["peg"] = None
        if snap.get("per") and snap.get("sales_growth_yoy"):
            eps_growth = snap["sales_growth_yoy"]  # サンプルなので簡易代用
            if eps_growth > 0:
                snap["peg"] = round(snap["per"] / (eps_growth * 100), 2)
        snap["data_available"] = {
            "price": snap["price"] is not None,
            "financials": snap.get("per") is not None,
        }
        snap["is_sample"] = True
        snap["updated_at"] = NOW
        snapshots_for_screening.append(snap)
        companies[code] = snap

    ranked = screener.rank(snapshots_for_screening)
    screening_by_code = {r["code"]: r for r in ranked}
    for code, snap in companies.items():
        snap["screening"] = screening_by_code.get(code)

    return {
        "generated_at": NOW,
        "mode": "sample",
        "source_info": {
            "provider": "サンプルデータ（J-Quants APIには接続していません）",
            "note": "これは画面確認用のダミーデータです。実際の株価・財務データではありません。",
        },
        "companies": companies,
    }


def main() -> None:
    site_data_dir = settings.SITE_DATA_DIR
    site_data_dir.mkdir(parents=True, exist_ok=True)

    payload = build_sample_payload()
    (site_data_dir / "watchlist_snapshot.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    companies_master = {
        code: {
            "code": code,
            "name": c["name"],
            "market_name": c["market_name"],
            "sector33_name": c["sector33_name"],
        }
        for code, c in SAMPLE_COMPANIES.items()
    }
    # 検索UIの動作確認用に、サンプル以外の企業もいくつか master に加える
    companies_master.update(
        {
            "7974": {"code": "7974", "name": "任天堂", "market_name": "プライム", "sector33_name": "その他製品"},
            "9433": {"code": "9433", "name": "KDDI", "market_name": "プライム", "sector33_name": "情報・通信業"},
            "8306": {"code": "8306", "name": "三菱UFJフィナンシャル・グループ", "market_name": "プライム", "sector33_name": "銀行業"},
        }
    )
    (site_data_dir / "companies_master.json").write_text(
        json.dumps(companies_master, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"サンプルデータを書き出しました: {site_data_dir}")


if __name__ == "__main__":
    main()
