"""CLI entry point for skevals."""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="skevals",
    help="A/B testing CLI for Claude Code skills",
    no_args_is_help=True,
)
console = Console()


@app.command()
def analyze(
    skill_path: Annotated[Path, typer.Argument(help="Path to skill directory")],
    output: Annotated[Optional[Path], typer.Option(help="Output file path")] = None,
    model: Annotated[str, typer.Option(help="Model for analysis")] = "sonnet",
) -> None:
    """Analyze a skill and generate evaluation dimensions."""
    from skevals.analyzer.skill_analyzer import analyze_skill, parse_skill_dir

    console.print(f"Parsing skill at [cyan]{skill_path}[/cyan]...")
    manifest = parse_skill_dir(skill_path)
    console.print(f"  Name: {manifest.name}")
    console.print(f"  Files: {len(manifest.files)}")
    console.print(f"  Est. tokens: {manifest.estimated_context_tokens:,}")

    console.print(f"Analyzing with [cyan]{model}[/cyan]...")
    analysis = analyze_skill(manifest, model=model)
    console.print(f"  Capabilities: {len(analysis.capabilities)}")
    console.print(f"  Dimensions: {len(analysis.dimensions)}")

    output_path = output or Path("analysis.json")
    output_path.write_text(analysis.model_dump_json(indent=2))
    console.print(f"[green]Wrote[/green] {output_path}")


@app.command()
def generate(
    analysis_path: Annotated[Path, typer.Argument(help="Path to analysis.json")],
    count: Annotated[int, typer.Option(help="Number of scenarios")] = 6,
    output: Annotated[Optional[Path], typer.Option(help="Output file path")] = None,
    model: Annotated[str, typer.Option(help="Model for generation")] = "sonnet",
) -> None:
    """Generate evaluation scenarios from an analysis."""
    from skevals.generator.scenario_gen import generate_scenarios
    from skevals.models.skill import SkillAnalysis

    analysis = SkillAnalysis.model_validate_json(analysis_path.read_text())
    console.print(f"Generating {count} scenarios for [cyan]{analysis.manifest.name}[/cyan]...")

    scenario_set = generate_scenarios(analysis, count=count, model=model)
    console.print(f"  Generated {len(scenario_set.scenarios)} scenarios")

    output_path = output or Path("scenarios.json")
    output_path.write_text(scenario_set.model_dump_json(indent=2))
    console.print(f"[green]Wrote[/green] {output_path}")


@app.command()
def run(
    scenarios_path: Annotated[Path, typer.Argument(help="Path to scenarios.json")],
    skill_path: Annotated[Path, typer.Argument(help="Path to skill directory")],
    output_dir: Annotated[Path, typer.Option(help="Output directory")] = Path("./results"),
    model: Annotated[str, typer.Option(help="Model for Claude sessions")] = "sonnet",
    budget: Annotated[float, typer.Option(help="Max budget per session (USD)")] = 0.50,
) -> None:
    """Run A/B evaluation sessions for all scenarios."""
    from skevals.models.scenario import ScenarioSet
    from skevals.runner.orchestrator import run_all_scenarios

    scenario_set = ScenarioSet.model_validate_json(scenarios_path.read_text())
    console.print(
        f"Running {len(scenario_set.scenarios)} scenarios "
        f"(control + treatment) with [cyan]{model}[/cyan]..."
    )

    run_all_scenarios(
        scenario_set=scenario_set,
        skill_path=skill_path,
        output_dir=output_dir,
        model=model,
        budget=budget,
    )

    console.print(f"[green]Results saved to[/green] {output_dir}")


