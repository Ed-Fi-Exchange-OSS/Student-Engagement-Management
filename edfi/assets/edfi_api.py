import json, os
from datetime import datetime

from typing import Union

from dagster import AssetKey, MetadataValue, Output, asset, Config, fs_io_manager, get_dagster_logger

from assets.edfi_api_endpoints import EDFI_API_ENDPOINTS

from resources.edfi_api_resource import EdFiApiClient, EdFiCurrentYearConfig, EdFiApiResource 
from resources.gcs_resource import GcsClient, GcsConfig, GcsResource
from resources.bq_resource import BigQueryClient


@asset(
    group_name="source",
    key_prefix=["staging"],
)
def change_query_versions(
    context, 
    config: EdFiCurrentYearConfig,
    edfi_api_client: EdFiApiResource,
    data_lake: GcsResource ):
    """
    Retrieve change query version from previous asset materialization
    and most recent change query version from Ed-Fi API.

    Use 0 if this is the first time the asset is being materialized.

    Use -1 and -1 if the run config is set to not use change queries.
    """
    base_url: str = config.base_url
    api_key: str = config.api_key
    api_secret: str = config.api_secret 
    api_page_limit: str = config.api_page_limit
    api_mode: str = config.api_mode 
    api_version: str = config.api_version
    use_change_queries: bool = config.use_change_queries

    edfi_api_client = edfi_api_client.init_edfi_resource()

    if not use_change_queries: 
        context.log.info("Will not use change queries")
        previous_change_version = -1
        newest_change_version = -1
    else:
        context.log.info("Using change queries")
        school_year = config.school_year
        previous_change_version = 0

        try:
            # get previous materialization events
            last_materialization = context.instance.get_latest_materialization_events(
                asset_keys=[AssetKey(("staging", "change_query_versions"))]
            )
            # iterate through metadata entries looking for previous change version number
            for metadata_entry in last_materialization[
                AssetKey(("staging", "change_query_versions"))
            ].dagster_event.event_specific_data.materialization.metadata_entries:
                if metadata_entry.label == "Newest change version":
                    # change version number found
                    previous_change_version = metadata_entry.entry_data.value
                    context.log.debug(
                        f"Setting previous change version to: {previous_change_version}"
                    )
        except:
            context.log.info("Did not find previous asset materialization")

        response = edfi_api_client.get_available_change_versions(
            school_year
        )
        context.log.debug(f"Retrieved response from change query API: {response}")

        newest_change_version = response["NewestChangeVersion"]
        context.log.debug(f"Setting newest change version to: {newest_change_version}")

    return Output(
        value={
            "previous_change_version": previous_change_version,
            "newest_change_version": newest_change_version,
        },
        metadata={
            "Previous change version": MetadataValue.int(previous_change_version),
            "Newest change version": MetadataValue.int(newest_change_version),
        },
    )


edfi_assets = list()
for edfi_asset in EDFI_API_ENDPOINTS:
    """
    Loop through each dict in EDFI_API_ENDPOINTS,
    create an asset for each dict and append to edfi_assets list

    Example value: { "asset": "base_edfi_schools", "endpoints": ["/ed-fi/schools", "/ed-fi/schools/deletes"] }
    """
    def make_func(edfi_asset):
        @asset(
            name=edfi_asset["asset"],
            group_name="source",
            key_prefix=["staging"],
        )
        def extract_and_load(
                context, 
                config: EdFiCurrentYearConfig, 
                edfi_api_client: EdFiApiResource,
                data_lake: GcsResource,
                change_query_versions,
            ):

            log = get_dagster_logger()

            school_year = config.school_year

            edfi_api_client = edfi_api_client.init_edfi_resource()

            data_lake = data_lake.init_gcs_resource()

            # change query version numbers
            previous_change_version = change_query_versions["previous_change_version"]
            newest_change_version = change_query_versions["newest_change_version"]

            # dagster run datetime. used in gcs filepath.
            stats = context.instance.event_log_storage.get_stats_for_run(context.run_id)
            launch_datetime = datetime.utcfromtimestamp(stats.launch_time)

            number_of_changed_records = 0
            changed_records_gcs_paths = []
            number_of_deleted_records = 0
            deleted_records_gcs_paths = []
            for endpoint in edfi_asset["endpoints"]:

                if (
                    previous_change_version == -1
                    and newest_change_version == -1
                    and "/deletes" in endpoint
                ):
                    # skip api endpoint if run config set to not use
                    # change queries and if endpoint is a deletes endpoint
                    context.log.info(f"Skipping the endpoint {endpoint}")
                    continue

                file_number = 1
                # process yielded records from generator
                for yielded_response in edfi_api_client.get_data(
                    api_endpoint=endpoint,
                    school_year=school_year,
                    previous_change_version=previous_change_version,
                    newest_change_version=newest_change_version,
                ):

                    records_to_upload = []
                    extract_type = "deletes" if "/deletes" in endpoint else "records"

                    # iterate through each record in page of api results
                    for response in yielded_response:
                        if "/deletes" in endpoint:
                            id = response["Id"].replace("-", "")
                            number_of_deleted_records += 1
                        else:
                            id = response["id"].replace("-", "")
                            number_of_changed_records += 1

                        records_to_upload.append(
                            {
                                "is_complete_extract": True
                                if previous_change_version == -1
                                else False,
                                "id": id,
                                "data": json.dumps(response),
                            }
                        )

                    # upload current set of records from generator
                    path = data_lake.upload_json(
                        path=(
                            f"edfi_api/{edfi_asset['asset']}/api_version={edfi_api_client.api_version}/"
                            f"school_year={school_year}/"
                            f"date_extracted={launch_datetime}/extract_type={extract_type}/"
                            f"{abs(hash(endpoint))}-{file_number:09}.json"
                        ),
                        records=records_to_upload if records_to_upload else [{}],
                    )
                    if "/deletes" in endpoint:
                        deleted_records_gcs_paths.append(path)
                    else:
                        changed_records_gcs_paths.append(path)
                    file_number += 1
                    context.log.debug(f"Uploaded records to: {path}")

            return Output(
                value="Task successful",
                metadata={
                    "Changed records": MetadataValue.int(number_of_changed_records),
                    "Deleted records": MetadataValue.int(number_of_deleted_records),
                    "Changed records GCS paths": MetadataValue.text(
                        ", ".join(changed_records_gcs_paths)
                    ),
                    "Deleted records GCS paths": MetadataValue.text(
                        ", ".join(deleted_records_gcs_paths)
                    ),
                },
            )

        return extract_and_load

    edfi_assets.append(make_func(edfi_asset))
