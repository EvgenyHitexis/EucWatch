#!/usr/bin/env python3
"""Fail unless every watch module the bundle builder ships parses as ECMAScript 5.

Exit 0: every module is ES5. Exit 1: a module is not. Exit 2: the check could not run.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "laptop"))
from eucwatch.installation import bundle_modules  # noqa: E402


def repository_relative(path: Path) -> str:
    """The resolved path, relative to the repository when it is inside it."""
    path = path.resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=ROOT / "watch")
    args = parser.parse_args()
    modules = bundle_modules(args.source)
    if not modules:
        print(f"ES5 check: no watch modules in {args.source}", file=sys.stderr)
        return 2
    node = shutil.which("node")
    if node is None:
        print("ES5 check: node is not on PATH; install Node.js, then run ./scripts/setup.sh", file=sys.stderr)
        return 2
    command = [node, str(ROOT / "scripts" / "check-es5.cjs"), *map(repository_relative, modules)]
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
