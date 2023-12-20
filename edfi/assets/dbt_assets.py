import os
from pathlib import Path

from dagster import AssetExecutionContext
from dagster_dbt import DbtCliResource, dbt_assets

dbt_manifest_path = os.getenv("DBT_PROFILES_DIR")+"/target/manifest.json"

@dbt_assets(manifest=Path("target", dbt_manifest_path))
def edfi_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    dbt_run_invocation = dbt.cli(["run"], context=context)

    yield from dbt_run_invocation.stream()

    # Retrieve the `run_results.json` dbt artifact as a dictionary:
    run_results_json = dbt_run_invocation.get_artifact("run_results.json")

    # Retrieve the `run_results.json` dbt artifact as a file path:
    run_results_path = dbt_run_invocation.target_path.joinpath("run_results.json")