@app.command()
def judge(
    results_dir: Annotated[Path, typer.Argument(help="Path to results directory")],
    analysis_path: Annotated[Optional[Path], typer.Option(help="Path to analysis.json for dimensions")] = None,
    output: Annotated[Optional[Path], typer.Option(help="Output file path")] = None,
    model: Annotated[str, typer.Option(help="Model for judging")] = "sonnet",
) -> None:
    """Judge session results using rubric and pairwise comparison."""
    from skevals.judge.pairwise import compare_pair
    from skevals.judge.rubric import score_session
    from skevals.models.judge import ScenarioJudgment
    from skevals.models.session import SessionResult
    from skevals.models.skill import EvalDimension, SkillAnalysis

    # Load results index
    index_path = results_dir / "index.json"
    if not index_path.exists():
        # Try looking in parent if results_dir points to sessions/
        index_path = results_dir.parent / "index.json"
    if not index_path.exists():
        console.print("[red]No index.json found in results directory[/red]")
        raise typer.Exit(1)

    index = json.loads(index_path.read_text())

    # Load dimensions if analysis provided
    dimensions: list[EvalDimension] = []
    if analysis_path and analysis_path.exists():
        analysis = SkillAnalysis.model_validate_json(analysis_path.read_text())
        dimensions = analysis.dimensions

    judgments: list[ScenarioJudgment] = []

    for scenario_id, paths in index.items():
        console.print(f"Judging [cyan]{scenario_id}[/cyan]...")

        control = SessionResult.model_validate_json(Path(paths["control"]).read_text())
        treatment = SessionResult.model_validate_json(Path(paths["treatment"]).read_text())

        # Rubric scoring
        ctrl_rubric = score_session(control, dimensions, [], control.turns[0].prompt if control.turns else "", model=model)
        treat_rubric = score_session(treatment, dimensions, [], treatment.turns[0].prompt if treatment.turns else "", model=model)

        # Pairwise comparison
        prompt = control.turns[0].prompt if control.turns else ""
        pairwise = compare_pair(control, treatment, prompt, model=model)

        judgments.append(ScenarioJudgment(
            scenario_id=scenario_id,
            control_rubric=ctrl_rubric,
            treatment_rubric=treat_rubric,
            pairwise=pairwise,
        ))

    output_path = output or Path("judgments.json")
    output_path.write_text(
        json.dumps([j.model_dump() for j in judgments], indent=2)
    )
    console.print(f"[green]Wrote[/green] {output_path}")


@app.command()
def report(
    judgments_path: Annotated[Path, typer.Argument(help="Path to judgments.json")],
    results_dir: Annotated[Path, typer.Argument(help="Path to results directory")],
    output: Annotated[Optional[Path], typer.Option(help="Output file path")] = None,
    model: Annotated[str, typer.Option(help="Model for verdict generation")] = "sonnet",
) -> None:
    """Generate a comparison report from judgments."""
    from skevals.models.judge import ScenarioJudgment
    from skevals.models.session import SessionResult
    from skevals.reporter.report_gen import generate_report, render_markdown

    judgments_data = json.loads(judgments_path.read_text())
    judgments = [ScenarioJudgment.model_validate(j) for j in judgments_data]

    # Load results
    index = json.loads((results_dir / "index.json").read_text())
    control_results = []
    treatment_results = []
    for paths in index.values():
        control_results.append(SessionResult.model_validate_json(Path(paths["control"]).read_text()))
        treatment_results.append(SessionResult.model_validate_json(Path(paths["treatment"]).read_text()))

    # Infer skill name from first judgment or results
    skill_name = "unknown"
    if judgments:
        skill_name = judgments[0].scenario_id.rsplit("_", 1)[0]

    report_obj = generate_report(
        judgments=judgments,
        control_results=control_results,
        treatment_results=treatment_results,
        skill_name=skill_name,
        model=model,
    )

    output_path = output or Path("report.md")
    output_path.write_text(render_markdown(report_obj))
    console.print(f"[green]Wrote[/green] {output_path}")

    # Also save raw report JSON
    json_path = output_path.with_suffix(".json")
    json_path.write_text(report_obj.model_dump_json(indent=2))
    console.print(f"[green]Wrote[/green] {json_path}")


