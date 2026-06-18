from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Literal
import typer
from rich import print
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset, save_jsonl
app = typer.Typer(add_completion=False)

@app.command()
def main(
    dataset: str = "data/hotpot_golden.json",
    out_dir: str = "outputs/golden_run",
    mode: Literal["mock", "llm"] = "mock",
    reflexion_attempts: int = 3,
    usd_per_million_tokens: float = 0.0,
    offset: int = 0,
    limit: int | None = None,
) -> None:
    examples = load_dataset(dataset, offset=offset, limit=limit)
    match mode:
        case "mock":
            from src.reflexion_lab import mock_runtime as runtime
        case "llm":
            from src.reflexion_lab import llm_runtime as runtime

    react = ReActAgent(runtime)
    reflexion = ReflexionAgent(runtime, max_attempts=reflexion_attempts)
    react_started = time.perf_counter()
    react_records = [react.run(example) for example in examples]
    react_seconds = time.perf_counter() - react_started
    reflexion_started = time.perf_counter()
    reflexion_records = [reflexion.run(example) for example in examples]
    reflexion_seconds = time.perf_counter() - reflexion_started
    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    report = build_report(
        all_records,
        dataset_name=Path(dataset).name,
        mode=mode,
        running_time_seconds={
            "react": react_seconds,
            "reflexion": reflexion_seconds,
        },
        usd_per_million_tokens=usd_per_million_tokens,
    )
    json_path, md_path = save_report(report, out_path)
    print(f"[green]Saved[/green] {json_path}")
    print(f"[green]Saved[/green] {md_path}")
    print(json.dumps(report.summary, indent=2))

if __name__ == "__main__":
    app()
