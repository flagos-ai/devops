# Post Benchmark Report Action

A reusable GitHub Action that uploads benchmark data to a backend service, configures list headers, and queries list data with pagination and sorting.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `backend_url` | **yes** | — | Backend base URL (e.g. `http://host:port`) |
| `report_path` | **yes** | — | Path to the benchmark JSON report file |
| `api_token` | no | `""` | Bearer token for authentication |
| `list_code` | **yes** | — | List code identifier |
| `list_name` | no | `list_code` value | List display name (defaults to `list_code` if empty) |
| `header_config` | **yes** | — | JSON array of header config for custom table columns |
| `repository_name` | no | `${{ github.repository }}` | Repository name |
| `workflow_id` | no | `${{ github.run_id }}` | Workflow run ID |
| `commit_id` | no | `${{ github.sha }}` | GitHub commit SHA |
| `run_id` | no | `${{ github.run_id }}` | GitHub Actions run ID |
| `page_size` | no | `10` | Number of items per page for query |
| `page` | no | `1` | Page number for query |
| `sort` | no | `created_at` | Sort field for query |
| `order` | no | `desc` | Sort direction (`asc` or `desc`) |
| `fail_on_error` | no | `true` | Whether to fail the step on error |

## Outputs

| Output | Description |
|---|---|
| `header_status` | HTTP status code from the header config request |
| `upload_status` | HTTP status code from the data upload request |
| `query_status` | HTTP status code from the data query request |
| `query_result` | JSON response from the data query request |

## Usage

### Basic (in a benchmark workflow)

```yaml
steps:
  - name: Run benchmark
    id: benchmark
    run: |
      python run_benchmark.py --output benchmark_metrics.json

  - name: Upload benchmark report
    if: steps.benchmark.outcome == 'success'
    uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
    with:
      backend_url: 'http://10.1.4.167:30180'
      report_path: 'benchmark_metrics.json'
      list_code: 'benchmark-list'
      list_name: 'Benchmark Results'
      header_config: |
        [{"field":"metric","name":"Metric","required":true,"sortable":true,"type":"string"},
         {"field":"p50","name":"P50","required":true,"sortable":true,"type":"number"},
         {"field":"p99","name":"P99","required":true,"sortable":true,"type":"number"},
         {"field":"mean","name":"Mean","required":true,"sortable":true,"type":"number"}]
```

`repository_name`, `workflow_id`, `commit_id`, and `run_id` are auto-detected from the GitHub context.

### With authentication and query options

```yaml
  - uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
    with:
      backend_url: 'http://10.1.4.167:30180'
      report_path: 'benchmark_metrics.json'
      list_code: 'perf-test'
      header_config: |
        [{"field":"metric","name":"Metric","required":true,"sortable":true,"type":"string"},
         {"field":"p50","name":"P50","required":true,"sortable":true,"type":"number"},
         {"field":"p99","name":"P99","required":true,"sortable":true,"type":"number"},
         {"field":"mean","name":"Mean","required":true,"sortable":true,"type":"number"}]
      api_token: ${{ secrets.BACKEND_TOKEN }}
      page_size: '20'
      sort: 'updated_at'
      order: 'asc'
      fail_on_error: 'false'
```

## Report File Format

The benchmark JSON report file must be a key-value object where each key is a metric name and each value is an **object** with named sub-fields. The sub-field names must match the `field` values in `header_config` (excluding the first entry which maps to the metric key).

### Example

```json
{
  "latency": {"p50": 1.2, "p99": 3.4, "mean": 2.0},
  "throughput": {"p50": 100, "p99": 80, "mean": 95}
}
```

With `header_config`:

```json
[
  {"field": "metric", "name": "Metric", "type": "string", ...},
  {"field": "p50",    "name": "P50",    "type": "number", ...},
  {"field": "p99",    "name": "P99",    "type": "number", ...},
  {"field": "mean",   "name": "Mean",   "type": "number", ...}
]
```

Transformed payload:

```json
{
  "items": [
    {"metric": "latency", "p50": 1.2, "p99": 3.4, "mean": 2.0, "commit_id": "...", ...},
    {"metric": "throughput", "p50": 100, "p99": 80, "mean": 95, "commit_id": "...", ...}
  ]
}
```

