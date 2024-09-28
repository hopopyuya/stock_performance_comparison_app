import streamlit as st
import pandas as pd
import seaborn as sns
import yfinance as yf
import matplotlib.pyplot as plt
import japanize_matplotlib
import requests
from io import StringIO
import datetime as dt

# ページの設定
st.set_page_config(
    page_title="stock_performance_comparison",
    layout="wide",  # "wide" レイアウトを維持
)

# タイトルの表示
st.title("stock_performance_comparison")

# 銘柄名データの読み込み
stock_names_df = pd.read_csv('./stock_code_name_mapping.csv', usecols=[0,1])

# メインページに選択ウィジェットを配置
st.header("filter")

# レイアウトの設定（レスポンシブに対応）
col1, col2 = st.columns([3, 2])  # ウィジェットの幅比率を調整

with col1:
    # 銘柄の選択
    selected_stock_names = st.multiselect(
        "銘柄を選択してください",
        options=stock_names_df['name'],
        default=[stock_names_df['name'][0]] if not stock_names_df.empty else None
    )

with col2:
    # 日付範囲の選択
    today = dt.date.today()
    default_start = dt.date(2024, 1, 1)
    start_date, end_date = st.date_input(
        "日付範囲を選択してください",
        value=(default_start, today),
        min_value=dt.date(2000, 1, 1),
        max_value=today
    )

st.markdown("---")  # 区切り線

# 選択された銘柄名から銘柄コードを取得
selected_stock_codes = stock_names_df[stock_names_df['name'].isin(selected_stock_names)]['code'].astype(str).tolist()

if not selected_stock_codes:
    st.warning("銘柄を選択してください。")
else:
    # yfinanceで株価データを取得する関数
    @st.cache_data
    def get_stock_data(ticker, start, end):
        try:
            df = yf.download(ticker, start=start, end=end)
            if df.empty:
                st.warning(f"{ticker} のデータが見つかりませんでした。")
                return None
            df.reset_index(inplace=True)
            df.sort_values('Date', inplace=True)
            return df
        except Exception as e:
            st.error(f"{ticker} のデータ取得中にエラーが発生しました: {e}")
            return None

    # 選択された銘柄のデータを取得
    dfs = []
    for code in selected_stock_codes:
        ticker = f"{code}.T"
        df = get_stock_data(ticker, start_date, end_date)
        if df is not None:
            # 最初の日付のクローズ価格を取得
            first_date = df['Date'].min()
            standard_value = df.loc[df['Date'] == first_date, 'Close'].iloc[0]
            # 正規化したクローズ価格を計算
            df[f'{code}'] = (df['Close'] / standard_value) * 100
            # 必要な列だけを抽出
            dfs.append(df[['Date', f'{code}']])

    if not dfs:
        st.error("選択された銘柄のデータが取得できませんでした。")
    else:
        # データフレームのマージ
        output_df = dfs[0]
        for df in dfs[1:]:
            output_df = pd.merge(output_df, df, on='Date', how='inner')

        # データを「長い形式」に変換
        output_df_melted = output_df.melt(id_vars='Date', var_name='Stock_Code', value_name='Normalized_Close')

        # 株コードと銘柄名のマッピング
        code_to_name = dict(zip(stock_names_df['code'].astype(str), stock_names_df['name']))
        output_df_melted['Stock_Name'] = output_df_melted['Stock_Code'].map(code_to_name)

        # マッピングに失敗した場合の処理
        missing_names = output_df_melted[output_df_melted['Stock_Name'].isna()]['Stock_Code'].unique()
        if len(missing_names) > 0:
            st.warning(f"以下の株コードの銘柄名がマッピングされていません: {missing_names}")
            for code in missing_names:
                code_to_name[code] = code  # 例として株コードをそのまま使用
            output_df_melted['Stock_Name'] = output_df_melted['Stock_Code'].map(code_to_name)

        # 背景色を定義
        BG_COLOR = '#0E1117'
        # プロットの作成
        plt.figure(figsize=(14, 7), facecolor=BG_COLOR)  # フィギュアの背景色を設定

        # Seabornのスタイルをカスタマイズ
        sns.set_style("darkgrid", {
            "axes.facecolor": BG_COLOR,      # 軸の背景色
            "figure.facecolor": BG_COLOR,    # フィギュアの背景色
            "grid.color": "#444444"           # グリッドの色
        })

        # 日本語フォントを適用
        japanize_matplotlib.japanize()

        # Seabornのコンテキストとスタイルを設定
        sns.set_context("notebook", font_scale=1.2)  # フォントスケールを調整

        # ラインプロットを作成
        sns.lineplot(
            data=output_df_melted,
            x='Date',
            y='Normalized_Close',
            hue='Stock_Name',
            marker='o',
            palette='bright'  # 明るい色のパレットを使用
        )

        # 100%の水平線を追加
        plt.axhline(y=100, color='white', linestyle='--', linewidth=1, alpha=0.7, label='基準値 (100%)')

        # タイトルとラベルの設定
        plt.title('stock_performance_comparison', color='white', fontsize=18)
        plt.xlabel('date', color='white', fontsize=16)
        plt.ylabel('stock_price_performance (%)', color='white', fontsize=16)

        # 現在の軸を取得
        ax = plt.gca()

        # 軸の背景色を黒に設定
        ax.set_facecolor(BG_COLOR)

        # スパイン（枠線）の色を白に設定
        for spine in ax.spines.values():
            spine.set_edgecolor('white')

        # 目盛りの色を白に設定
        ax.tick_params(colors='white', which='both')

        # X軸とY軸の目盛りラベルの色も白に設定
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_color('white')

        # 凡例の設定（フォントサイズを大きく）
        legend = plt.legend(
            title='銘柄名',
            bbox_to_anchor=(1.05, 1),
            loc='upper left',
            fontsize=18,          # 凡例項目のフォントサイズ
            title_fontsize=20     # 凡例タイトルのフォントサイズ
        )
        for text in legend.get_texts():
            text.set_color("white")
        legend.get_title().set_color("white")

        # X軸の目盛りを45度回転
        plt.xticks(rotation=45, color='white')

        # レイアウトを調整して余白を最小化
        plt.tight_layout()

        # グラフをStreamlitに表示
        st.pyplot(plt, facecolor=BG_COLOR)

        # 図を閉じてメモリを解放
        plt.clf()
        plt.close()
