import requests
import zipfile
import io
import pandas as pd
import os
from datetime import datetime
from math import log, sqrt, exp
from scipy.stats import norm
from scipy.optimize import brentq
import yfinance as yf

SAVE_DIR = r"C:\temp\option\TargetBuy\jpx_daily"
os.makedirs(SAVE_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(SAVE_DIR, "daily_option_data.csv")

TARGET_CODES = [
    "7203","9432","9984","6758","8306","8035","6861","4502",
    "4063","6954","7974","6098","2413","2801","2914","3382",
    "5108","5401","5713","5802","6301","6501","6503","6594",
    "6702","6723","6752","6762"
]

ZIP_URL_TEMPLATE = "https://www.jpx.co.jp/markets/derivatives/option-price/data/ose{day}tp.zip"


# -------------------------
# 株価を yfinance から取得（trade_date に対応）
# -------------------------
def get_stock_price_from_yf(code, trade_date):
    """
    指定した trade_date 当日またはそれ以前で一番近い終値を返す。
    """
    try:
        ticker = yf.Ticker(f"{code}.T")

        start = trade_date - pd.Timedelta(days=10)
        end   = trade_date + pd.Timedelta(days=1)

        hist = ticker.history(start=start, end=end, interval="1d")
        if hist.empty:
            return None

        idx = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
        hist = hist[idx <= trade_date]

        if hist.empty:
            return None

        return float(hist["Close"].iloc[-1])

    except Exception:
        return None


# -------------------------
# ブラックショールズ
# -------------------------
def bs_call_price(S, K, T, r, sigma):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    d1 = (log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt(T))
    d2 = d1 - sigma*sqrt(T)
    return S * norm.cdf(d1) - K * exp(-r*T) * norm.cdf(d2)

def bs_put_price(S, K, T, r, sigma):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    d1 = (log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt(T))
    d2 = d1 - sigma*sqrt(T)
    return K * exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def implied_vol_put(S, K, T, r, market_price):
    try:
        return brentq(
            lambda sigma: bs_put_price(S, K, T, r, sigma) - market_price,
            0.0001, 3.0
        )
    except Exception:
        return None
# JPX CSV の 17 列ヘッダー
HEADER_ROW = [
    "商品コード","商品タイプ","限月","権利行使価格","理論価格","清算価格",
    "コール出来高","プット出来高","コール終値","コールIV",
    "プット終値","原資産終値","プットIV","基準価格","基準IV",
    "追加列1","追加列2"
]

def read_jpx_csv(csv_file):
    df = pd.read_csv(csv_file, encoding="shift_jis", header=None, names=HEADER_ROW)
    df["商品コード4桁"] = df["商品コード"].astype(str).str[:4]
    return df


def process_one_day(csv_file, trade_date_str):
    df = read_jpx_csv(csv_file)
    if df is None:
        return []

    records = []
    trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d")

    for code in TARGET_CODES:
        df_code = df[df["商品コード4桁"] == code]
        if df_code.empty:
            continue

        # -------------------------
        # 株価：まず JPX → ダメなら yfinance（trade_date 対応）
        # -------------------------
        spot = None
        try:
            spot = float(df_code["原資産終値"].iloc[0])
        except:
            spot = None

        if spot is None or spot <= 0:
            spot = get_stock_price_from_yf(code, trade_date)

        if spot is None or spot <= 0:
            continue

        call_target = spot * 1.05
        put_target  = spot * 0.95

        next_month = (trade_date + pd.DateOffset(months=1)).strftime("%Y%m")
        df_m = df_code[df_code["限月"].astype(str).str.strip() == next_month]
        if df_m.empty:
            continue

        df_m = df_m.copy()
        df_m["権利行使価格"] = pd.to_numeric(df_m["権利行使価格"], errors="coerce")
        df_m = df_m.dropna(subset=["権利行使価格"])
        if df_m.empty:
            continue

        call_row = df_m.iloc[(df_m["権利行使価格"] - call_target).abs().argmin()]
        put_row  = df_m.iloc[(df_m["権利行使価格"] - put_target).abs().argmin()]

        call_strike = float(call_row["権利行使価格"])
        put_strike  = float(put_row["権利行使価格"])

        if abs(call_strike - spot) / spot > 0.20:
            continue
        if abs(put_strike - spot) / spot > 0.20:
            continue

        call_price = call_row.get("コール終値", None)
        put_price  = put_row.get("プット終値", None)

        sigma_call = None
        try:
            raw_sigma = call_row.get("コールIV", None)
            if raw_sigma is not None:
                sigma_call = float(raw_sigma)
                if sigma_call <= 0:
                    sigma_call = None
        except:
            sigma_call = None

        asset_iv = call_row.get("基準IV", None)

        T = 30 / 365
        r = 0.0

        call_theo = None
        put_theo  = None
        if sigma_call is not None:
            try:
                call_theo = bs_call_price(spot, call_strike, T, r, sigma_call)
                put_theo  = bs_put_price(spot, put_strike, T, r, sigma_call)
            except:
                pass

        put_iv = None
        try:
            if put_price is not None and float(put_price) > 0:
                put_iv = implied_vol_put(
                    S=spot, K=put_strike, T=T, r=r, market_price=float(put_price)
                )
        except:
            put_iv = None

        records.append([
            trade_date_str, code, spot, next_month,
            call_strike, call_price, call_theo, sigma_call,
            put_strike, put_price, put_theo, put_iv,
            asset_iv
        ])

    return records
def fetch_and_process_day(trade_date):
    day_str = trade_date.strftime("%Y%m%d")
    trade_date_str = trade_date.strftime("%Y-%m-%d")
    url = ZIP_URL_TEMPLATE.format(day=day_str)
    print(f"[取得] {trade_date_str} → {url}")

    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"  -> ZIP取得失敗 (status={resp.status_code})")
            return []

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_name = [n for n in z.namelist() if n.endswith(".csv")][0]
            with z.open(csv_name) as f:
                return process_one_day(f, trade_date_str)

    except Exception as e:
        print(f"  -> エラー: {e}")
        return []


