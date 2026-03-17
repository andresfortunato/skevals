"""Workspace creation for scenario execution."""

import json
from pathlib import Path

from skevals.models.scenario import Scenario


def create_workspace(
    scenario: Scenario,
    condition: str,
    output_dir: Path,
    skill_path: Path | None = None,
) -> tuple[Path, Path | None]:
    """Create a temp workspace for running a scenario.

    Returns (workspace_path, plugin_dir | None).
    For treatment condition, wraps the skill into plugin format so --plugin-dir works.
    """
    workspace = output_dir / "workspaces" / scenario.id / condition
    workspace.mkdir(parents=True, exist_ok=True)

    # Write ground files
    for gf in scenario.ground_files:
        file_path = workspace / gf.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(gf.content)

    # Create a minimal .claude directory so Claude recognizes it as a project
    (workspace / ".claude").mkdir(exist_ok=True)

    plugin_dir = None
    if condition == "treatment" and skill_path is not None:
        plugin_dir = _create_plugin_wrapper(skill_path, output_dir / "plugins" / scenario.id)

    return workspace, plugin_dir


def _create_plugin_wrapper(skill_path: Path, plugin_dir: Path) -> Path:
    """Wrap a bare skill directory into plugin format for --plugin-dir.

    Creates:
      plugin_dir/
        .claude-plugin/
          plugin.json
        skills/
          <skill_name>/  -> symlink to actual skill dir
    """
    skill_name = skill_path.name

    plugin_meta_dir = plugin_dir / ".claude-plugin"
    plugin_meta_dir.mkdir(parents=True, exist_ok=True)

    plugin_json = {
        "name": f"skevals-{skill_name}",
        "version": "0.1.0",
        "description": f"Wrapper for evaluating skill: {skill_name}",
    }
    (plugin_meta_dir / "plugin.json").write_text(json.dumps(plugin_json, indent=2))

    skills_dir = plugin_dir / "skills" / skill_name
    skills_dir.parent.mkdir(parents=True, exist_ok=True)
    if skills_dir.exists() or skills_dir.is_symlink():
        skills_dir.unlink()
    skills_dir.symlink_to(skill_path.resolve())

    return plugin_dir
