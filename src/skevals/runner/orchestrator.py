"""Orchestrator: coordinates A/B scenario execution."""

import json
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from skevals.config import EvalMode
from skevals.models.scenario import ScenarioSet
from skevals.models.session import SessionResult
from skevals.runner.executor import run_session
from skevals.runner.workspace import create_workspace

console = Console()


def run_all_scenarios(
    scenario_set: ScenarioSet,
    skill_path: Path,
    output_dir: Path,
    model: str = "sonnet",
    budget: float = 0.50,
    timeout: int = 300,
    mode: EvalMode = EvalMode.lite,
) -> list[tuple[SessionResult, SessionResult]]:
    """Run all scenarios, each in control + treatment. Returns pairs."""
    results_dir = output_dir / "sessions"
    results_dir.mkdir(parents=True, exist_ok=True)

    pairs: list[tuple[SessionResult, SessionResult]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running scenarios...", total=len(scenario_set.scenarios))

        for scenario in scenario_set.scenarios:
            progress.update(task, description=f"Scenario {scenario.id}...")

            # Create workspaces
            ctrl_ws, _ = create_workspace(scenario, "control", output_dir)
            treat_ws, plugin_dir = create_workspace(scenario, "treatment", output_dir, skill_path)

            # Run control
            progress.update(task, description=f"  {scenario.id} [control]")
            control_result = run_session(
                scenario_id=scenario.id,
                prompt=scenario.prompt,
                condition="control",
                workspace_path=ctrl_ws,
                plugin_dir=None,
                model=model,
                budget=budget,
                timeout=timeout,
                mode=mode,
            )

            # Run treatment
            progress.update(task, description=f"  {scenario.id} [treatment]")
            treatment_result = run_session(
                scenario_id=scenario.id,
                prompt=scenario.prompt,
                condition="treatment",
                workspace_path=treat_ws,
                plugin_dir=plugin_dir,
                model=model,
                budget=budget,
                timeout=timeout,
                mode=mode,
            )

            # Compute skill overhead ratio
            ctrl_input = control_result.total_usage.input_tokens
            treat_input = treatment_result.total_usage.input_tokens
            if treat_input > 0:
                treatment_result.skill_overhead_ratio = (
                    (treat_input - ctrl_input) / treat_input
                )

            pairs.append((control_result, treatment_result))

            # Save results
            scenario_dir = results_dir / scenario.id
            scenario_dir.mkdir(parents=True, exist_ok=True)
            (scenario_dir / "control.json").write_text(
                control_result.model_dump_json(indent=2)
            )
            (scenario_dir / "treatment.json").write_text(
                treatment_result.model_dump_json(indent=2)
            )

            progress.advance(task)

    # Write index
    index = {
        s.id: {
            "control": str(results_dir / s.id / "control.json"),
            "treatment": str(results_dir / s.id / "treatment.json"),
        }
        for s in scenario_set.scenarios
    }
    (output_dir / "index.json").write_text(json.dumps(index, indent=2))

    console.print(f"[green]✓[/green] Completed {len(pairs)} scenario pairs")
    return pairs
