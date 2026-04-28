#!/usr/bin/env bash
project_root="/Users/gavin.reid/gavin/catalog_data_platform"
cd "$project_root/dbt_project" || exit 1
"$project_root/.venv/bin/dbt" parse 2>&1
exit $?