@app.command(name="eval")
def eval_skill(
    skill_path: Annotated[Path, typer.Argument(help="Path to skill directory")],
    output_dir: Annotated[Path, typer.Option(help="Output directory")] = Path("./eval-output"),
    scenarios: Annotated[int, typer.Option(help="Number of scenarios to generate")] = 6,
    model: Annotated[str, typer.Option(help="Model for analysis/generation and Claude sessions")] = "sonnet",
    budget: Annotated[float, typer.Option(help="Max budget per session (USD)")] = 0.50,
    lite: Annotated[bool, typer.Option("--lite", help="Lite mode: single-turn, text-only, truncated judge input (default)")] = False,
    full: Annotated[bool, typer.Option("--full", help="Full mode: multi-turn, tool use, sonnet judge")] = False,
    judge_model: Annotated[Optional[str], typer.Option(help="Model for judging (overrides mode default)")] = None,
) -> None:
    """Run full evaluation pipeline: analyze -> generate -> run -> judge -> report.

    Default mode is --lite (fast, cheap). Use --full for thorough evaluation with tool use.
    """
    from skevals.analyzer.skill_analyzer import analyze_skill, parse_skill_dir
    from skevals.config import EvalMode
    from skevals.generator.scenario_gen import generate_scenarios
    from skevals.judge.pairwise import compare_pair
    from skevals.judge.rubric import score_session
    from skevals.models.judge import ScenarioJudgment
    from skevals.reporter.report_gen import generate_report, render_markdown
    from skevals.runner.orchestrator import run_all_scenarios

    # Resolve mode: --full wins if both specified, default is lite
    mode = EvalMode.full if full else EvalMode.lite

    # Resolve judge model: explicit flag > mode default
    if judge_model is None:
        j_model = model
    else:
        j_model = judge_model

    # Lite mode judge settings
    judge_max_output_chars = 8000 if mode == EvalMode.lite else 0
    judge_max_tokens = 2048 if mode == EvalMode.lite else 16384

    output_dir.mkdir(parents=True, exist_ok=True)

    mode_label = f"[cyan]{mode.value}[/cyan]"
    console.print(f"\nMode: {mode_label} | Model: [cyan]{model}[/cyan] | Judge: [cyan]{j_model}[/cyan]")

    # Step 1: Analyze
    console.print("\n[bold]Step 1/5: Analyzing skill[/bold]")
    manifest = parse_skill_dir(skill_path)
    analysis = analyze_skill(manifest, model=model)
    analysis_path = output_dir / "analysis.json"
    analysis_path.write_text(analysis.model_dump_json(indent=2))
    console.print(f"  {len(analysis.capabilities)} capabilities, {len(analysis.dimensions)} dimensions")

    # Step 2: Generate scenarios
    console.print("\n[bold]Step 2/5: Generating scenarios[/bold]")
    scenario_set = generate_scenarios(analysis, count=scenarios, model=model, mode=mode)
    scenarios_path = output_dir / "scenarios.json"
    scenarios_path.write_text(scenario_set.model_dump_json(indent=2))
    console.print(f"  {len(scenario_set.scenarios)} scenarios generated")

    # Step 3: Run A/B sessions
    console.print("\n[bold]Step 3/5: Running A/B sessions[/bold]")
    pairs = run_all_scenarios(
        scenario_set=scenario_set,
        skill_path=skill_path,
        output_dir=output_dir,
        model=model,
        budget=budget,
        mode=mode,
    )

    # Step 4: Judge
    console.print("\n[bold]Step 4/5: Judging results[/bold]")
    judgments: list[ScenarioJudgment] = []
    for control, treatment in pairs:
        scenario = next(
            s for s in scenario_set.scenarios if s.id == control.scenario_id
        )
        ctrl_rubric = score_session(
            control, analysis.dimensions, scenario.expectations,
            scenario.prompt, model=j_model,
            max_output_chars=judge_max_output_chars,
            max_tokens=judge_max_tokens,
        )
        treat_rubric = score_session(
            treatment, analysis.dimensions, scenario.expectations,
            scenario.prompt, model=j_model,
            max_output_chars=judge_max_output_chars,
            max_tokens=judge_max_tokens,
        )
        pairwise = compare_pair(
            control, treatment, scenario.prompt, model=j_model,
            max_output_chars=judge_max_output_chars,
            max_tokens=judge_max_tokens,
        )
        judgments.append(ScenarioJudgment(
            scenario_id=scenario.id,
            control_rubric=ctrl_rubric,
            treatment_rubric=treat_rubric,
            pairwise=pairwise,
        ))
    judgments_path = output_dir / "judgments.json"
    judgments_path.write_text(
        json.dumps([j.model_dump() for j in judgments], indent=2)
    )

    # Step 5: Report
    console.print("\n[bold]Step 5/5: Generating report[/bold]")
    control_results = [c for c, _ in pairs]
    treatment_results = [t for _, t in pairs]
    report_obj = generate_report(
        judgments=judgments,
        control_results=control_results,
        treatment_results=treatment_results,
        skill_name=analysis.manifest.name,
        model=j_model,
    )
    report_path = output_dir / "report.md"
    report_path.write_text(render_markdown(report_obj))
    (output_dir / "report.json").write_text(report_obj.model_dump_json(indent=2))

    console.print(f"\n[bold green]Complete![/bold green]")
    console.print(f"  Report: {report_path}")
    console.print(f"  All artifacts: {output_dir}/")

    # Print summary
    console.print(f"\n  Control avg: {report_obj.control_summary.overall_score.mean:.2f}")
    console.print(f"  Treatment avg: {report_obj.treatment_summary.overall_score.mean:.2f}")
    console.print(
        f"  Pairwise: treatment {report_obj.pairwise_wins.get('treatment', 0)} / "
        f"control {report_obj.pairwise_wins.get('control', 0)} / "
        f"tie {report_obj.pairwise_wins.get('tie', 0)}"
    )


if __name__ == "__main__":
    app()
