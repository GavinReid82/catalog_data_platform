#!/usr/bin/env bash
input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name')
file=$(echo "$input" | jq -r '.tool_input.file_path // ""')

if [[ "$tool" != "Edit" && "$tool" != "Write" ]]; then exit 0; fi
if [[ "$file" != *.py ]]; then exit 0; fi

project_root="/Users/gavin.reid/gavin/catalog_data_platform"
"$project_root/.venv/bin/python" -m py_compile "$file" 2>&1
exit $?
