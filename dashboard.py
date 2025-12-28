import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
import subprocess

# 日本語フォント（Windows用）
plt.rcParams['font.family'] = 'MS Gothic'

# 銘柄コード → 銘柄名 対応表
code_to_name = {
    "7203": "トヨタ自動車", "9432": "NTT", "9984": "ソフトバンクG", "6758": "ソニーG",
    "8306": "三菱UFJ", "8035": "東京エレクトロン", "6861": "キーエンス", "4502": "武田薬品",
    "4063": "信越化学", "6954": "ファナック", "7974": "任天堂", "6098": "リクルート",
    "2413": "エムスリー", "2801": "キッコーマン", "2914": "JT", "3382": "セブン＆アイHD",
    "5108": "ブリヂストン", "5401": "日本製鉄", "5713": "住友金属鉱山", "5802": "住友電気工業",
    "6301": "コマツ", "6501": "日立製作所", "6503": "三菱電機", "6594": "日本電産",
    "6702": "富士通", "6723": "ルネサス", "6752": "パナソニック", "6762": "TDK"
}

# CSVパス
csv_path = r"C:\temp\option\TargetBuy\jpx_daily\daily_option_data.csv"

# ---------------------------------------------------------
# 🔘 今すぐ更新ボタン（TargetBuyPBR.py 実行）
# ---------------------------------------------------------
st.markdown("## 📥 データ更新")

if st.button("📥 今すぐデータ更新（TargetBuyPBR.py 実行）"):
    with st.spinner("TargetBuyPBR.py を実行中…"):
        result = subprocess.run(
            ["python", r"C:\temp\option\TargetBuy\TargetBuyPBR.py"],
            capture_output=True, text=True
        )
        st.success("✅ データ更新完了")
        st.text(result.stdout)
        st.text(result.stderr)

# ---------------------------------------------------------
# CSV読み込み
# ---------------------------------------------------------
df = pd.read_csv(csv_path)
codes = sorted(df["銘柄"].unique())

st.markdown("## 📊 オプション価格比較ダッシュボード（スマホ最適化版）")

# ---------------------------------------------------------
# 📊 最新一覧（色付け＋横スクロール）
# ---------------------------------------------------------
st.subheader("📊 最新一覧")

latest_rows = []
for code in codes:
    df_code = df[df["銘柄"] == code].sort_values("日付")
    latest = df_code.iloc[-1]

    ticker = yf.Ticker(f"{code}.T")
    info = ticker.info

    latest_rows.append({
        "銘柄": code,
        "銘柄名": code_to_name.get(str(code), "不明"),
        "株価": info.get("currentPrice"),
        "原資産IV": latest.get("原資産IV"),
        "PER": info.get("trailingPE"),
        "PBR": info.get("priceToBook")
    })

df_latest = pd.DataFrame(latest_rows)

# 🔶 IV段階色分け
def highlight_iv(row):
    iv = row["原資産IV"]
    if iv is None:
        return [''] * len(row)
    if iv >= 0.30:
        return ['background-color: #cc6600; color: white'] * len(row)
    elif iv >= 0.25:
        return ['background-color: #ffcc99'] * len(row)
    else:
        return [''] * len(row)

st.dataframe(
    df_latest.style.apply(highlight_iv, axis=1),
    use_container_width=True
)

# ---------------------------------------------------------
# 🔽 銘柄選択・日付範囲選択
# ---------------------------------------------------------
st.subheader("🔍 銘柄別データ")

code = st.selectbox(
    "銘柄を選択",
    codes,
    format_func=lambda x: f"{x}：{code_to_name.get(str(x), '不明')}"
)

df_code = df[df["銘柄"] == code].sort_values("日付")

min_date = pd.to_datetime(df_code["日付"].min())
max_date = pd.to_datetime(df_code["日付"].max())

start_date, end_date = st.date_input(
    "表示する日付範囲を選択",
    [min_date, max_date]
)

df_filtered = df_code[
    (pd.to_datetime(df_code["日付"]) >= pd.to_datetime(start_date)) &
    (pd.to_datetime(df_code["日付"]) <= pd.to_datetime(end_date))
]

st.write("### データ一覧（最新順）")
st.dataframe(df_filtered.sort_values("日付", ascending=False), use_container_width=True)

# ---------------------------------------------------------
# 📈 グラフ表示（スマホ対応）
# ---------------------------------------------------------
st.subheader("📈 グラフ表示")

if st.button("📈 グラフを表示"):
    fig, ax1 = plt.subplots(figsize=(10, 5))

    ax1.plot(df_filtered["日付"], df_filtered["コール終値"], label="コール終値", color="red")
    ax1.plot(df_filtered["日付"], df_filtered["コール理論"], label="コール理論", color="orange", linestyle="--")
    ax1.set_xlabel("日付")
    ax1.set_ylabel("コール価格", color="red")
    plt.xticks(rotation=45)

    ax2 = ax1.twinx()
    ax2.plot(df_filtered["日付"], df_filtered["プット終値"], label="プット終値", color="blue")
    ax2.plot(df_filtered["日付"], df_filtered["プット理論"], label="プット理論", color="cyan", linestyle="--")
    ax2.set_ylabel("プット価格", color="blue")

    ax3 = ax1.twinx()
    ax3.spines["right"].set_position(("outward", 60))
    ax3.plot(df_filtered["日付"], df_filtered["株価"], label="株価", color="black", linewidth=3)
    ax3.set_ylabel("株価", color="black")

    lines, labels = [], []
    for ax in [ax1, ax2, ax3]:
        line, label = ax.get_legend_handles_labels()
        lines += line
        labels += label

    fig.legend(lines, labels, loc="upper left", bbox_to_anchor=(0.1, 0.9))
    plt.title(f"{code}：{code_to_name.get(str(code), '不明')} オプション価格＋株価推移")
    st.pyplot(fig)

# ---------------------------------------------------------
# 📉 IVグラフ（スマホ対応）
# ---------------------------------------------------------
if st.checkbox("IVの推移も表示する"):
    fig2, ax = plt.subplots(figsize=(10, 4))

    ax.plot(df_filtered["日付"], df_filtered["コールIV"], label="コールIV", color="red")
    ax.plot(df_filtered["日付"], df_filtered["プットIV"], label="プットIV", color="blue")
    ax.plot(df_filtered["日付"], df_filtered["原資産IV"], label="原資産IV", color="gray", linestyle="--")

    ax.set_title(f"{code}：{code_to_name.get(str(code), '不明')} IVの推移")
    ax.set_xlabel("日付")
    ax.set_ylabel("IV")
    plt.xticks(rotation=45)
    ax.legend()

    st.pyplot(fig2)
