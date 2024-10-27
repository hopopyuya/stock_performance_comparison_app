import os
import pandas as pd
import yfinance as yf
from google.cloud import bigquery
from google.cloud import storage
import datetime as dt
import time
from tqdm import tqdm
from google.oauth2 import service_account

class GCSBigQueryFacade:
    def __init__(self, project_id, dataset_name, table_name, bucket_name):
        self.project_id = project_id
        self.dataset_name = dataset_name
        self.table_name = table_name
        self.bucket_name = bucket_name

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

        # BigQueryクライアントとStorageクライアントの初期化
        self.bq_client = bigquery.Client(credentials=credentials, project=service_account_info["project_id"])
        self.storage_client = storage.Client(credentials=credentials, project=service_account_info["project_id"])

    def get_max_date_from_bq(self):
        query = f"""
            SELECT MAX(Date) as max_date 
            FROM `{self.project_id}.{self.dataset_name}.{self.table_name}`
        """
        query_job = self.bq_client.query(query)
        results = query_job.result()
        for row in results:
            return row['max_date']

    def upload_to_gcs(self, local_file_path, destination_blob_name):
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_file_path)
        tqdm.write(f"File {local_file_path} uploaded to {destination_blob_name}.")

    def delete_from_gcs(self, file_name):
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(file_name)
        if blob.exists():
            blob.delete()
            tqdm.write(f"Deleted {file_name} from GCS.")

    def load_data_to_bigquery(self, source_uri):
        dataset_ref = self.bq_client.dataset(self.dataset_name)
        table_ref = dataset_ref.table(self.table_name)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND
        )
        
        load_job = self.bq_client.load_table_from_uri(
            source_uri, table_ref, job_config=job_config
        )

        # ロードジョブが完了するまで待つ
        load_job.result()

        tqdm.write(f"Data loaded into BigQuery table {self.dataset_name}.{self.table_name} from {source_uri}.")

def suppress_yfinance_warnings():
    import logging
    yf_logger = logging.getLogger("yfinance")
    yf_logger.setLevel(logging.ERROR)

def main():
    suppress_yfinance_warnings()

    # BigQueryとGCSの設定
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    DATASET_NAME = 'stock_dataset'
    BUCKET_NAME = 'stock-data-bucket_hopop'
    TABLE_NAME = 'stock_data'

    # GCS & BigQuery操作のためのファサードを初期化
    gcs_bq = GCSBigQueryFacade(PROJECT_ID, DATASET_NAME, TABLE_NAME, BUCKET_NAME)

    # BigQueryから最大の日付を取得
    max_date = gcs_bq.get_max_date_from_bq()
    
    if max_date:
        # max_dateを文字列からdatetime型に変換
        max_date = pd.to_datetime(max_date).date()
        START_DATE = max_date + dt.timedelta(days=1)
    else:
        # データがない場合、デフォルトの開始日
        START_DATE = dt.date(2024, 1, 1)

    END_DATE = dt.date.today()

    # START_DATE == END_DATEの場合、処理をスキップ
    if START_DATE >= END_DATE:
        tqdm.write("最新データが既に存在します。新しいデータはありません。")
        return

    # GCS上のファイルが存在するかを確認し、削除
    combined_file_name = "combined_stock_data.parquet"
    gcs_bq.delete_from_gcs(combined_file_name)

    # CSVファイルのパス
    STOCK_MAPPING_CSV = 'stock_code_name_mapping.csv'

    # CSVファイルの読み込み
    stock_names_df = pd.read_csv(STOCK_MAPPING_CSV, usecols=['code', 'name'])

    # すべての銘柄のデータを結合するためのデータフレームを準備
    combined_df = pd.DataFrame()

    # tqdmを使用して進捗を可視化（バーを最上部に固定）
    progress_bar = tqdm(stock_names_df.iterrows(), total=len(stock_names_df), ncols=100, leave=True, position=0)

    for index, row in progress_bar:
        stock_code = str(row['code']).strip()
        ticker = f"{stock_code}.T"  # 東証の場合、ティッカーは通常「.T」が付加されます
        
        # 株価データの取得
        df = yf.download(ticker, start=START_DATE, end=END_DATE)

        if df.empty:
            tqdm.write(f"No data found for {ticker}. Skipping...")
        else:
            # データフレームの前処理
            df.reset_index(inplace=True)
            df = df.rename(columns={
                'Date': 'Date',
                'Open': 'Open',
                'High': 'High',
                'Low': 'Low',
                'Close': 'Close',
                'Adj Close': 'Adj_Close',
                'Volume': 'Volume'
            })
            df['Stock_Code'] = stock_code
    
            # 必要なカラムのみを選択
            df = df[['Date', 'Stock_Code', 'Open', 'High', 'Low', 'Close', 'Adj_Close', 'Volume']]
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            # データを結合
            combined_df = pd.concat([combined_df, df], ignore_index=True)
        
        # Yahoo Finance APIの制限を避けるために1秒スリープ
        time.sleep(1)
    
    progress_bar.close()

    if not combined_df.empty:
        # すべての銘柄データを一度にまとめてParquetファイルとして保存
        local_file_name = f"combined_stock_data.parquet"
        local_file_path = f"./output/{local_file_name}"
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
        
        # Parquet形式で保存
        combined_df.to_parquet(local_file_path, engine='pyarrow', index=False)
        
        # GCSへのアップロード
        gcs_bq.upload_to_gcs(local_file_path, combined_file_name)
        
        # BigQueryへのデータロード
        source_uri = f"gs://{BUCKET_NAME}/{combined_file_name}"
        gcs_bq.load_data_to_bigquery(source_uri)
    else:
        tqdm.write("combined_dfが空です。処理をスキップします。")

if __name__ == "__main__":
    main()
