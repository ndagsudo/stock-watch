"""
割安成長株の抽出（明示的ルールのみ。AIは判定に関与しない）。

各銘柄について、config/settings.py にある閾値と比較し、
「注目理由」「懸念点」「データ基準日」「データ十分か」を組み立てる。
ランキングはスコアの高い順だが、SCREEN_REQUIRED_FIELDS が欠けている銘柄は
データ不十分として上位に出さない（リストの末尾、あるいは別枠に回す）。
"""
from __future__ import annotations

from typing import Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings


def _fmt_pct(x: Optional[float]) -> str:
    return "不明" if x is None else f"{x * 100:.1f}%"


def evaluate(snapshot: dict) -> dict:
    """1銘柄のスナップショット(indicators.build_snapshotの戻り値)を評価する。"""
    reasons: list[str] = []
    concerns: list[str] = []
    score = 0.0

    per = snapshot.get("per")
    peg = snapshot.get("peg")
    pbr = snapshot.get("pbr")
    sales_growth = snapshot.get("sales_growth_yoy")
    op_growth = snapshot.get("operating_profit_growth_yoy")
    equity_ratio = snapshot.get("equity_ratio")
    op_margin = snapshot.get("operating_margin")
    drawdown = snapshot.get("drawdown_from_52w_high")
    roe = snapshot.get("roe")

    # 割安度
    if peg is not None and peg <= settings.SCREEN_MAX_PEG_FOR_VALUE:
        reasons.append(f"PEGレシオが{peg:.2f}と割安（成長率に対してPERが低い）")
        score += 25
    elif per is not None and per <= settings.SCREEN_MAX_PER_FOR_VALUE:
        reasons.append(f"PERが{per:.1f}倍と低め")
        score += 15
    elif per is not None:
        concerns.append(f"PERが{per:.1f}倍で割安感は薄い")

    if pbr is not None and pbr < 1.0:
        reasons.append(f"PBRが{pbr:.2f}倍で解散価値に近い水準")
        score += 5

    # 成長性
    if sales_growth is not None and sales_growth >= settings.SCREEN_MIN_SALES_GROWTH:
        reasons.append(f"売上高成長率が{_fmt_pct(sales_growth)}")
        score += 15
    elif sales_growth is not None and sales_growth < 0:
        concerns.append(f"売上高が前期比{_fmt_pct(sales_growth)}で減少")

    if op_growth is not None and op_growth >= settings.SCREEN_MIN_OPERATING_PROFIT_GROWTH:
        reasons.append(f"営業利益成長率が{_fmt_pct(op_growth)}")
        score += 20
    elif op_growth is not None and op_growth < 0:
        concerns.append(f"営業利益が前期比{_fmt_pct(op_growth)}で減少")

    # 収益性
    if op_margin is not None and op_margin >= settings.SCREEN_MIN_OPERATING_MARGIN:
        reasons.append(f"営業利益率が{_fmt_pct(op_margin)}と高め")
        score += 10
    if roe is not None and roe >= 0.10:
        reasons.append(f"ROEが{_fmt_pct(roe)}")
        score += 10

    # 財務健全性
    if equity_ratio is not None and equity_ratio >= settings.SCREEN_MIN_EQUITY_RATIO:
        score += 5
    elif equity_ratio is not None:
        concerns.append(f"自己資本比率が{_fmt_pct(equity_ratio)}と低め")

    # 株価位置（調整中かどうか）
    if drawdown is not None and drawdown >= settings.SCREEN_MIN_DRAWDOWN_FROM_HIGH:
        reasons.append(f"52週高値から{_fmt_pct(drawdown)}下落しており調整中")
        score += 10

    missing = [f for f in settings.SCREEN_REQUIRED_FIELDS if snapshot.get(f) is None]
    data_sufficient = len(missing) == 0

    if not reasons:
        reasons.append("明確な割安・成長シグナルは見つかりませんでした")

    as_of_date = snapshot.get("latest_disclosure_date") or snapshot.get("price_date")

    return {
        "score": round(score, 1) if data_sufficient else None,
        "notable_reasons": reasons,
        "concerns": concerns,
        "data_sufficient": data_sufficient,
        "missing_fields": missing,
        "as_of_date": as_of_date,
    }


def rank(snapshots: list[dict]) -> list[dict]:
    """データ十分な銘柄をスコア降順→データ不足銘柄を末尾に、という順で並べる。
    各要素は {code, name, score, ...evaluate()の出力} を持つ。"""
    evaluated = []
    for s in snapshots:
        ev = evaluate(s)
        evaluated.append({"code": s.get("code"), "name": s.get("name"), **ev})

    sufficient = [e for e in evaluated if e["data_sufficient"]]
    insufficient = [e for e in evaluated if not e["data_sufficient"]]
    sufficient.sort(key=lambda e: e["score"] or 0, reverse=True)
    return sufficient + insufficient
