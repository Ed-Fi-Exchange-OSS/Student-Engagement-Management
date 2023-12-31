import csv
import json
import uuid
import os

from dagster import get_dagster_logger
from dagster import resource, ConfigurableResource, Config, InitResourceContext
from google.cloud import exceptions, storage
import pandas as pd

class GcsConfig(Config):
    staging_gcs_bucket: str = os.getenv("GCS_BUCKET_DEV")
    
class GcsClient:
    """Class for loading data into GCS"""

    def __init__(self, staging_gcs_bucket):
        self.staging_gcs_bucket = staging_gcs_bucket
        self.log = get_dagster_logger()

    def delete_files(self, gcs_path):
        """
        Delete all files in passed in bucket folder
        """
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.staging_gcs_bucket)
        blobs = list(bucket.list_blobs(prefix=gcs_path))
        for blob in blobs:
            blob.delete()

        self.log.info(f"Deleted {len(blobs)} files from {gcs_path}")

    def upload_df(self, folder_name: str, file_name: str, df: pd.DataFrame) -> str:
        """
        Upload dataframe to GCS as CSV
        and return GCS folder path.
        """
        try:
            storage_client = storage.Client()
            bucket = storage_client.get_bucket(self.staging_gcs_bucket)
        except exceptions.NotFound:
            self.log.error("Sorry, that bucket does not exist!")
            raise

        self.log.debug(
            f"Uploading {file_name} to gs://{self.staging_gcs_bucket}/{folder_name}"
        )

        bucket.blob(f"{folder_name}/{file_name}").upload_from_string(
            df.to_csv(index=False, quoting=csv.QUOTE_ALL),
            content_type="text/csv",
            num_retries=3,
        )

        return f"gs://{self.staging_gcs_bucket}/{folder_name}/{file_name}"

    def upload_json(self, path, records) -> str:
        """
        Upload list of dictionaries to gcs
        as a JSON file.
        """
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.staging_gcs_bucket)

        output = ""
        for record in records:
            output = output + json.dumps(record) + "\r\n"

        bucket.blob(path).upload_from_string(
            output, content_type="application/json", num_retries=3
        )
        gcs_upload_path = f"gs://{self.staging_gcs_bucket}/{path}"
        self.log.debug(f"Uploaded JSON file to {gcs_upload_path}")

        return gcs_upload_path


# https://docs.dagster.io/guides/dagster/migrating-to-pythonic-resources-and-config#migrating-resources-that-use-separate-objects-for-business-logic
# https://docs.dagster.io/_apidocs/resources#dagster.ConfigurableResource
class GcsResource(ConfigurableResource):
    staging_gcs_bucket: str

    def init_gcs_resource(self) -> GcsClient:
        return GcsClient(self.staging_gcs_bucket)