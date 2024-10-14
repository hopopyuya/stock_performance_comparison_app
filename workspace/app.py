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

# ページの設定
st.set_page_config(
    page_title="stock_performance_comparison",
    layout="wide",
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
                    FROM `dbt-analytics-engineer-435907.dbt_test_stock_dataset.fct_stock_data`
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
            # 以下、データ処理とグラフ描画のコード
            # （前述のコードをそのまま使用します）
            # 各銘柄のデータを正規化
            # ...

            # データフレームのマージ、プロット作成など
            # ...

            # グラフをStreamlitに表示
            st.pyplot(plt, facecolor=BG_COLOR)

            # 図を閉じてメモリを解放
            plt.clf()
            plt.close()
