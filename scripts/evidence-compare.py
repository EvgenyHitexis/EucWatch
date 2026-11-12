#!/usr/bin/env python3
"""Did this change alter behavior? Compare evidence regenerated at a base ref with
evidence regenerated at the working tree.

Each side is exported to a temporary directory outside the repository: the base
with `git archive`, the working tree as its tracked files with their uncommitted
changes plus untracked files that are not ignored. In each copy the watch evidence
directory is emptied and every watch suite that copy's scripts/check.sh lists runs
with EUCWATCH_WRITE_EVIDENCE=1. With --browser, the copy's frontend is built and
its browser flows run without the flag, so they write into the copy's empty
.test-output/evidence/. The two outputs are compared file by file, ignoring only
provenance: source_sha256, fingerprints, trace_sha256, and the version-derived
names, sizes and checksums in bundle.json. Every remaining difference is printed.
Both copies run on this tree's ignored dependencies (the Python .venv and
frontend/node_modules), so a base with other locked dependencies runs on these.

Exit 0: no difference. Exit 1: differences. Exit 2: the run itself failed.
The repository is never written: git status and git worktree list are unchanged.
"""

import argparse
import difflib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Regenerated evidence in a copy, and the tracked directory it stands for.
WATCH_EVIDENCE = ("watch/evidence", "watch/evidence")
BROWSER_EVIDENCE = (".test-output/evidence", "docs/acceptance/evidence")


def files(directory: Path) -> set[str]:
    return {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}


# Provenance: hashes of the files that produced the evidence, not what they did.
PROVENANCE = {"source_sha256", "fingerprints", "trace_sha256"}
# In bundle.json the version is a hash of the watch sources, so the Storage names
# built from it, and the bundled files' sizes and checksums, change with any edit.
BUNDLE_SIZES_AND_CHECKSUMS = {"bytes", "required_bytes", "sha256", "crc32"}
ABSENT = object()


def shown(value) -> str:
    return "absent" if value is ABSENT else json.dumps(value, ensure_ascii=False)


def json_differences(base, tree, where="$"):
    """Yield (field, base value, working tree value) for every leaf that differs."""
    if isinstance(base, dict) and isinstance(tree, dict):
        for key in sorted((base.keys() | tree.keys()) - PROVENANCE):
            yield from json_differences(base.get(key, ABSENT), tree.get(key, ABSENT), f"{where}.{key}")
    elif isinstance(base, list) and isinstance(tree, list):
        for index, (left, right) in enumerate(itertools.zip_longest(base, tree, fillvalue=ABSENT)):
            yield from json_differences(left, right, f"{where}[{index}]")
    elif base != tree:
        yield where, base, tree


def file_differences(relative: str, base: bytes, tree: bytes) -> list[str]:
    if base == tree:
        return []
    if relative.endswith(".json"):
        base, tree = json.loads(base), json.loads(tree)
        if Path(relative).name == "bundle.json":
            base, tree = without_version(base), without_version(tree)
        return [f"{relative}: {field}: base {shown(left)}, working tree {shown(right)}"
                for field, left, right in json_differences(base, tree)]
    if relative.endswith(".svg"):
        return [f"{relative}: line {number}: base {shown(left)}, working tree {shown(right)}"
                for number, left, right in line_differences(base.decode().splitlines(), tree.decode().splitlines())]
    return [f"{relative}: bytes differ"]


def without_version(bundle):
    """bundle.json with its version written as <version> and no sizes or checksums."""
    version = bundle["manifest"]["version"]

    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key not in BUNDLE_SIZES_AND_CHECKSUMS}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value.replace(version, "<version>") if isinstance(value, str) else value
    return strip(bundle)


def line_differences(base: list[str], tree: list[str]):
    """Yield (line number, base line, working tree line) for every changed line."""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base, tree, autojunk=False).get_opcodes():
        if tag != "equal":
            for offset, (left, right) in enumerate(itertools.zip_longest(base[i1:i2], tree[j1:j2], fillvalue=ABSENT)):
                yield (i1 if left is not ABSENT else j1) + offset + 1, left, right


def differences(base: Path, tree: Path) -> list[str]:
    """Every difference between two regenerated evidence directories, by file."""
    found = []
    at_base, in_tree = files(base), files(tree)
    for relative in sorted(at_base | in_tree):
        if relative not in in_tree:
            found.append(f"{relative}: written only at base")
        elif relative not in at_base:
            found.append(f"{relative}: written only in the working tree")
        else:
            found += file_differences(relative, (base / relative).read_bytes(), (tree / relative).read_bytes())
    return found


