import subprocess
import sys
import os
import streamlit as st
import pandas as pd
import seaborn as sns
from google.cloud import bigquery
from google.oauth2 import service_account
import matplotlib.pyplot as plt
import japanize_matplotlib
import datetime as dt
import json
import db_dtypes
from bs4 import BeautifulSoup
import pathlib
import shutil

GTM_ID = "google_tag_manager"
GTM_HEAD_SCRIPT = """
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-5Z976GNJ');</script>
<!-- End Google Tag Manager -->
"""

GTM_BODY_SCRIPT = """
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-5Z976GNJ"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->
"""

def inject_gtm():
    # index.html のパスを取得
    index_path = pathlib.Path(st.__file__).parent / "static" / "index.html"
    soup = BeautifulSoup(index_path.read_text(), features="html.parser")

    # <head> 内のなるべく上のほうに GTM スクリプトを挿入
    if not soup.find(id=GTM_ID):
        # バックアップを作成
        bck_index = index_path.with_suffix('.bck')
        if not bck_index.exists():
            shutil.copy(index_path, bck_index)

        # <head> タグの最初の部分に GTM のスクリプトを追加
        head_tag = soup.head
        head_tag.insert(0, BeautifulSoup(GTM_HEAD_SCRIPT, "html.parser"))

        # 既存のメタディスクリプションを削除
        existing_meta_description = soup.find("meta", {"name": "description"})
        if existing_meta_description:
            existing_meta_description.decompose()

        # 新しいメタディスクリプションを挿入
        meta_description = BeautifulSoup(
            '<meta name="description" content="複数の銘柄の株価パフォーマンスを一目で比較。リアルタイムデータとチャートで投資判断をサポートする、使いやすい株式比較ツール。">', 
            "html.parser"
        )
        head_tag.insert(1, meta_description)

        # <body> 開始タグの直後に GTM の noscript を追加
        body_tag = soup.body
        body_tag.insert(0, BeautifulSoup(GTM_BODY_SCRIPT, "html.parser"))

        # 新しい HTML を index.html に書き込み
        index_path.write_text(str(soup))

# GTM タグを挿入
inject_gtm()

# ページの設定
st.set_page_config(
    page_title="株価パフォーマンス比較",
    page_icon="📈",
    layout="wide"
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
        default=['トヨタ自'] if 'トヨタ自' in stock_names_df['name'].values else [stock_names_df['name'].iloc[0]]
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
    # BigQueryクライアントの初期化
    @st.cache_resource
    def get_bigquery_client():
        try:
            # 環境変数からサービスアカウント情報を取得
            service_account_info = {
                "type": "service_account",
                "project_id": os.environ.get("GCP_PROJECT_ID"),
                "private_key_id": os.environ.get("GCP_PRIVATE_KEY_ID"),
                "private_key": os.environ.get("GCP_PRIVATE_KEY").replace('\\n', '\n'),
                "client_email": os.environ.get("GCP_CLIENT_EMAIL"),
                "client_id": os.environ.get("GCP_CLIENT_ID"),
                "auth_uri": os.environ.get("GCP_AUTH_URI"),
                "token_uri": os.environ.get("GCP_TOKEN_URI"),
                "auth_provider_x509_cert_url": os.environ.get("GCP_AUTH_PROVIDER_X509_CERT_URL"),
                "client_x509_cert_url": os.environ.get("GCP_CLIENT_X509_CERT_URL")
            }
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            client = bigquery.Client(credentials=credentials, project=service_account_info["project_id"])
            return client
        except Exception as e:
            st.error(f"認証情報の読み込み中にエラーが発生しました: {e}")
            return None

    client = get_bigquery_client()

    if client is None:
        st.error("BigQueryクライアントの初期化に失敗しました。")
    else:
        # BigQueryからデータを取得する関数
        @st.cache_data
        def get_stock_data_from_bq(codes, start, end):
            try:
                # クエリの作成
                query = """
                    SELECT date, stock_code, close
                    FROM `dbt-analytics-engineer-435907.stock_dataset_mart.fct_stock_data`
                    WHERE stock_code IN UNNEST(@codes)
                      AND date BETWEEN @start_date AND @end_date
                    ORDER BY date ASC
                """
                # クエリジョブの設定
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ArrayQueryParameter("codes", "STRING", codes),
                        bigquery.ScalarQueryParameter("start_date", "DATE", start),
                        bigquery.ScalarQueryParameter("end_date", "DATE", end),
                    ]
                )
                # クエリの実行
                query_job = client.query(query, job_config=job_config)
                df = query_job.to_dataframe()
                if df.empty:
                    st.warning("指定された条件に合致するデータが存在しません。")
                    return None
      
                return df
            except Exception as e:
                st.error(f"BigQueryからのデータ取得中にエラーが発生しました: {e}")
                return None

        # 選択された銘柄のデータを取得
        df_bq = get_stock_data_from_bq(selected_stock_codes, start_date, end_date)

        if df_bq is None:
            st.error("選択された銘柄のデータが取得できませんでした。")
        else:
            # 各銘柄のデータを正規化
            dfs = []
            for code in selected_stock_codes:
                df = df_bq[df_bq['stock_code'] == code].copy()
                if df.empty:
                    st.warning(f"{code} のデータが存在しません。")
                    continue
                # 最初の日付のクローズ価格を取得
                first_date = df['date'].min()
                standard_value = df.loc[df['date'] == first_date, 'close'].iloc[0]
                # 正規化したクローズ価格を計算
                df[f'{code}'] = (df['close'] / standard_value) * 100
                # 必要な列だけを抽出
                dfs.append(df[['date', f'{code}']])

            if not dfs:
                st.error("選択された銘柄のデータが取得できませんでした。")
            else:
                # データフレームのマージ
                output_df = dfs[0]
                for df in dfs[1:]:
                    output_df = pd.merge(output_df, df, on='date', how='inner')

                # データを「長い形式」に変換
                output_df_melted = output_df.melt(id_vars='date', var_name='stock_code', value_name='normalized_close')

                # 株コードと銘柄名のマッピング
                code_to_name = dict(zip(stock_names_df['code'].astype(str), stock_names_df['name']))
                output_df_melted['stock_name'] = output_df_melted['stock_code'].map(code_to_name)

                # マッピングに失敗した場合の処理
                missing_names = output_df_melted[output_df_melted['stock_name'].isna()]['stock_code'].unique()
                if len(missing_names) > 0:
                    st.warning(f"以下の株コードの銘柄名がマッピングされていません: {missing_names}")
                    for code in missing_names:
                        code_to_name[code] = code  # 例として株コードをそのまま使用
                    output_df_melted['stock_name'] = output_df_melted['stock_code'].map(code_to_name)

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
                    x='date',
                    y='normalized_close',
                    hue='stock_name',
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
