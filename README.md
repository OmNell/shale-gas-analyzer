# Shale Gas Analyzer

CrewAI multi-agent shale gas production analysis system.

This project reads shale gas well production CSV data, calculates decline and production metrics, runs a CrewAI analysis workflow, and writes a production analysis report to `shale_gas_production_report.md`.

## Version

Current version: `0.1.0`

See `CHANGELOG.md` for release notes.

## Repository Safety

The real `.env` file is intentionally ignored by Git and must not be uploaded.

Use `.env.example` as the public configuration template. Copy it to `.env` locally, then fill in your private values:

```powershell
Copy-Item .env.example .env
```

Before pushing, you can verify that `.env` is ignored:

```powershell
git check-ignore -v .env
```

## Requirements

- Python `>=3.10,<3.14`
- An OpenAI-compatible API key and base URL
- Production data CSV files in the `data/` folder

## Installation

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project:

```powershell
pip install -e .
```

Or install dependencies only:

```powershell
pip install -r requirements.txt
```

## Configuration

Create `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
WELL_NAME=your_well_name_here
THINKING_MAX_TOKENS=4096
REGULAR_MAX_TOKENS=2048
CREW_MAX_RPM=60
AGENT_MAX_EXECUTION_TIME=300
```

## Data

Place well production CSV files in `data/`.

The data loader chooses a CSV in this order:

1. Match `well_name` to a CSV filename, case-insensitive.
2. Match `well_name` to the `Well_ID` column inside CSV files.
3. If `WELL_NAME=AUTO` and only one CSV exists, use that file.
4. If multiple CSV files exist and no exact match is found, use the newest modified CSV.

## Usage

Run the stable production pipeline:

```powershell
python -m shale_gas_analyzer.main
```

Run analysis for a specific well:

```powershell
python -m shale_gas_analyzer.main X2
```

Run the full hierarchical manager pipeline:

```powershell
python -m shale_gas_analyzer.main hierarchical X2
```

Train the crew:

```powershell
python -m shale_gas_analyzer.main train 1 training_results.pkl
```

Replay a task:

```powershell
python -m shale_gas_analyzer.main replay <task_id>
```

Run CrewAI test evaluation:

```powershell
python -m shale_gas_analyzer.main test 1 openai/glm-4.7
```

If installed with `pip install -e .`, the console command is also available:

```powershell
shale-gas-analyzer
```

## Outputs

- `shale_gas_production_report.md`: generated production analysis report
- `crew_execution.log`: runtime log, ignored by Git

## Version Management

Recommended release workflow:

```powershell
git status
git add .
git commit -m "Release v0.1.0"
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

When creating a new version:

1. Update `version` in `pyproject.toml`.
2. Add release notes to `CHANGELOG.md`.
3. Commit the changes.
4. Create a matching Git tag, for example `v0.2.0`.

