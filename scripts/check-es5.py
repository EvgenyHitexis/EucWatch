#!/usr/bin/env python3
"""Fail unless every watch module the bundle builder ships parses as ECMAScript 5."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "laptop"))
from eucwatch.installation import bundle_modules  # noqa: E402


def shown(path: Path) -> str:
    path = path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "watch")
    args = parser.parse_args()
    modules = bundle_modules(args.source)
    if not modules:
        print(f"ES5 check: no watch modules in {args.source}", file=sys.stderr)
        return 2
    return subprocess.run(["node", str(ROOT / "scripts" / "check-es5.cjs"), *map(shown, modules)], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