### Validation

Before uploading, the action validates that every metric value is an object and contains all fields specified in `header_config` (from the second entry onward). If validation fails:

- When `fail_on_error` is `true` (default): the step fails with an error listing the mismatches.
- When `fail_on_error` is `false`: a warning is logged and the upload is skipped.

### Transform rules

- `header_config[0].field` → always mapped to each entry's **key** (metric name)
- `header_config[1+].field` → extracts `value[field]` from the metric's object value

## `header_config` Format

`header_config` is a JSON array describing the columns of the report list. Each item has the following fields:

| Field | Type | Description |
|---|---|---|
| `field` | string | Column field key |
| `name` | string | Column display name |
| `required` | boolean | Whether the column is required |
| `sortable` | boolean | Whether the column is sortable |
| `type` | string | Data type (`string`, `number`, etc.) |

Example:

```json
[
  {
    "field": "username",
    "name": "Username",
    "required": true,
    "sortable": true,
    "type": "string"
  }
]
```

## Behavior

1. **Resolve inputs**: Defaults are populated from GitHub context (`github.repository`, `github.run_id`, `github.sha`). `run_id` also defaults to `github.run_id`. If `list_name` is empty, it defaults to `list_code`.
2. **Post header config**: Sends the header configuration to `{backend_url}/flagcicd-backend/list/header`. If the list code already exists, the step is treated as a no-op.
3. **Validate report**: Checks that every metric value is an object containing all expected sub-fields from `header_config`. Fails or warns based on `fail_on_error`.
4. **Upload data**: Reads the report file and transforms entries using `header_config`. The first header field receives the metric key; subsequent fields extract the matching sub-field from the value object. POSTs to `{backend_url}/flagcicd-backend/list/data/{list_code}`. Each item includes `commit_id`, `repository_name`, `workflow_id`, and `run_id`.
5. **Query data**: After a successful upload, queries the list data with pagination and sorting from `{backend_url}/flagcicd-backend/list/data/{list_code}`.
6. **Error handling**: Controlled by `fail_on_error`. When `true` (default), a failed request or missing report file fails the workflow step. When `false`, a warning is logged and the step succeeds.

## Notes

1. **Report file must use object-of-objects format**: Each metric value must be an object (e.g. `{"p50": 1.2, "p99": 3.4}`). Arrays and primitive types are not supported. Validation will fail before upload if any value is not an object.

   ```jsonc
   // ✅ Correct: values are objects
   {
     "latency": {"p50": 1.2, "p99": 3.4, "mean": 2.0},
     "throughput": {"p50": 100, "p99": 80, "mean": 95}
   }

   // ❌ Wrong: value is an array
   {
     "latency": [1.2, 3.4, 2.0]
   }

   // ❌ Wrong: value is a primitive
   {
     "latency": 1.2
   }
   ```

2. **`header_config[0]` maps to the metric key**: The first entry in `header_config` does not extract a field from the report value object. Instead, it is automatically mapped to each report entry's **key** (the metric name). For example, if `header_config[0]` is `{"field": "metric", ...}`, then the key `"latency"` in `{"latency": {...}}` will be assigned to the `"metric"` field. Therefore, do **not** duplicate this field inside the report value objects.

   ```jsonc
   // header_config[0] is {"field": "metric", ...}, it automatically takes the report key

   // ✅ Correct: value does not contain the "metric" field
   {"latency": {"p50": 1.2, "p99": 3.4}}
   // Transformed → {"metric": "latency", "p50": 1.2, "p99": 3.4, ...}

   // ❌ Wrong: value redundantly includes the "metric" field
   {"latency": {"metric": "latency", "p50": 1.2, "p99": 3.4}}
   ```

3. **`header_config` fields must match report fields exactly**: Every `field` from `header_config[1]` onward must exist in each report value object. Field names are case-sensitive.

   ```jsonc
   // header_config: [{"field":"metric",...}, {"field":"p50",...}, {"field":"p99",...}]

   // ✅ Correct: value contains both p50 and p99
   {"latency": {"p50": 1.2, "p99": 3.4}}

   // ❌ Wrong: value is missing the p99 field
   {"latency": {"p50": 1.2}}

   // ❌ Wrong: field name case mismatch (P50 ≠ p50)
   {"latency": {"P50": 1.2, "P99": 3.4}}
   ```

