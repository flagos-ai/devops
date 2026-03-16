# Post Pytest Report Action

A reusable GitHub Action that uploads a pytest JSON report to a backend HTTP service via multipart form POST.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `backend_url` | **yes** | — | Full URL of the backend metrics endpoint |
| `report_path` | **yes** | — | Path to the pytest JSON report file |
| `api_token` | no | `""` | Bearer token for authentication |
| `file_format` | no | `json` | File format identifier |
| `file_type` | no | `pytest` | File type identifier |
| `is_zipped` | no | `false` | Whether the file is zipped |
| `git_project_name` | no | `${{ github.repository }}` | Project name |
| `workflow_name` | no | `${{ github.workflow }}` | Workflow name |
| `job_name` | no | `${{ github.job }}` | Job name |
| `pr_id` | no | auto-detected | PR number (auto-detected from PR events, defaults to `0` for push events) |
| `fail_on_error` | no | `true` | Whether to fail the step on upload error |

## Outputs

| Output | Description |
|---|---|
| `status` | HTTP status code from the upload request |

## Usage

### Basic (in a pytest workflow)

```yaml
steps:
  - name: Run pytest
    id: pytest
    run: |
      pytest --json-report --json-report-file=benchmark_metrics.json

  - name: Upload pytest report
    if: steps.pytest.outcome == 'success'
    uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
    with:
      backend_url: 'http://10.1.4.167:30180/flagcicd-backend/metrics/'
      report_path: 'benchmark_metrics.json'
```

`workflow_name`, `job_name`, `pr_id`, and `git_project_name` are auto-detected from the GitHub context.

### With authentication and custom settings

```yaml
  - uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
    with:
      backend_url: 'http://10.1.4.167:30180/flagcicd-backend/metrics/'
      report_path: 'benchmark_metrics.json'
      is_zipped: 'true'
      api_token: ${{ secrets.BACKEND_TOKEN }}
      job_name: 'pytest_unit_tests'
      fail_on_error: 'false'
```

### Non-PR context (push to main)

When running outside a PR context, `pr_id` defaults to `0`:

```yaml
  - uses: flagos-ai/FlagOps/actions/post-benchmark-report@main
    with:
      backend_url: 'http://10.1.4.167:30180/flagcicd-backend/metrics/'
      report_path: 'benchmark_metrics.json'
      pr_id: '0'  # optional explicit override
```

## Behavior

- **Auto-detection**: `git_project_name`, `workflow_name`, `job_name`, and `pr_id` are auto-populated from GitHub context variables. Any of them can be overridden by setting the input explicitly.
- **pr_id fallback**: If no PR context is available and `pr_id` is not set, it defaults to `0`.
- **Error handling**: Controlled by `fail_on_error`. When `true` (default), a failed upload or missing report file fails the workflow step. When `false`, a warning is logged and the step succeeds.
