import datetime as dt
import os
import pathlib
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import japanize_matplotlib
import streamlit as st
from bs4 import BeautifulSoup
from google.cloud import bigquery, storage
from google.oauth2 import service_account


@dataclass
class GCPCredentials:
    """Google Cloud Platform credentials container"""
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_x509_cert_url: str


class GCSBigQueryFacade:
    """Facade for interacting with Google Cloud Storage and BigQuery services"""
    
    def __init__(self, project_id: str, dataset_name: str, table_name: str, bucket_name: str):
        self.project_id = project_id
        self.dataset_name = dataset_name
        self.table_name = table_name
        self.bucket_name = bucket_name
        
        self.credentials = self._load_credentials()
        self.bq_client = self._initialize_bigquery_client()
        self.storage_client = self._initialize_storage_client()

    def _load_credentials(self) -> GCPCredentials:
        """Load GCP credentials from environment variables"""
        return GCPCredentials(
            project_id=os.environ.get("GCP_PROJECT_ID", ""),
            private_key_id=os.environ.get("GCP_PRIVATE_KEY_ID", ""),
            private_key=os.environ.get("GCP_PRIVATE_KEY", "").replace('\\n', '\n'),
            client_email=os.environ.get("GCP_CLIENT_EMAIL", ""),
            client_id=os.environ.get("GCP_CLIENT_ID", ""),
            auth_uri=os.environ.get("GCP_AUTH_URI", ""),
            token_uri=os.environ.get("GCP_TOKEN_URI", ""),
            auth_provider_x509_cert_url=os.environ.get("GCP_AUTH_PROVIDER_X509_CERT_URL", ""),
            client_x509_cert_url=os.environ.get("GCP_CLIENT_X509_CERT_URL", "")
        )

    def _initialize_bigquery_client(self) -> bigquery.Client:
        """Initialize BigQuery client"""
        credentials = service_account.Credentials.from_service_account_info(vars(self.credentials))
        return bigquery.Client(credentials=credentials, project=self.credentials.project_id)

    def _initialize_storage_client(self) -> storage.Client:
        """Initialize Storage client"""
        credentials = service_account.Credentials.from_service_account_info(vars(self.credentials))
        return storage.Client(credentials=credentials, project=self.credentials.project_id)

    # @st.cache_data(ttl=3600)
    def read_parquet_from_gcs(self, file_name: str) -> pd.DataFrame:
        """Read parquet file from Google Cloud Storage"""
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(file_name)
            
            local_file_path = f"/tmp/{file_name}"
            blob.download_to_filename(local_file_path)
            
            df = pd.read_parquet(local_file_path, engine='pyarrow')
            os.remove(local_file_path)  # Clean up temporary file
            
            return df
        except Exception as e:
            st.error(f"Failed to read parquet file: {str(e)}")
            return pd.DataFrame()

    # @st.cache_data(ttl=300)
    def get_stock_data(self, codes: List[str], start_date: dt.date, end_date: dt.date) -> Optional[pd.DataFrame]:
        """Fetch stock data from BigQuery"""
        try:
            query = """
                SELECT date, stock_code, close
                FROM `{}.{}.{}`
                WHERE stock_code IN UNNEST(@codes)
                  AND date BETWEEN @start_date AND @end_date
                ORDER BY date ASC
            """.format(self.project_id, self.dataset_name, self.table_name)

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("codes", "STRING", codes),
                    bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                    bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
                ]
            )
            
            return self.bq_client.query(query, job_config=job_config).to_dataframe()
        except Exception as e:
            st.error(f"Failed to fetch stock data: {str(e)}")
            return None