4. **`list_code` is unique and immutable**: The first time a `list_code` is used, the header config is created. On subsequent runs with the same `list_code`, the header request is silently skipped (it will not overwrite the existing config). To change the header, use a new `list_code`.

   ```yaml
   # First run: creates the header config
   list_code: 'perf-test-v1'
   header_config: |
     [{"field":"metric","name":"Metric",...}, {"field":"p50","name":"P50",...}]

   # Subsequent runs: header already exists, automatically skipped (no error)
   list_code: 'perf-test-v1'

   # To modify the header (e.g. add a p99 column), you must use a new list_code
   list_code: 'perf-test-v2'
   header_config: |
     [{"field":"metric","name":"Metric",...}, {"field":"p50","name":"P50",...}, {"field":"p99","name":"P99",...}]
   ```

5. **Metadata fields are injected automatically**: Each uploaded item automatically includes `commit_id`, `repository_name`, `workflow_id`, and `run_id`. You do not need to define these in the report file or `header_config`.

   ```jsonc
   // The report file only needs business data:
   {"latency": {"p50": 1.2, "p99": 3.4}}

   // The action automatically expands each item to:
   {
     "metric": "latency",
     "p50": 1.2,
     "p99": 3.4,
     "commit_id": "abc123...",        // ← auto-injected
     "repository_name": "org/repo",   // ← auto-injected
     "workflow_id": "123456789",      // ← auto-injected
     "run_id": "123456789"            // ← auto-injected
   }
   ```

6. **`header_config` must be a valid JSON array**: When passing it in YAML, pay attention to proper JSON formatting and escaping. Using a `|` block scalar is recommended for readability.

   ```yaml
   # ✅ Recommended: use | block scalar for clarity
   header_config: |
     [
       {"field": "metric", "name": "Metric", "required": true, "sortable": true, "type": "string"},
       {"field": "p50", "name": "P50", "required": true, "sortable": true, "type": "number"}
     ]

   # ✅ Also valid: single-line (not recommended for long configs)
   header_config: '[{"field":"metric","name":"Metric","required":true,"sortable":true,"type":"string"}]'

   # ❌ Wrong: missing quotes and commas cause JSON parse failure
   header_config: |
     [{field: metric, name: Metric}]
   ```

7. **Temporary file side effects**: The action writes to `/tmp/header_response.txt` and `/tmp/upload_response.txt` during execution. If multiple steps in the same job use this action, later responses will overwrite earlier ones.

   ```yaml
   # To preserve each step's response, use outputs instead of /tmp files:
   - name: Upload report A
     id: report_a
     uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
     with:
       list_code: 'report-a'
       # ...

   - name: Upload report B
     id: report_b
     uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
     with:
       list_code: 'report-b'
       # ...

   # Retrieve results via outputs (do not rely on /tmp files)
   - run: |
       echo "Report A status: ${{ steps.report_a.outputs.upload_status }}"
       echo "Report B status: ${{ steps.report_b.outputs.upload_status }}"
   ```

8. **Query step only runs after a successful upload**: If the data upload fails (non-2xx HTTP status), the query step is automatically skipped.

   ```yaml
   # If upload returns 500, query_status and query_result will be empty
   - name: Check results
     run: |
       if [ -z "${{ steps.upload_step.outputs.query_result }}" ]; then
         echo "Query was skipped because upload failed"
       fi
   ```

9. **Scope of `fail_on_error`**: This parameter controls the behavior for missing files, validation failures, header request failures, and data upload failures. When set to `false`, all errors are downgraded to warnings.

   ```yaml
   # Set to false: all errors become warnings, the workflow continues
   fail_on_error: 'false'
   # Use when: report upload is optional and should not block the pipeline

   # Set to true (default): any error fails the step
   fail_on_error: 'true'
   # Use when: report upload is critical and should block the pipeline on failure
   ```
