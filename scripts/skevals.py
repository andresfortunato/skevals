#!/usr/bin/env python3
"""skevals — A/B testing CLI for Claude Code skills.

Zero-dependency entry point. Runs as:
  python scripts/skevals.py eval <skill-path> [options]
  python scripts/skevals.py analyze|generate|run|judge|report [args]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure sibling modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend import set_backend


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze a skill and generate evaluation dimensions."""
    from analyzer import analyze_skill, parse_skill_dir

    print(f"Parsing skill at {args.skill_path}...")
    manifest = parse_skill_dir(args.skill_path)
    print(f"  Name: {manifest['name']}")
    print(f"  Files: {len(manifest['files'])}")
    print(f"  Est. tokens: {manifest['estimated_context_tokens']:,}")

    print(f"Analyzing with {args.model}...")
    analysis = analyze_skill(manifest, model=args.model)
    print(f"  Capabilities: {len(analysis['capabilities'])}")
    print(f"  Dimensions: {len(analysis['dimensions'])}")

    output_path = args.output or os.path.join(os.getcwd(), "analysis.json")
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"Wrote {output_path}")


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate evaluation scenarios from an analysis."""
    from generator import generate_scenarios

    with open(args.analysis_path) as f:
        analysis = json.load(f)

    print(f"Generating {args.count} scenarios for {analysis['manifest']['name']}...")
    scenario_set = generate_scenarios(
        analysis, count=args.count, model=args.model, mode=args.mode,
    )
    print(f"  Generated {len(scenario_set['scenarios'])} scenarios")

    output_path = args.output or os.path.join(os.getcwd(), "scenarios.json")
    with open(output_path, "w") as f:
        json.dump(scenario_set, f, indent=2)
    print(f"Wrote {output_path}")


def cmd_run(args: argparse.Namespace) -> None:
    """Run A/B evaluation sessions for all scenarios."""
    from runner import run_all_scenarios

    with open(args.scenarios_path) as f:
        scenario_set = json.load(f)

    n = len(scenario_set["scenarios"])
    print(f"Running {n} scenarios (control + treatment) with {args.model}...")

    run_all_scenarios(
        scenario_set=scenario_set,
        skill_path=args.skill_path,
        output_dir=args.output_dir,
        model=args.model,
        budget=args.budget,
        timeout=args.timeout,
        mode=args.mode,
    )
    print(f"Results saved to {args.output_dir}")


def cmd_judge(args: argparse.Namespace) -> None:
    """Judge session results using rubric and pairwise comparison."""
    from judge import judge_scenario

    # Load results index
    index_path = os.path.join(args.results_dir, "index.json")
    if not os.path.isfile(index_path):
        parent_index = os.path.join(os.path.dirname(args.results_dir), "index.json")
        if os.path.isfile(parent_index):
            index_path = parent_index
        else:
            print(f"Error: No index.json found in {args.results_dir}")
            sys.exit(1)

    with open(index_path) as f:
        index = json.load(f)

    # Load dimensions if analysis provided
    dimensions: list[dict] = []
    scenarios_by_id: dict[str, dict] = {}
    if args.analysis_path and os.path.isfile(args.analysis_path):
        with open(args.analysis_path) as f:
            analysis = json.load(f)
        dimensions = analysis.get("dimensions", [])
    if args.scenarios_path and os.path.isfile(args.scenarios_path):
        with open(args.scenarios_path) as f:
            scenario_set = json.load(f)
        scenarios_by_id = {s["id"]: s for s in scenario_set.get("scenarios", [])}

    judgments: list[dict] = []
    for scenario_id, paths in index.items():
        print(f"Judging {scenario_id}...")

        with open(paths["control"]) as f:
            control = json.load(f)
        with open(paths["treatment"]) as f:
            treatment = json.load(f)

        scenario = scenarios_by_id.get(scenario_id, {
            "id": scenario_id,
            "prompt": control["turns"][0]["prompt"] if control.get("turns") else "",
            "expectations": [],
        })

        judgment = judge_scenario(
            scenario, control, treatment, dimensions,
            model=args.model,
            max_output_chars=args.max_output_chars,
            max_tokens=args.max_tokens,
        )
        judgments.append(judgment)

    output_path = args.output or os.path.join(os.getcwd(), "judgments.json")
    with open(output_path, "w") as f:
        json.dump(judgments, f, indent=2)
    print(f"Wrote {output_path}")


def cmd_report(args: argparse.Namespace) -> None:
    """Generate a comparison report from judgments."""
    from reporter import generate_report, render_markdown

    with open(args.judgments_path) as f:
        judgments = json.load(f)

    with open(os.path.join(args.results_dir, "index.json")) as f:
        index = json.load(f)

    control_results = []
    treatment_results = []
    for paths in index.values():
        with open(paths["control"]) as f:
            control_results.append(json.load(f))
        with open(paths["treatment"]) as f:
            treatment_results.append(json.load(f))

    skill_name = args.skill_name or "unknown"

    report = generate_report(
        judgments=judgments,
        control_results=control_results,
        treatment_results=treatment_results,
        skill_name=skill_name,
        model=args.model,
    )

    output_path = args.output or os.path.join(os.getcwd(), "report.md")
    with open(output_path, "w") as f:
        f.write(render_markdown(report))
    print(f"Wrote {output_path}")

    json_path = os.path.splitext(output_path)[0] + ".json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {json_path}")


def cmd_eval_skill(args: argparse.Namespace) -> None:
    """Run full pipeline: analyze -> generate -> run -> judge -> report."""
    from analyzer import analyze_skill, parse_skill_dir
    from judge import judge_scenario
    from generator import generate_scenarios
    from reporter import generate_report, render_markdown
    from runner import run_all_scenarios

    # Resolve mode
    mode = "full" if args.full else "lite"

    # Resolve judge model
    j_model = args.judge_model or args.model

    # Lite mode judge settings
    judge_max_output_chars = 8000 if mode == "lite" else 0
    judge_max_tokens = 2048 if mode == "lite" else 16384

    os.makedirs(args.output_dir, exist_ok=True)

    print(f"\nMode: {mode} | Model: {args.model} | Judge: {j_model}")

    # Step 1: Analyze
    print("\n--- Step 1/5: Analyzing skill ---")
    manifest = parse_skill_dir(args.skill_path)
    analysis = analyze_skill(manifest, model=args.model)
    analysis_path = os.path.join(args.output_dir, "analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"  {len(analysis['capabilities'])} capabilities, {len(analysis['dimensions'])} dimensions")

    # Step 2: Generate scenarios
    print("\n--- Step 2/5: Generating scenarios ---")
    scenario_set = generate_scenarios(
        analysis, count=args.scenarios, model=args.model, mode=mode,
    )
    scenarios_path = os.path.join(args.output_dir, "scenarios.json")
    with open(scenarios_path, "w") as f:
        json.dump(scenario_set, f, indent=2)
    print(f"  {len(scenario_set['scenarios'])} scenarios generated")

    # Step 3: Run A/B sessions
    print("\n--- Step 3/5: Running A/B sessions ---")
    pairs = run_all_scenarios(
        scenario_set=scenario_set,
        skill_path=args.skill_path,
        output_dir=args.output_dir,
        model=args.model,
        budget=args.budget,
        timeout=args.timeout,
        mode=mode,
    )

    # Step 4: Judge
    print("\n--- Step 4/5: Judging results ---")
    judgments: list[dict] = []
    scenarios_by_id = {s["id"]: s for s in scenario_set["scenarios"]}
    for control, treatment in pairs:
        sid = control["scenario_id"]
        scenario = scenarios_by_id[sid]
        print(f"  Judging {sid}...")

        judgment = judge_scenario(
            scenario, control, treatment,
            analysis["dimensions"],
            model=j_model,
            max_output_chars=judge_max_output_chars,
            max_tokens=judge_max_tokens,
        )
        judgments.append(judgment)

    judgments_path = os.path.join(args.output_dir, "judgments.json")
    with open(judgments_path, "w") as f:
        json.dump(judgments, f, indent=2)

    # Step 5: Report
    print("\n--- Step 5/5: Generating report ---")
    control_results = [c for c, _ in pairs]
    treatment_results = [t for _, t in pairs]
    report = generate_report(
        judgments=judgments,
        control_results=control_results,
        treatment_results=treatment_results,
        skill_name=analysis["manifest"]["name"],
        model=j_model,
    )
    report_path = os.path.join(args.output_dir, "report.md")
    with open(report_path, "w") as f:
        f.write(render_markdown(report))
    with open(os.path.join(args.output_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Summary
    cs = report["control_summary"]
    ts = report["treatment_summary"]
    pw = report["pairwise_wins"]
    print(f"\nComplete!")
    print(f"  Report: {report_path}")
    print(f"  Control avg: {cs['overall_score']['mean']:.2f}")
    print(f"  Treatment avg: {ts['overall_score']['mean']:.2f}")
    print(f"  Pairwise: treatment {pw.get('treatment', 0)} / control {pw.get('control', 0)} / tie {pw.get('tie', 0)}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skevals",
        description="A/B testing CLI for Claude Code skills",
    )
    parser.add_argument(
        "--backend", choices=["api", "cli"],
        help="Force LLM backend (default: auto-detect)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- eval (full pipeline) ---
    p_eval = sub.add_parser("eval", help="Run full evaluation pipeline")
    p_eval.add_argument("skill_path", help="Path to skill directory")
    p_eval.add_argument("--output-dir", default="./eval-output", help="Output directory (default: ./eval-output)")
    p_eval.add_argument("--scenarios", type=int, default=6, help="Number of scenarios (default: 6)")
    p_eval.add_argument("--model", default="sonnet", help="Model for analysis/generation/sessions (default: sonnet)")
    p_eval.add_argument("--judge-model", default=None, help="Override judge model")
    p_eval.add_argument("--budget", type=float, default=0.50, help="Max budget per session in USD (default: 0.50)")
    p_eval.add_argument("--timeout", type=int, default=300, help="Session timeout in seconds (default: 300)")
    p_eval.add_argument("--lite", action="store_true", default=True, help="Lite mode: single-turn, text-only (default)")
    p_eval.add_argument("--full", action="store_true", default=False, help="Full mode: multi-turn, tool use")
    p_eval.set_defaults(func=cmd_eval_skill)

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Analyze a skill and generate eval dimensions")
    p_analyze.add_argument("skill_path", help="Path to skill directory")
    p_analyze.add_argument("--output", "-o", help="Output file path (default: analysis.json)")
    p_analyze.add_argument("--model", default="sonnet", help="Model for analysis (default: sonnet)")
    p_analyze.set_defaults(func=cmd_analyze)

    # --- generate ---
    p_gen = sub.add_parser("generate", help="Generate scenarios from an analysis")
    p_gen.add_argument("analysis_path", help="Path to analysis.json")
    p_gen.add_argument("--count", type=int, default=6, help="Number of scenarios (default: 6)")
    p_gen.add_argument("--output", "-o", help="Output file path (default: scenarios.json)")
    p_gen.add_argument("--model", default="sonnet", help="Model for generation (default: sonnet)")
    p_gen.add_argument("--mode", choices=["lite", "full"], default="lite", help="Mode (default: lite)")
    p_gen.set_defaults(func=cmd_generate)

    # --- run ---
    p_run = sub.add_parser("run", help="Run A/B sessions for all scenarios")
    p_run.add_argument("scenarios_path", help="Path to scenarios.json")
    p_run.add_argument("skill_path", help="Path to skill directory")
    p_run.add_argument("--output-dir", default="./results", help="Output directory (default: ./results)")
    p_run.add_argument("--model", default="sonnet", help="Model for sessions (default: sonnet)")
    p_run.add_argument("--budget", type=float, default=0.50, help="Max budget per session (default: 0.50)")
    p_run.add_argument("--timeout", type=int, default=300, help="Session timeout in seconds (default: 300)")
    p_run.add_argument("--mode", choices=["lite", "full"], default="lite", help="Mode (default: lite)")
    p_run.set_defaults(func=cmd_run)

    # --- judge ---
    p_judge = sub.add_parser("judge", help="Judge session results")
    p_judge.add_argument("results_dir", help="Path to results directory")
    p_judge.add_argument("--analysis-path", help="Path to analysis.json for dimensions")
    p_judge.add_argument("--scenarios-path", help="Path to scenarios.json for expectations")
    p_judge.add_argument("--output", "-o", help="Output file path (default: judgments.json)")
    p_judge.add_argument("--model", default="sonnet", help="Model for judging (default: sonnet)")
    p_judge.add_argument("--max-output-chars", type=int, default=0, help="Truncate outputs before judging")
    p_judge.add_argument("--max-tokens", type=int, default=16384, help="Max judge output tokens")
    p_judge.set_defaults(func=cmd_judge)

    # --- report ---
    p_report = sub.add_parser("report", help="Generate comparison report")
    p_report.add_argument("judgments_path", help="Path to judgments.json")
    p_report.add_argument("results_dir", help="Path to results directory")
    p_report.add_argument("--output", "-o", help="Output file path (default: report.md)")
    p_report.add_argument("--model", default="sonnet", help="Model for verdict (default: sonnet)")
    p_report.add_argument("--skill-name", help="Skill name for report header")
    p_report.set_defaults(func=cmd_report)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Apply backend override if specified
    if args.backend:
        set_backend(args.backend)

    args.func(args)


if __name__ == "__main__":
    main()
