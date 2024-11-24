import os
import time
import requests
import pandas as pd
import yfinance as yf
from google.cloud import bigquery
from google.cloud import storage
import datetime as dt
from tqdm import tqdm
from google.oauth2 import service_account

class GCSBigQueryFacade:
    def __init__(self, project_id, dataset_name, table_name, bucket_name):
        self.project_id = project_id
        self.dataset_name = dataset_name
        self.table_name = table_name
        self.bucket_name = bucket_name

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
    
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    DATASET_NAME = 'stock_dataset'
    BUCKET_NAME = 'stock-data-bucket_hopop'
    TABLE_NAME = 'stock_data'
    gcs_bq = GCSBigQueryFacade(PROJECT_ID, DATASET_NAME, TABLE_NAME, BUCKET_NAME)
    
    max_date = gcs_bq.get_max_date_from_bq()
    max_date = pd.to_datetime(max_date).date()
    START_DATE = max_date + dt.timedelta(days=1)
    END_DATE = dt.date.today()
    
    if START_DATE >= END_DATE:
        tqdm.write("最新データが既に存在します。新しいデータはありません。")
        return
    
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    r = requests.get(url)
    with open('data_j.xls', 'wb') as output:
        output.write(r.content)
    stocklist = pd.read_excel("./data_j.xls")
    stocklist = stocklist[stocklist["市場・商品区分"].isin(["プライム（内国株式）", "グロース（内国株式）", "スタンダード（内国株式）"])]
    stock_names_df = stocklist[['コード', '銘柄名']]
    print(f'{START_DATE} ~ {END_DATE}')
    
    
    combined_df = pd.DataFrame()
    # tqdmを使用して進捗を可視化（バーを最上部に固定）
    progress_bar = tqdm(stock_names_df.iterrows(), total=len(stock_names_df), ncols=100, leave=True, position=0)
    
    for index, row in progress_bar:
        stock_code = str(row['コード']).strip()
        ticker = f"{stock_code}.T"
        
        df = yf.download(ticker, start=START_DATE, end=END_DATE)
    
        if df.empty:
            tqdm.write(f"No data found for {ticker}. Skipping...")
        else:
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
    
            df = df[['Date', 'Stock_Code', 'Open', 'High', 'Low', 'Close', 'Adj_Close', 'Volume']]
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            combined_df = pd.concat([combined_df, df], ignore_index=True)
        
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