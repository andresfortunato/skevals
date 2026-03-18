"""Runner: workspace creation, Claude CLI execution, and A/B orchestration.

Merges the old executor.py + orchestrator.py + workspace.py into a single
zero-dep module.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend import resolve_model


# ---------------------------------------------------------------------------
# Workspace creation
# ---------------------------------------------------------------------------

def create_workspace(
    scenario: dict,
    condition: str,
    output_dir: str,
    skill_path: str | None = None,
) -> tuple[str, str | None]:
    """Create a temp workspace for running a scenario.

    Returns (workspace_path, plugin_dir | None).
    For treatment condition, wraps the skill into plugin format.
    """
    workspace = os.path.join(output_dir, "workspaces", scenario["id"], condition)
    os.makedirs(workspace, exist_ok=True)

    # Write ground files
    for gf in scenario.get("ground_files", []):
        file_path = os.path.join(workspace, gf["path"])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(gf["content"])

    # Create a minimal .claude directory so Claude recognizes it as a project
    os.makedirs(os.path.join(workspace, ".claude"), exist_ok=True)

    plugin_dir = None
    if condition == "treatment" and skill_path is not None:
        plugin_dir = _create_plugin_wrapper(
            skill_path, os.path.join(output_dir, "plugins", scenario["id"])
        )

    return workspace, plugin_dir


def _create_plugin_wrapper(skill_path: str, plugin_dir: str) -> str:
    """Wrap a bare skill directory into plugin format for --plugin-dir.

    Creates:
      plugin_dir/
        .claude-plugin/
          plugin.json
        skills/
          <skill_name>/  -> symlink to actual skill dir
    """
    skill_name = os.path.basename(os.path.normpath(skill_path))

    plugin_meta_dir = os.path.join(plugin_dir, ".claude-plugin")
    os.makedirs(plugin_meta_dir, exist_ok=True)

    plugin_json = {
        "name": f"skevals-{skill_name}",
        "version": "0.1.0",
        "description": f"Wrapper for evaluating skill: {skill_name}",
    }
    with open(os.path.join(plugin_meta_dir, "plugin.json"), "w") as f:
        json.dump(plugin_json, f, indent=2)

    skills_dir = os.path.join(plugin_dir, "skills", skill_name)
    os.makedirs(os.path.dirname(skills_dir), exist_ok=True)
    if os.path.exists(skills_dir) or os.path.islink(skills_dir):
        os.unlink(skills_dir)
    os.symlink(os.path.realpath(skill_path), skills_dir)

    return plugin_dir


# ---------------------------------------------------------------------------
# Session execution
# ---------------------------------------------------------------------------

def run_session(
    scenario_id: str,
    prompt: str,
    condition: str,
    workspace_path: str,
    plugin_dir: str | None,
    model: str = "sonnet",
    budget: float = 0.50,
    timeout: int = 300,
    mode: str = "lite",
) -> dict:
    """Run a single Claude session and return a session result dict.

    A/B control mechanism:
    - Control: --disable-slash-commands (no skills loaded)
    - Treatment: --plugin-dir <dir> (skill loaded via plugin wrapper)
    Lite mode adds: --max-turns 1
    """
    resolved_model = resolve_model(model)

    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--no-session-persistence",
        "--model", resolved_model,
        "--max-budget-usd", str(budget),
        "-p", prompt,
    ]

    if mode == "lite":
        cmd.extend(["--max-turns", "1"])

    if condition == "control":
        cmd.append("--disable-slash-commands")
    elif condition == "treatment" and plugin_dir is not None:
        cmd.extend(["--plugin-dir", plugin_dir])

    # Strip CLAUDECODE env var to allow nesting claude inside Claude Code
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=workspace_path,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _make_session_result(
            scenario_id, condition, prompt, "[TIMEOUT]",
            duration_ms=timeout * 1000,
        )

    output = _parse_claude_output(result.stdout)

    # If result_text is empty, Claude likely used tool calls to write files.
    if not output["result_text"].strip():
        output["result_text"] = _collect_workspace_output(workspace_path)

    return _make_session_result(
        scenario_id,
        condition,
        prompt,
        output["result_text"],
        session_id=output.get("session_id", ""),
        duration_ms=output.get("duration_ms", 0),
        duration_api_ms=output.get("duration_api_ms", 0),
        total_cost_usd=output.get("total_cost_usd", 0.0),
        usage=output.get("usage", {}),
        output_composition=_analyze_output_composition(output["result_text"]),
    )


def _make_session_result(
    scenario_id: str,
    condition: str,
    prompt: str,
    result_text: str,
    *,
    session_id: str = "",
    duration_ms: int = 0,
    duration_api_ms: int = 0,
    total_cost_usd: float = 0.0,
    usage: dict | None = None,
    output_composition: dict | None = None,
) -> dict:
    """Build a session result dict."""
    u = usage or {}
    return {
        "scenario_id": scenario_id,
        "condition": condition,
        "turns": [
            {
                "prompt": prompt,
                "output": {
                    "result_text": result_text,
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "duration_api_ms": duration_api_ms,
                    "total_cost_usd": total_cost_usd,
                    "usage": {
                        "input_tokens": u.get("input_tokens", 0),
                        "output_tokens": u.get("output_tokens", 0),
                        "cache_read_tokens": u.get("cache_read_tokens", 0),
                        "cache_creation_tokens": u.get("cache_creation_tokens", 0),
                    },
                },
            }
        ],
        "total_duration_ms": duration_ms,
        "total_duration_api_ms": duration_api_ms,
        "total_cost_usd": total_cost_usd,
        "total_usage": {
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": u.get("cache_read_tokens", 0),
            "cache_creation_tokens": u.get("cache_creation_tokens", 0),
        },
        "skill_overhead_ratio": None,
        "output_composition": output_composition,
        "reference_files_available": 0,
        "reference_files_loaded": 0,
    }


def _parse_claude_output(stdout: str) -> dict:
    """Parse JSON output from claude --print --output-format json."""
    if not stdout.strip():
        return {"result_text": "[EMPTY OUTPUT]", "usage": {}}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"result_text": stdout.strip(), "usage": {}}

    usage = _extract_model_usage(data)
    return {
        "result_text": data.get("result", data.get("text", "")),
        "session_id": data.get("session_id", ""),
        "duration_ms": data.get("duration_ms", 0),
        "duration_api_ms": data.get("duration_api_ms", 0),
        "total_cost_usd": data.get("total_cost_usd", data.get("cost_usd", 0.0)),
        "usage": usage,
    }


def _extract_model_usage(data: dict) -> dict:
    """Extract token counts from modelUsage (accurate) or usage (fallback)."""
    model_usage = data.get("modelUsage", {})
    if model_usage:
        return {
            "input_tokens": sum(m.get("inputTokens", 0) for m in model_usage.values()),
            "output_tokens": sum(m.get("outputTokens", 0) for m in model_usage.values()),
            "cache_read_tokens": sum(m.get("cacheReadInputTokens", 0) for m in model_usage.values()),
            "cache_creation_tokens": sum(m.get("cacheCreationInputTokens", 0) for m in model_usage.values()),
        }

    usage = data.get("usage", {})
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
    }


_SKIP_DIRS = {".claude", "__pycache__", ".git", "node_modules"}
_MAX_FILE_SIZE = 50_000


def _collect_workspace_output(workspace_path: str) -> str:
    """Collect files created/modified in workspace as text for the judge."""
    parts: list[str] = []
    for root, dirs, filenames in os.walk(workspace_path):
        # Prune skip dirs
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in sorted(filenames):
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, workspace_path)
            try:
                with open(full, errors="replace") as f:
                    content = f.read()
            except OSError:
                continue
            if len(content) > _MAX_FILE_SIZE:
                content = content[:_MAX_FILE_SIZE] + "\n... [truncated]"
            parts.append(f"--- {rel} ---\n{content}")

    if not parts:
        return "[No files created in workspace]"
    return "[Claude wrote files via tool use]\n\n" + "\n\n".join(parts)


def _analyze_output_composition(text: str) -> dict[str, int]:
    """Heuristically classify output lines as code vs prose."""
    code_lines = 0
    prose_lines = 0
    in_code_block = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not stripped:
            continue
        if in_code_block:
            code_lines += 1
        else:
            prose_lines += 1

    return {"code_lines": code_lines, "prose_lines": prose_lines}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_all_scenarios(
    scenario_set: dict,
    skill_path: str,
    output_dir: str,
    model: str = "sonnet",
    budget: float = 0.50,
    timeout: int = 300,
    mode: str = "lite",
) -> list[tuple[dict, dict]]:
    """Run all scenarios, each in control + treatment. Returns pairs."""
    results_dir = os.path.join(output_dir, "sessions")
    os.makedirs(results_dir, exist_ok=True)

    scenarios = scenario_set["scenarios"]
    total = len(scenarios)
    pairs: list[tuple[dict, dict]] = []

    for i, scenario in enumerate(scenarios):
        sid = scenario["id"]
        print(f"  [{i + 1}/{total}] {sid}")

        # Create workspaces
        ctrl_ws, _ = create_workspace(scenario, "control", output_dir)
        treat_ws, plugin_dir = create_workspace(scenario, "treatment", output_dir, skill_path)

        # Run control
        print(f"    control...", end="", flush=True)
        control_result = run_session(
            scenario_id=sid,
            prompt=scenario["prompt"],
            condition="control",
            workspace_path=ctrl_ws,
            plugin_dir=None,
            model=model,
            budget=budget,
            timeout=timeout,
            mode=mode,
        )
        print(" done")

        # Run treatment
        print(f"    treatment...", end="", flush=True)
        treatment_result = run_session(
            scenario_id=sid,
            prompt=scenario["prompt"],
            condition="treatment",
            workspace_path=treat_ws,
            plugin_dir=plugin_dir,
            model=model,
            budget=budget,
            timeout=timeout,
            mode=mode,
        )
        print(" done")

        # Compute skill overhead ratio
        ctrl_input = control_result["total_usage"]["input_tokens"]
        treat_input = treatment_result["total_usage"]["input_tokens"]
        if treat_input > 0:
            treatment_result["skill_overhead_ratio"] = (
                (treat_input - ctrl_input) / treat_input
            )

        pairs.append((control_result, treatment_result))

        # Save results
        scenario_dir = os.path.join(results_dir, sid)
        os.makedirs(scenario_dir, exist_ok=True)
        with open(os.path.join(scenario_dir, "control.json"), "w") as f:
            json.dump(control_result, f, indent=2)
        with open(os.path.join(scenario_dir, "treatment.json"), "w") as f:
            json.dump(treatment_result, f, indent=2)

    # Write index
    index = {
        s["id"]: {
            "control": os.path.join(results_dir, s["id"], "control.json"),
            "treatment": os.path.join(results_dir, s["id"], "treatment.json"),
        }
        for s in scenarios
    }
    with open(os.path.join(output_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=2)

    print(f"  Completed {len(pairs)} scenario pairs")
    return pairs
