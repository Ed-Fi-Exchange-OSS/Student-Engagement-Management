import os

from dagster import (
    AssetSelection,
    define_asset_job,
    DefaultScheduleStatus,
    Definitions,
    EnvVar,
    fs_io_manager,
    make_values_resource,
    multiprocess_executor,
    repository,
    ScheduleDefinition,
    with_resources,
)
from dagster_dbt import load_assets_from_dbt_project, DbtCliResource
from dagster_gcp.gcs.resources import gcs_resource

from assets.edfi_api import change_query_versions, edfi_assets
from assets.dbt_assets import edfi_dbt_assets

from resources.edfi_api_resource import EdFiApiClient, EdFiApiResource
from resources.gcs_resource import GcsClient, GcsResource
from resources.bq_resource import BigQueryClient

# dbt_refresh_job = define_asset_job(
#     name="dbt_refresh_job", 
#     selection=AssetSelection.groups("edfi_staging") | AssetSelection.groups("edfi_amt"), 
#     tags={"dagster/max_retries": 3}
# )

edfi_api_refresh_job = define_asset_job(
    name=f"edfi_api_job_{os.getenv('CURRENT_SCHOOL_YEAR')}", 
    selection=AssetSelection.groups("source") | AssetSelection.groups("edfi_staging") | AssetSelection.groups("edfi_amt"), 
    tags={"dagster/max_retries": 3}
)

edfi_full_refresh_schedule = ScheduleDefinition(
    name="edfi_full_refresh",
    job=edfi_api_refresh_job,
    cron_schedule="0 6 * * 6",
    run_config={
        "ops": {
            "staging__change_query_versions": {"config": {"use_change_queries": False}}
        }
    },
    default_status=DefaultScheduleStatus.RUNNING,
)

edfi_delta_refresh_schedule = ScheduleDefinition(
    name="edfi_delta_refresh",
    job=edfi_api_refresh_job,
    cron_schedule="0 6 * * 7,1-5",
    run_config={
        "ops": {
            "staging__change_query_versions": {"config": {"use_change_queries": True}}
        }
    },
    default_status=DefaultScheduleStatus.RUNNING,
)


EdFi_Current_School_Year = Definitions(
    assets=[change_query_versions] + edfi_assets + [edfi_dbt_assets],
    jobs=[edfi_api_refresh_job], # + [dbt_refresh_job],
    schedules=[edfi_full_refresh_schedule] + [edfi_delta_refresh_schedule],
    resources= {
        "gcs": gcs_resource,
        "io_manager": fs_io_manager,
        "data_lake": GcsResource(
            staging_gcs_bucket = EnvVar("GCS_BUCKET_PROD")
        ),
        "dbt": DbtCliResource(
            project_dir = os.getenv("DBT_PROJECT_DIR"),
            profiles_dir = os.getenv("DBT_PROFILES_DIR"),
            target = "prod",
        ),
        "edfi_api_client": EdFiApiResource(
            base_url = os.getenv("EDFI_BASE_URL"),
            api_key = os.getenv("EDFI_API_KEY"),
            api_secret = os.getenv("EDFI_API_SECRET"),
            api_page_limit = 2500,
            api_mode = "YearSpecific", # DistrictSpecific, SharedInstance, YearSpecific
            api_version = "5.3",
        ),
        "globals": make_values_resource(school_year=int).configured(
            {
                "school_year": int(os.getenv("CURRENT_SCHOOL_YEAR"))
            }
        ),
    },
)