class GTMInjector:
    """Google Tag Manager injector for Streamlit"""
    
    GTM_ID = "GTM-5Z976GNJ"
    
    @classmethod
    def inject(cls) -> None:
        """Inject GTM scripts into Streamlit's index.html"""
        index_path = pathlib.Path(st.__file__).parent / "static" / "index.html"
        soup = BeautifulSoup(index_path.read_text(), features="html.parser")

        if not soup.find(id="google_tag_manager"):
            # Create backup
            bck_index = index_path.with_suffix('.bck')
            if not bck_index.exists():
                shutil.copy(index_path, bck_index)

            cls._inject_head_content(soup)
            cls._inject_body_content(soup)
            
            index_path.write_text(str(soup))

    @classmethod
    def _inject_head_content(cls, soup: BeautifulSoup) -> None:
        """Inject GTM script and meta description into head"""
        head_tag = soup.head
        
        # Add GTM script
        gtm_script = cls._get_gtm_head_script()
        head_tag.insert(0, BeautifulSoup(gtm_script, "html.parser"))
        
        # Update meta description
        existing_meta = soup.find("meta", {"name": "description"})
        if existing_meta:
            existing_meta.decompose()
        
        meta_description = BeautifulSoup(
            '<meta name="description" content="複数の銘柄の株価パフォーマンスを一目で比較。'
            'リアルタイムデータとチャートで投資判断をサポートする、使いやすい株式比較ツール。">', 
            "html.parser"
        )
        head_tag.insert(1, meta_description)

    @classmethod
    def _inject_body_content(cls, soup: BeautifulSoup) -> None:
        """Inject GTM noscript into body"""
        body_tag = soup.body
        gtm_noscript = cls._get_gtm_body_script()
        body_tag.insert(0, BeautifulSoup(gtm_noscript, "html.parser"))

    @classmethod
    def _get_gtm_head_script(cls) -> str:
        return f"""
        <!-- Google Tag Manager -->
        <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
        new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
        j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
        'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
        }})(window,document,'script','dataLayer','{cls.GTM_ID}');</script>
        <!-- End Google Tag Manager -->
        """

    @classmethod
    def _get_gtm_body_script(cls) -> str:
        return f"""
        <!-- Google Tag Manager (noscript) -->
        <noscript><iframe src="https://www.googletagmanager.com/ns.html?id={cls.GTM_ID}"
        height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
        <!-- End Google Tag Manager (noscript) -->
        """


def main():
    """Main application entry point"""
    # Initialize GTM
    GTMInjector.inject()

    # Configure Streamlit page
    st.set_page_config(
        page_title="株価パフォーマンス比較",
        page_icon="📈",
        layout="wide"
    )
    st.title("Stock Performance Comparison")

    # Initialize GCP facade
    gcs_bq = GCSBigQueryFacade(
        project_id=os.environ.get("GCP_PROJECT_ID"),
        dataset_name="stock_dataset_mart",
        table_name="fct_stock_data",
        bucket_name="stock-data-bucket_hopop"
    )

    # Load stock data
    stock_names_df = gcs_bq.read_parquet_from_gcs("stocklist.parquet")

    # Create filter section
    st.header("Filter")
    col1, col2 = st.columns([3, 2])

    with col1:
        default_stock = 'トヨタ自動車' if 'トヨタ自動車' in stock_names_df['name'].values else stock_names_df['name'].iloc[0]
        selected_stock_names = st.multiselect(
            "銘柄を選択してください",
            options=stock_names_df['name'].tolist(),
            default=[default_stock]
        )

    with col2:
        today = dt.date.today()
        default_start = dt.date(2024, 1, 1)
        start_date, end_date = st.date_input(
            "日付範囲を選択してください",
            value=(default_start, today),
            min_value=dt.date(2023, 1, 1),
            max_value=today
        )

    st.markdown("---")

    # Process selected stocks
    selected_stocks = stock_names_df[stock_names_df['name'].isin(selected_stock_names)]
    selected_stock_codes = selected_stocks['code'].astype(str).tolist()

    if not selected_stock_codes:
        st.warning("銘柄を選択してください。")
        return

    # Fetch and process stock data
    df = gcs_bq.get_stock_data(selected_stock_codes, start_date, end_date)

    if df is None or df.empty:
        st.error("選択された銘柄のデータが取得できませんでした。")
        return

    # Create normalized data
    normalized_data_list = []
    stock_code_to_name = dict(zip(selected_stocks['code'].astype(str), selected_stocks['name']))
    for code in selected_stock_codes:
        stock_data = df[df['stock_code'] == code].copy()
        base_value = stock_data.iloc[0]['close']
        stock_data['normalized_close'] = (stock_data['close'] / base_value) * 100
        stock_data['stock_name'] = stock_code_to_name[code]  # Add stock name
        normalized_data_list.append(stock_data[['date', 'normalized_close', 'stock_name']])
    normalized_data = pd.concat(normalized_data_list, ignore_index=True)

    

    # プロットの作成
    BG_COLOR = '#0E1117'
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
        data=normalized_data,
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



if __name__ == "__main__":
    main()
