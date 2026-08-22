"""Safe, local-only discovery for confirmed offline review targets."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import List, Optional, Union


PathLike = Union[str, Path]


@dataclass(frozen=True)
class ReviewTarget:
    scope_path: Path
    plan_path: Path
    target_dir: Path
    relative_name: str


@dataclass(frozen=True)
class ReviewTargetEntry:
    scope_path: Optional[Path]
    plan_path: Optional[Path]
    target_dir: Path
    relative_name: str
    scope_status: str
    plan_status: str
    status: str
    actionable: bool


def _resolve_directory(path: PathLike, missing_reason: str, file_reason: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise ValueError(missing_reason)
    if not resolved.is_dir():
        raise ValueError(file_reason)
    return resolved


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validated_roots(selected_directory: PathLike, targets_root: PathLike):
    root = _resolve_directory(
        targets_root, "targets_root_missing", "targets_root_not_directory"
    )
    selected = _resolve_directory(
        selected_directory,
        "selected_directory_missing",
        "selected_path_not_directory",
    )
    if not _is_within(selected, root):
        raise ValueError("outside_targets_root")
    return selected, root


def inspect_review_targets(
    selected_directory: PathLike, targets_root: PathLike
) -> List[ReviewTargetEntry]:
    """Describe review-related target directories without granting permission."""

    selected, root = _validated_roots(selected_directory, targets_root)
    entries = []
    recognized_names = {
        "scope_confirmed.yaml",
        "scope_candidate.yaml",
        "live_plan.yaml",
    }

    for current_raw, directory_names, file_names in os.walk(
        str(selected), followlinks=False
    ):
        current = Path(current_raw).resolve()
        directory_names[:] = [
            name
            for name in directory_names
            if not (Path(current_raw) / name).is_symlink()
        ]
        if not _is_within(current, root):
            directory_names[:] = []
            continue
        present_names = recognized_names.intersection(file_names)
        if not present_names:
            continue

        confirmed = (current / "scope_confirmed.yaml").resolve()
        candidate = (current / "scope_candidate.yaml").resolve()
        plan = (current / "live_plan.yaml").resolve()
        confirmed_present = (
            "scope_confirmed.yaml" in present_names
            and _is_within(confirmed, root)
            and confirmed.is_file()
        )
        candidate_present = (
            "scope_candidate.yaml" in present_names
            and _is_within(candidate, root)
            and candidate.is_file()
        )
        plan_present = (
            "live_plan.yaml" in present_names
            and _is_within(plan, root)
            and plan.is_file()
        )

        if confirmed_present and plan_present:
            status = "ready"
            actionable = True
        elif confirmed_present:
            status = "missing_plan"
            actionable = False
        elif candidate_present:
            status = "candidate_only"
            actionable = False
        else:
            status = "missing_scope"
            actionable = False

        relative_name = current.relative_to(root).as_posix()
        entries.append(
            ReviewTargetEntry(
                scope_path=confirmed if confirmed_present else (candidate if candidate_present else None),
                plan_path=plan if plan_present else None,
                target_dir=current,
                relative_name=relative_name,
                scope_status=(
                    "confirmed"
                    if confirmed_present
                    else ("candidate" if candidate_present else "missing")
                ),
                plan_status="present" if plan_present else "missing",
                status=status,
                actionable=actionable,
            )
        )

    return sorted(entries, key=lambda item: item.relative_name.casefold())


def discover_review_targets(
    selected_directory: PathLike, targets_root: PathLike
) -> List[ReviewTarget]:
    """Return confirmed scope/plan pairs below an allowed project target root.

    This function performs filesystem discovery only. It does not parse plans,
    invoke the target-review command, or make any network request.
    """

    discovered = []
    for entry in inspect_review_targets(selected_directory, targets_root):
        if not entry.actionable or entry.scope_path is None or entry.plan_path is None:
            continue
        discovered.append(
            ReviewTarget(
                scope_path=entry.scope_path,
                plan_path=entry.plan_path,
                target_dir=entry.target_dir,
                relative_name=entry.relative_name,
            )
        )
    return discovered


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover confirmed SRC-Auto targets for offline review."
    )
    parser.add_argument("--selected", required=True)
    parser.add_argument("--root", required=True)
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        entries = inspect_review_targets(args.selected, args.root)
    except ValueError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2

    targets = [entry for entry in entries if entry.actionable]

    payload = {
        "status": "ok",
        "entries": [
            {
                "relative_name": entry.relative_name,
                "scope_path": str(entry.scope_path) if entry.scope_path else "",
                "plan_path": str(entry.plan_path) if entry.plan_path else "",
                "target_dir": str(entry.target_dir),
                "scope_status": entry.scope_status,
                "plan_status": entry.plan_status,
                "status": entry.status,
                "actionable": entry.actionable,
            }
            for entry in entries
        ],
        "targets": [
            {
                "relative_name": target.relative_name,
                "scope_path": str(target.scope_path),
                "plan_path": str(target.plan_path),
                "target_dir": str(target.target_dir),
            }
            for target in targets
        ],
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
