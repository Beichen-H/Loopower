#!/usr/bin/env python3
"""Install meta-skills-library skills into a local Codex skills directory.

This installer copies only static skill assets. It does not install or generate a
Runtime Engine; execution remains the responsibility of an external controller.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SKILL_NAME = "prompt-to-loop-engineering"
DEFAULT_TARGET_ROOT = Path.home() / ".codex" / "skills"
EXCLUDED_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install a static Skill asset from meta-skills-library into a local "
            "Codex skills directory."
        )
    )
    parser.add_argument(
        "--skill",
        default=DEFAULT_SKILL_NAME,
        help=f"Skill folder under skills/ to install. Default: {DEFAULT_SKILL_NAME}",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET_ROOT,
        help=f"Destination skills root. Default: {DEFAULT_TARGET_ROOT}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing installed skill directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writing files.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run the installed skill's static DAG validation after copying.",
    )
    return parser.parse_args()


def should_ignore(_: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(name)
        if name in EXCLUDED_DIRS or path.suffix in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


def require_skill_source(skill_name: str) -> Path:
    source = REPO_ROOT / "skills" / skill_name
    required = ["SKILL.md", "loop_spec.json", "scripts/test_spec_loading.py"]
    missing = [relative for relative in required if not (source / relative).is_file()]
    if not source.is_dir() or missing:
        missing_text = ", ".join(missing) if missing else str(source)
        raise SystemExit(f"Skill source is incomplete: {missing_text}")
    return source


def safe_remove_existing(destination: Path, target_root: Path) -> None:
    resolved_destination = destination.resolve()
    resolved_target_root = target_root.resolve()
    if resolved_destination == resolved_target_root:
        raise SystemExit("Refusing to remove the target skills root itself.")
    if resolved_target_root not in resolved_destination.parents:
        raise SystemExit(f"Refusing to remove path outside target root: {destination}")
    shutil.rmtree(resolved_destination)


def run_verification(destination: Path) -> None:
    test_script = destination / "scripts" / "test_spec_loading.py"
    result = subprocess.run(
        [sys.executable, "-B", str(test_script)],
        cwd=destination,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    args = parse_args()
    source = require_skill_source(args.skill)
    target_root = args.target.expanduser()
    destination = target_root / args.skill

    print(f"Source:      {source}")
    print(f"Destination: {destination}")
    print("Runtime:     not installed; Codex is the host executor for project-local scaffolds")

    if args.dry_run:
        action = "replace" if destination.exists() else "copy"
        print(f"DRY RUN: would {action} static skill assets.")
        if args.verify:
            print("DRY RUN: would run scripts/test_spec_loading.py after install.")
        return 0

    if destination.exists():
        if not args.force:
            raise SystemExit(
                f"Destination already exists: {destination}\n"
                "Use --force to replace it, or choose another --target."
            )
        safe_remove_existing(destination, target_root)

    target_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=should_ignore)
    print(f"Installed {args.skill} to {destination}")

    if args.verify:
        run_verification(destination)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
