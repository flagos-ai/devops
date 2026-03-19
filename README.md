# FlagOS DevOps Central

This repository is the single source of truth for CI/CD logic across the **FlagOS AI** organization. It contains unified GitHub Actions (individual steps) and Reusable Workflows (entire pipelines) to ensure consistency, security, and speed across all our projects.

## 📁 Repository Structure

```text
flagos-ai/FlagOps/
├── .github/
│   └── workflows/                  # Reusable Workflows & CI tests
│       ├── ci-shared.yml
│       ├── test-post-pytest-report.yml
│       └── test-post-benchmark-report.yml
├── actions/                        # Custom Actions (The "Individual Steps")
│   ├── setup-poetry/
│   │   └── action.yml
│   ├── notify-slack/
│   │   └── action.yml
│   ├── post-pytest-report/         # Upload pytest JSON reports
│   │   ├── action.yml
│   │   └── README.md
│   └── post-benchmark-report/      # Upload benchmark data with custom columns
│       ├── action.yml
│       └── README.md
└── README.md

```

---

## 🚀 How to use Shared Workflows

Reusable workflows allow you to standardize entire CI pipelines (e.g., testing, linting, and deploying) with just a few lines of code.

### Usage Example

In your application repository (e.g., `flagos-ai/model-api`), create a file at `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  run-standard-ci:
    uses: flagos-ai/FlagOps/.github/workflows/ci-python.yml@main
    with:
      python-version: "3.11"
    secrets:
      HF_TOKEN: ${{ secrets.HF_TOKEN }}

```

---

## 🛠 How to use Shared Actions

Custom actions are discrete tasks used within your own existing jobs.

### Usage Example

In any workflow file within the organization:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # Using a shared action from this repo
      - name: Setup Environment
        uses: flagos-ai/FlagOps/actions/setup-poetry@main
        with:
          install-dev-deps: "true"

```

### Available Actions

| Action | Description |
|---|---|
| [`setup-poetry`](actions/setup-poetry/) | Set up Poetry environment |
| [`notify-slack`](actions/notify-slack/) | Send Slack notifications |
| [`post-pytest-report`](actions/post-pytest-report/) | Upload pytest JSON reports to backend |
| [`post-benchmark-report`](actions/post-benchmark-report/) | Upload benchmark data with custom table columns |

---

## 📌 Best Practices

### 1. Versioning

For production-critical repositories, avoid using `@main`. Instead, reference a specific version tag or commit SHA to prevent breaking changes:

* `uses: flagos-ai/FlagOps/.github/workflows/ci-python.yml@v1.0.0`
* `uses: flagos-ai/FlagOps/actions/setup-poetry@v1.2.3`

### 2. Contributions

1. Create a new branch for your changes.
2. Add your action or workflow following the folder structure above.
3. Document any required `inputs` or `secrets` in the local `action.yml` or workflow file.
4. Open a Pull Request for the DevOps team to review.

---

## 📞 Support

For questions regarding CI/CD standards or help with these actions, please contact the Infrastructure team or open an issue in this repository.
