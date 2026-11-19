#!/usr/bin/env python3
"""Does this regression test fail without the fix? Run the working tree's version of
a test against a base ref's code, and against the working tree.

The base is exported with `git archive` to a temporary directory outside the
repository, and the working tree's test code (tests/ and watch/tests/, so the
shared helpers come along) is copied over it. The working tree is exported the
way evidence-compare exports it: tracked files with their uncommitted changes,
plus untracked files that are not ignored. Both copies run on this tree's
ignored dependencies (the Python .venv and frontend/node_modules).

The test runs as check.sh runs it:
  tests/test_*.py        python -m unittest, each extra argument a test name in the module
  tests/<other>.py       a browser flow or the launch smoke, after the copy's frontend is built;
                         extra arguments go to the script (a flow name, for browser flows)
  watch/tests/*.cjs      node

With --runs N, each copy runs the test N times, for a race that fails only when
its interleaving is forced. A run counts as failed when it exits non-zero or
exceeds the timeout. The base's first failure is printed, so you can see whether
the test fails for the reason the fix addresses.

Exit 0: red, meaning every base run failed and every working-tree run passed.
Exit 1: not red, meaning some base run passed or some working-tree run failed.
Exit 2: the run itself failed (an unknown ref, a missing test, a frontend build that fails).
The repository is never written: git status and git worktree list are unchanged.
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_spec = importlib.util.spec_from_file_location("evidence_compare", Path(__file__).with_name("evidence-compare.py"))
compare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare)

# The working tree's test code, copied over the base: a test brings its helpers with it.
TEST_DIRECTORIES = ["tests", "watch/tests"]
TIMEOUT_SECONDS = 300
# The lines of the base's first failure that are printed.
SHOWN_LINES = 20


def command_for(copy: Path, test: str, names: list[str]) -> list[str]:
    """The command check.sh would run for this test, in this copy."""
    python = str(copy / compare.VENV / "bin/python")
    path = Path(test)
    if path.parts[:2] == ("watch", "tests") and path.suffix == ".cjs":
        return ["node", test, *names]
    if path.parent == Path("tests") and path.suffix == ".py":
        if path.name.startswith("test_"):
            return [python, "-m", "unittest", *([f"{path.stem}.{name}" for name in names] or [path.stem])]
        return [python, test, *names]
    raise compare.Failed(f"{test}: not a test check.sh runs (tests/*.py or watch/tests/*.cjs)")


def needs_frontend(test: str) -> bool:
    path = Path(test)
    return path.parent == Path("tests") and path.suffix == ".py" and not path.name.startswith("test_")


def prepare(copy: Path, test: str):
    """Link this tree's dependencies into the copy, and build its frontend if the test serves it."""
    if not (copy / test).is_file():
        raise compare.Failed(f"{test} does not exist in the working tree")
    (copy / compare.VENV).parent.mkdir(parents=True, exist_ok=True)
    (copy / compare.VENV).symlink_to(compare.ROOT / compare.VENV, target_is_directory=True)
    if needs_frontend(test):
        (copy / compare.NODE_MODULES).symlink_to(compare.ROOT / compare.NODE_MODULES, target_is_directory=True)
        result = subprocess.run(["npm", "run", "build", "--prefix", "frontend"], cwd=copy, capture_output=True, text=True)
        if result.returncode:
            raise compare.Failed(f"{copy.name}: the frontend build exited {result.returncode}\n{result.stdout}{result.stderr}")


def run_once(copy: Path, command: list[str]) -> tuple[bool, str]:
    """Run the test once in the copy, without any inherited EUCWATCH_* setting. True when it passed."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("EUCWATCH_")}
    try:
        result = subprocess.run(command, cwd=copy, env={**env, "PYTHONPATH": "laptop:tests"},
                                capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as expired:
        output = (expired.stdout or b"").decode() if isinstance(expired.stdout, bytes) else (expired.stdout or "")
        return False, f"{output}timed out after {TIMEOUT_SECONDS} s"
    except OSError as error:
        raise compare.Failed(f"{copy.name}: cannot run {command[0]}: {error.strerror}") from None
    return result.returncode == 0, f"{result.stdout}{result.stderr}exited {result.returncode}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", help="the ref without the fix, e.g. HEAD~1 or research/watch-recovery")
    parser.add_argument("test", help="the test file, e.g. tests/browser_backup.py or watch/tests/preset-editor.cjs")
    parser.add_argument("names", nargs="*", help="test names in a unittest module, or the arguments a script takes")
    parser.add_argument("--runs", type=int, default=1, help="how many times each copy runs the test (default 1)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary copies and print where they are")
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="eucwatch-red-at-"))
    try:
        if args.runs < 1:
            raise compare.Failed("--runs must be at least 1")
        compare.require_dependencies(needs_frontend(args.test))
        commit = compare.git("rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}", allow_failure=True).strip()
        if not commit:
            raise compare.Failed(f"{args.base} is not a commit")
        base, tree = scratch / "base", scratch / "working-tree"
        base.mkdir()
        tree.mkdir()
        compare.export_base(commit, base)
        compare.export_working_tree(tree)
        for directory in TEST_DIRECTORIES:
            shutil.rmtree(base / directory, ignore_errors=True)
            if (tree / directory).is_dir():
                shutil.copytree(tree / directory, base / directory, symlinks=True)
        passed = {}
        for copy in (base, tree):
            prepare(copy, args.test)
            command = command_for(copy, args.test, args.names)
            passed[copy] = 0
            for number in range(1, args.runs + 1):
                ok, output = run_once(copy, command)
                print(f"{copy.name} run {number}: {'passed' if ok else 'failed'}", flush=True)
                if not ok and copy is base and passed[copy] == number - 1 and number == 1:
                    print("\n".join(output.strip().splitlines()[-SHOWN_LINES:]), flush=True)
                passed[copy] += ok
        failed_at_base, passed_in_tree = args.runs - passed[base], passed[tree]
        summary = (f"{failed_at_base} of {args.runs} runs failed there and "
                   f"{passed_in_tree} of {args.runs} passed in the working tree")
        if failed_at_base == args.runs and passed_in_tree == args.runs:
            print(f"red at {args.base}: {summary}")
            return 0
        print(f"not red at {args.base}: {summary}")
        return 1
    except compare.Failed as error:
        print(f"red-at: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # Exit 1 means not red only, so anything unforeseen is a failed run.
        print(f"red-at: the run failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    finally:
        if args.keep:
            print(f"kept: {scratch}", file=sys.stderr)
        else:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
