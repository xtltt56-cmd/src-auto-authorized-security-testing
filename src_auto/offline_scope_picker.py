"""Safe, local-only discovery for confirmed offline review targets."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import List, Union


PathLike = Union[str, Path]


@dataclass(frozen=True)
class ReviewTarget:
    scope_path: Path
    plan_path: Path
    target_dir: Path
    relative_name: str


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


def discover_review_targets(
    selected_directory: PathLike, targets_root: PathLike
) -> List[ReviewTarget]:
    """Return confirmed scope/plan pairs below an allowed project target root.

    This function performs filesystem discovery only. It does not parse plans,
    invoke the target-review command, or make any network request.
    """

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

    discovered = []
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
        if "scope_confirmed.yaml" not in file_names or "live_plan.yaml" not in file_names:
            continue

        scope = (current / "scope_confirmed.yaml").resolve()
        plan = (current / "live_plan.yaml").resolve()
        if not _is_within(scope, root) or not _is_within(plan, root):
            continue
        if not scope.is_file() or not plan.is_file():
            continue

        relative_name = current.relative_to(root).as_posix()
        discovered.append(
            ReviewTarget(
                scope_path=scope,
                plan_path=plan,
                target_dir=current,
                relative_name=relative_name,
            )
        )

    return sorted(discovered, key=lambda item: item.relative_name.casefold())
