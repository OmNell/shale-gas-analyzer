"""One-command launcher for the shale gas analyzer project."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


SUPPORTED_PYTHON = (3, 10), (3, 14)
PROJECT_FOLDER = "shale_gas_analyzer"
RAG_STARTUP_MODES = {"run", "hierarchical"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the shale gas analyzer project.")
    parser.add_argument(
        "mode",
        nargs="?",
        default="web",
        choices=[
            "run",
            "hierarchical",
            "train",
            "replay",
            "test",
            "rag-update",
            "rag-status",
            "rag-rebuild",
            "web",
        ],
        help="Run mode. Defaults to web.",
    )
    parser.add_argument("well_name", nargs="?", default="", help="Optional well name, for example X2.")
    parser.add_argument("--iterations", type=int, default=1, help="Iterations for train/test modes.")
    parser.add_argument("--output", default="training_results.pkl", help="Training output file.")
    parser.add_argument("--task-id", default="", help="Task id for replay mode.")
    parser.add_argument("--eval-llm", default="openai/glm-4.7", help="Evaluation LLM for test mode.")
    parser.add_argument("--skip-install", action="store_true", help="Skip dependency installation.")
    parser.add_argument("--skip-rag", action="store_true", help="Do not update the RAG knowledge base before analysis.")
    parser.add_argument("--rag-rebuild", action="store_true", help="Fully rebuild the RAG index before analysis.")
    parser.add_argument("--no-venv", action="store_true", help="Use the current Python instead of .venv.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for web mode.")
    parser.add_argument("--port", type=int, default=8765, help="Port for web mode.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser in web mode.")
    return parser.parse_args()


def check_python_version() -> None:
    lower, upper = SUPPORTED_PYTHON
    if not (lower <= sys.version_info[:2] < upper):
        version = ".".join(map(str, sys.version_info[:3]))
        raise SystemExit(f"Python {version} is not supported. Use Python >=3.10,<3.14.")


def project_dir() -> Path:
    root = Path(__file__).resolve().parent
    nested = root / PROJECT_FOLDER

    if (nested / "pyproject.toml").exists():
        return nested
    if (root / "pyproject.toml").exists():
        return root

    raise SystemExit("Cannot find pyproject.toml. Put start_project.py next to the project folder.")


def venv_python(project: Path) -> Path:
    if os.name == "nt":
        return project / ".venv" / "Scripts" / "python.exe"
    return project / ".venv" / "bin" / "python"


def run_command(command: list[str], cwd: Path) -> None:
    print("Running:", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def run_command_result(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print("Running:", " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace")


def ensure_venv(project: Path, use_venv: bool) -> Path:
    if not use_venv:
        return Path(sys.executable)

    python_path = venv_python(project)
    if python_path.exists():
        return python_path

    print("Creating virtual environment: .venv", flush=True)
    run_command([sys.executable, "-m", "venv", ".venv"], cwd=project)

    if not python_path.exists():
        raise SystemExit("Virtual environment was created, but its Python executable was not found.")
    return python_path


def ensure_env_file(project: Path) -> None:
    env_path = project / ".env"
    example_path = project / ".env.example"

    if not env_path.exists():
        if example_path.exists():
            shutil.copyfile(example_path, env_path)
            print(".env was created from .env.example. Fill in OPENAI_API_KEY before real analysis.")
        else:
            print("Warning: .env was not found, and .env.example is missing.")
            return

    env_text = env_path.read_text(encoding="utf-8", errors="replace")
    if "your_openai_api_key_here" in env_text or "OPENAI_API_KEY=" not in env_text:
        print("Warning: OPENAI_API_KEY in .env looks empty or still uses the placeholder.")


def read_env_value(project: Path, name: str, default: str = "") -> str:
    env_path = project / ".env"
    if not env_path.exists():
        return os.getenv(name, default)

    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return os.getenv(name, default)


def install_project(python_path: Path, project: Path, skip_install: bool) -> None:
    if skip_install:
        return

    print("Installing/updating project dependencies...", flush=True)
    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip"], cwd=project)
    run_command([str(python_path), "-m", "pip", "install", "-e", "."], cwd=project)


def prepare_rag_index(python_path: Path, project: Path, args: argparse.Namespace) -> None:
    if args.mode not in RAG_STARTUP_MODES or args.skip_rag:
        return

    rag_enabled = read_env_value(project, "RAG_ENABLED", "true").strip().lower()
    if rag_enabled in {"0", "false", "no", "off"}:
        print("RAG is disabled by RAG_ENABLED, skipping knowledge base update.", flush=True)
        return

    mode = "rebuild" if args.rag_rebuild else "update"
    print(f"Preparing RAG knowledge base: {mode}", flush=True)
    run_command([str(python_path), "-m", "shale_gas_analyzer.rag.build_index", "--mode", mode], cwd=project)
    if not _rag_health_ok(python_path, project):
        print("RAG health check failed. Rebuilding the vector index...", flush=True)
        run_command([str(python_path), "-m", "shale_gas_analyzer.rag.build_index", "--mode", "rebuild"], cwd=project)
        if not _rag_health_ok(python_path, project):
            raise SystemExit("RAG health check still failed after rebuild.")


def _rag_health_ok(python_path: Path, project: Path) -> bool:
    health_code = (
        "from shale_gas_analyzer.rag.retriever import retrieve_knowledge; "
        "results = retrieve_knowledge('shale gas production decline', top_k=1); "
        "print(f'RAG health results={len(results)}')"
    )
    result = run_command_result(
        [str(python_path), "-c", health_code],
        cwd=project,
    )
    if result.returncode == 0:
        print("RAG health check passed.", flush=True)
        return True
    print("RAG health check output:", flush=True)
    if result.stdout:
        print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, flush=True)
    return False


def build_run_args(args: argparse.Namespace) -> list[str]:
    if args.mode == "run":
        command = ["-m", "shale_gas_analyzer.main"]
        if args.well_name:
            command.append(args.well_name)
        return command

    if args.mode == "hierarchical":
        command = ["-m", "shale_gas_analyzer.main", "hierarchical"]
        if args.well_name:
            command.append(args.well_name)
        return command

    if args.mode == "train":
        return ["-m", "shale_gas_analyzer.main", "train", str(args.iterations), args.output]

    if args.mode == "replay":
        if not args.task_id:
            raise SystemExit("Replay mode requires --task-id <task_id>.")
        return ["-m", "shale_gas_analyzer.main", "replay", args.task_id]

    if args.mode == "test":
        return ["-m", "shale_gas_analyzer.main", "test", str(args.iterations), args.eval_llm]

    rag_modes = {
        "rag-update": "update",
        "rag-status": "status",
        "rag-rebuild": "rebuild",
    }
    return ["-m", "shale_gas_analyzer.rag.build_index", "--mode", rag_modes[args.mode]]


def main() -> None:
    check_python_version()
    args = parse_args()
    project = project_dir()

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    print(f"Project directory: {project}", flush=True)
    python_path = ensure_venv(project, use_venv=not args.no_venv)
    install_project(python_path, project, skip_install=args.skip_install)
    ensure_env_file(project)

    if args.mode == "web":
        from agent_console import run_server

        run_server(python_path=python_path, host=args.host, port=args.port, open_browser=not args.no_browser)
        return

    prepare_rag_index(python_path, project, args)

    command = [str(python_path), *build_run_args(args)]
    run_command(command, cwd=project)


if __name__ == "__main__":
    main()
