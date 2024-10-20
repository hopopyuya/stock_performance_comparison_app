from google.cloud import bigquery
from google.cloud import storage

class Gcs_client:
    def __init__(self):
        self.client = storage.Client()

    def create_bucket(self, bucket_name):
        try:
            bucket = self.client.get_bucket(bucket_name)
            print(f"Bucket {bucket_name} already exists.")
        except storage.exceptions.NotFound:
            bucket = self.client.create_bucket(bucket_name)
            print(f"Bucket {bucket_name} created.")

    def list_all_objects(self, bucket_name):
        bucket = self.client.bucket(bucket_name)
        blobs = bucket.list_blobs()
        return [blob.name for blob in blobs]

    def upload_gcs(self, bucket_name, local_file_path, destination_blob_name):
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_file_path)
        print(f"Uploaded {local_file_path} to gs://{bucket_name}/{destination_blob_name}")

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

        tqdm.write(f"Data loaded into BigQuery table {self.dataset_name}.{self.table_name} from {source_uri}.")ss

class Bigquery_client:
    def __init__(self):
        self.client = bigquery.Client()