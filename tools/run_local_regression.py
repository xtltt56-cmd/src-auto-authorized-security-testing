"""Run the bounded, non-destructive local OWASP regression profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src_auto.local_regression import MAX_ROUNDS, run_regression


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SRC-Auto 本地靶场安全回归")
    parser.add_argument("--local-only", action="store_true", default=True, help="仅回环靶场（固定启用）")
    parser.add_argument("--repeat-rounds", type=int, default=0, choices=range(0, MAX_ROUNDS + 1))
    parser.add_argument("--lab", action="append", dest="labs", help="只运行指定靶场，可重复指定")
    parser.add_argument("--case", action="append", dest="case_ids", help="只运行指定用例，可重复指定")
    parser.add_argument("--json", action="store_true", dest="json_output", help="只输出机器可读 JSON")
    args = parser.parse_args(argv)
    if not args.local_only:
        result = {"status": "BLOCKED_POLICY", "reason": "local_only_is_mandatory", "network_contact": False}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    try:
        result = run_regression(
            PROJECT_ROOT,
            repeat_rounds=args.repeat_rounds,
            labs=args.labs,
            case_ids=args.case_ids,
        )
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        result = {"status": "FAIL", "reason": "local_regression_failed", "detail": str(exc)[:500], "network_contact": False}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "COMPLETED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
