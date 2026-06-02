"""Main entrypoint for the shale gas analyzer crew."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from shale_gas_analyzer.crew import ShaleGasAnalyzerCrew

load_dotenv()

COMMANDS = {"run", "hierarchical", "train", "replay", "test"}


def _args() -> list[str]:
    args = sys.argv[1:]
    if args and args[0] in COMMANDS:
        return args[1:]
    return args


def _inputs() -> dict[str, str]:
    args = _args()
    well_name = args[0] if args and not args[0].isdigit() else os.getenv("WELL_NAME", "AUTO")
    return {"well_name": well_name}


def run() -> None:
    """Run the stable production pipeline."""
    ShaleGasAnalyzerCrew().stable_crew().kickoff(inputs=_inputs())


def hierarchical() -> None:
    """Run the full hierarchical manager pipeline."""
    ShaleGasAnalyzerCrew().crew().kickoff(inputs=_inputs())


def train() -> None:
    """Train the crew for the requested number of iterations."""
    args = _args()
    inputs = {"well_name": os.getenv("WELL_NAME", "AUTO")}
    try:
        n_iterations = int(args[0])
    except (IndexError, ValueError):
        n_iterations = 1

    filename = args[1] if len(args) > 1 else "training_results.pkl"
    ShaleGasAnalyzerCrew().crew().train(n_iterations=n_iterations, filename=filename, inputs=inputs)


def replay() -> None:
    """Replay the crew execution from a specific task id."""
    args = _args()
    if not args:
        raise ValueError("Please provide task_id, for example: python -m shale_gas_analyzer.main replay <task_id>")
    ShaleGasAnalyzerCrew().crew().replay(task_id=args[0])


def test() -> None:
    """Run quality test evaluation for the crew."""
    args = _args()
    inputs = {"well_name": os.getenv("WELL_NAME", "AUTO")}
    try:
        n_iterations = int(args[0])
    except (IndexError, ValueError):
        n_iterations = 1

    eval_llm = args[1] if len(args) > 1 else "openai/glm-4.7"
    ShaleGasAnalyzerCrew().crew().test(n_iterations=n_iterations, eval_llm=eval_llm, inputs=inputs)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in COMMANDS else "run"
    if command == "hierarchical":
        hierarchical()
    elif command == "train":
        train()
    elif command == "replay":
        replay()
    elif command == "test":
        test()
    else:
        run()
