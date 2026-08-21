import json
from pathlib import Path
from typing import Any, Dict


def load_mapping(path: Path) -> Dict[str, Any]:
    """Load JSON or YAML; project YAML files are also valid JSON for no-dependency use."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is not None:
        loaded = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("configuration root must be a mapping")
    return loaded


def write_mapping(path: Path, value: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
