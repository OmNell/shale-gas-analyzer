# Changelog

All notable changes to this project are tracked here.

## [0.1.0] - 2026-06-02

### Added

- Initial CrewAI shale gas production analysis workflow.
- Stable sequential production pipeline.
- Hierarchical manager pipeline option.
- CSV data loading and decline metric calculation tools.
- Generated production report output.
- Public `.env.example` configuration template.
- Git ignore rules that keep `.env`, logs, caches, and build artifacts out of Git.

### Usage

Install locally:

```powershell
pip install -e .
```

Run the stable pipeline:

```powershell
python -m shale_gas_analyzer.main
```

Run for a specific well:

```powershell
python -m shale_gas_analyzer.main X2
```