class Failed(Exception):
    """The comparison could not be made."""


def git(*args, binary=False):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if result.returncode and "--quiet" not in args:
        raise Failed(f"git {' '.join(args)}: {result.stderr.decode().strip()}")
    return result.stdout if binary else result.stdout.decode()


def export_base(commit: str, copy: Path):
    archive = Path(tempfile.mkstemp(suffix=".tar", dir=copy.parent)[1])
    archive.write_bytes(git("archive", "--format=tar", commit, binary=True))
    with tarfile.open(archive) as tar:
        tar.extractall(copy, filter="data")
    archive.unlink()


def export_working_tree(copy: Path):
    for relative in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0"):
        source = ROOT / relative
        if relative and (source.is_file() or source.is_symlink()):
            (copy / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy / relative, follow_symlinks=False)


def listed(copy: Path, variable: str) -> list[str]:
    """The names a `for <variable> in ...; do` loop in the copy's scripts/check.sh runs."""
    match = re.search(rf"^\s*for {variable} in ([^;]+); do", (copy / "scripts/check.sh").read_text(), re.MULTILINE)
    if not match:
        raise Failed(f"{copy.name}: scripts/check.sh has no `for {variable} in ...` loop")
    return match.group(1).split()


def run(copy: Path, command: list[str], **variables):
    """Run command in the copy with no inherited EUCWATCH_* settings."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("EUCWATCH_")}
    result = subprocess.run(command, cwd=copy, env={**env, **variables}, capture_output=True, text=True)
    if result.returncode:
        raise Failed(f"{copy.name}: {' '.join(command)} exited {result.returncode}\n{result.stdout}{result.stderr}")


def regenerate(copy: Path, browser: bool):
    """Regenerate the copy's evidence into empty directories."""
    # Dependencies are ignored, so neither export has them: use this tree's.
    venv = copy / "experiments/laptop-feasibility/.venv"
    venv.symlink_to(ROOT / "experiments/laptop-feasibility/.venv", target_is_directory=True)
    shutil.rmtree(copy / WATCH_EVIDENCE[0], ignore_errors=True)
    (copy / WATCH_EVIDENCE[0]).mkdir(parents=True)
    for suite in listed(copy, "suite"):
        run(copy, ["node", f"watch/tests/{suite}.cjs"], EUCWATCH_WRITE_EVIDENCE="1")
    if browser:
        if "def evidence_directory" not in (copy / "tests/support.py").read_text():
            raise Failed(f"{copy.name}: --browser needs browser flows that write .test-output/evidence/ (#65)")
        (copy / "frontend/node_modules").symlink_to(ROOT / "frontend/node_modules", target_is_directory=True)
        run(copy, ["npm", "run", "build", "--prefix", "frontend"])
        for flow in listed(copy, "flow"):
            run(copy, [str(venv / "bin/python"), f"tests/{flow}.py"], PYTHONPATH="laptop:tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", help="the base ref, e.g. HEAD or chore/retro-guardrails")
    parser.add_argument("--browser", action="store_true",
                        help="also compare the laptop browser flows' evidence (needs Chrome)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary copies and print where they are")
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="eucwatch-evidence-compare-"))
    try:
        commit = git("rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}").strip()
        if not commit:
            raise Failed(f"{args.base} is not a commit")
        base, tree = scratch / "base", scratch / "working-tree"
        base.mkdir()
        tree.mkdir()
        export_base(commit, base)
        export_working_tree(tree)
        compared = [WATCH_EVIDENCE] + ([BROWSER_EVIDENCE] if args.browser else [])
        for copy in (base, tree):
            print(f"regenerating evidence: {copy.name}", flush=True)
            regenerate(copy, args.browser)
        found, count = [], 0
        for directory, shown_as in compared:
            count += len(files(base / directory) | files(tree / directory))
            found += [f"{shown_as}/{difference}" for difference in differences(base / directory, tree / directory)]
        for difference in found:
            print(difference)
        names = " and ".join(shown_as for _, shown_as in compared)
        if found:
            print(f"{len(found)} difference(s) in {names} between {args.base} ({commit[:7]}) and the working tree")
            return 1
        print(f"no differences: {count} files in {names} match between {args.base} ({commit[:7]}) "
              "and the working tree, ignoring provenance")
        return 0
    except Failed as error:
        print(f"evidence-compare: {error}", file=sys.stderr)
        return 2
    finally:
        if args.keep:
            print(f"kept: {scratch}", file=sys.stderr)
        else:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
