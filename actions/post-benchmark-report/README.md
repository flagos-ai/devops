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
         {"field":"value","name":"Value","required":true,"sortable":true,"type":"number"}]
```

`repository_name`, `workflow_id`, `commit_id`, and `run_id` are auto-detected from the GitHub context.

### With authentication and query options

```yaml
  - uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
    with:
      backend_url: 'http://10.1.4.167:30180'
      report_path: 'benchmark_metrics.json'
      list_code: 'perf-test'
      header_config: '[{"field":"metric","name":"Metric","required":true,"sortable":true,"type":"string"}]'
      api_token: ${{ secrets.BACKEND_TOKEN }}
      page_size: '20'
      sort: 'updated_at'
      order: 'asc'
      fail_on_error: 'false'
```

## Report File Format

The benchmark JSON report file should have the following structure:

```json
{
  "metric_name": {
    "values": [1.23, 4.56, 7.89]
  },
  "another_metric": {
    "values": [10, 20, 30]
  }
}
```

Each key is a metric name, and its `values` array contains the data points. The action transforms this into the upload payload automatically.

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
    "name": "用户名",
    "required": true,
    "sortable": true,
    "type": "string"
  }
]
```

## Behavior

1. **Resolve inputs**: Defaults are populated from GitHub context (`github.repository`, `github.run_id`, `github.sha`). `run_id` also defaults to `github.run_id`. If `list_name` is empty, it defaults to `list_code`.
2. **Post header config**: Sends the header configuration to `{backend_url}/flagcicd-backend/list/header`. If the list code already exists, the step is treated as a no-op.
3. **Upload data**: Reads the report file, transforms it into items, and POSTs to `{backend_url}/flagcicd-backend/list/data/{list_code}`.
4. **Query data**: After a successful upload, queries the list data with pagination and sorting from `{backend_url}/flagcicd-backend/list/data/{list_code}`.
5. **Error handling**: Controlled by `fail_on_error`. When `true` (default), a failed request or missing report file fails the workflow step. When `false`, a warning is logged and the step succeeds.