def main():
    if os.path.exists(OUTPUT_CSV):
        df_csv = pd.read_csv(OUTPUT_CSV)
        existing_dates = set(df_csv["日付"].astype(str).tolist())
        print(f"既存CSV読み込み: {OUTPUT_CSV}（{len(df_csv)}行）")
    else:
        df_csv = pd.DataFrame(columns=[
            "日付","銘柄","株価","限月",
            "コールスト","コール終値","コール理論","コールIV",
            "プットスト","プット終値","プット理論","プットIV",
            "原資産IV"
        ])
        existing_dates = set()
        print(f"新規CSVとして作成予定: {OUTPUT_CSV}")

    start_date = datetime(2025, 10, 8)
    today = datetime.today()
    all_days = pd.date_range(start_date, today, freq="B")

    missing_days = [
        d for d in all_days
        if d.strftime("%Y-%m-%d") not in existing_dates
    ]

    print(f"=== 欠損日: {len(missing_days)}件 ===")
    all_records = []

    for d in missing_days:
        recs = fetch_and_process_day(d)
        if recs:
            print(f"  -> {d.strftime('%Y-%m-%d')}: {len(recs)}件")
            all_records.extend(recs)
        else:
            print(f"  -> {d.strftime('%Y-%m-%d')}: データなし or 抽出0件")

    if all_records:
        df_new = pd.DataFrame(all_records, columns=[
            "日付","銘柄","株価","限月",
            "コールスト","コール終値","コール理論","コールIV",
            "プットスト","プット終値","プット理論","プットIV",
            "原資産IV"
        ])

        df_all = pd.concat([df_csv, df_new], ignore_index=True)
        df_all = df_all.sort_values(["日付","銘柄"])
        df_all.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

        print(f"✅ 保存完了: {OUTPUT_CSV}（合計 {len(df_all)} 行）")
    else:
        print("⚠️ 新規レコードなし（全日データなし or 既存と重複）")


if __name__ == "__main__":
    main()
