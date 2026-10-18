"""
日本株監視アシスタント 設定ファイル。

すべての閾値・パスをここに集約する。数値の意味を変えたいときは
コードではなくこのファイルを編集する。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # ローカル開発用。存在しなければ何もしない（GitHub Actionsでは無視される）

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "watchlist.db"
SITE_DIR = BASE_DIR / "site"
SITE_DATA_DIR = SITE_DIR / "data"

# 監視対象の銘柄コード一覧（このファイルに「コードだけ」を保存する。
# 購入検討価格・メモ・アラート条件などの個人データはブラウザのlocalStorageのみに
# 保存され、このリポジトリには一切含まれない）。
WATCHLIST_CODES_PATH = DATA_DIR / "watchlist_codes.json"

# --------------------------------------------------------------------------
# J-Quants API (V2) — https://jpx-jquants.com/
# --------------------------------------------------------------------------
JQUANTS_API_KEY = os.environ.get("JQUANTS_API_KEY", "")
JQUANTS_BASE_URL = "https://api.jquants.com/v2"
# Free プラン = 5 req/min。デフォルトは安全側。契約プランに応じて環境変数で上書き可。
JQUANTS_REQUESTS_PER_MINUTE = int(os.environ.get("JQUANTS_REQUESTS_PER_MINUTE", "5"))

# 価格履歴の取得日数（52週高値・前日比の計算に必要な分だけ取得する）
PRICE_HISTORY_DAYS = 400

# --------------------------------------------------------------------------
# 割安成長株抽出（明示的ルール。AIは判定に関与しない）
# --------------------------------------------------------------------------
SCREEN_MIN_SALES_GROWTH = 0.08          # 売上高成長率がこれ以上なら「成長」とみなす
SCREEN_MIN_OPERATING_PROFIT_GROWTH = 0.08
SCREEN_MAX_PER_FOR_VALUE = 15.0         # これ以下のPERを「割安」の目安とする
SCREEN_MAX_PEG_FOR_VALUE = 1.0          # PEG（PER÷EPS成長率%）がこれ以下なら割安成長
SCREEN_MIN_EQUITY_RATIO = 0.30          # 自己資本比率がこれ以上なら健全とみなす
SCREEN_MIN_OPERATING_MARGIN = 0.08
SCREEN_MIN_DRAWDOWN_FROM_HIGH = 0.15    # 52週高値からこれ以上下落していれば「調整中」

# ランキング上位に出すために最低限必要なデータ（これが欠けている銘柄は
# 「データ不足」としてランキング上位に出さない）
SCREEN_REQUIRED_FIELDS = ["price", "per", "sales_growth_yoy", "operating_profit_growth_yoy"]
