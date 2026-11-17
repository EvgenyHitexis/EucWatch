#!/usr/bin/env python3
"""Did this change alter behavior? Compare evidence regenerated at a base ref with
evidence regenerated at the working tree.

Each side is exported to a temporary directory outside the repository: the base
with `git archive`, the working tree as its tracked files with their uncommitted
changes plus untracked files that are not ignored. Every suite and flow runs in
those copies with EUCWATCH_WRITE_EVIDENCE=1, so it writes the copy's evidence
paths and never the repository's.

In each copy the watch evidence directory is emptied and every watch suite that
the copy's check scripts list runs (scripts/check-watch.sh, or scripts/check.sh
in a base from before it existed). With --browser, the copy's acceptance
evidence directory is emptied too, and the copy's frontend is built and its
browser flows run before the watch suites, so the watch parity suites replay the
laptop traces those flows just wrote, not the committed ones. The two outputs
are compared file by file, ignoring only provenance: source_sha256,
fingerprints, trace_sha256, and the version-derived names, sizes and checksums
in bundle.json. Every remaining difference is printed. Both copies run on this
tree's ignored dependencies (the Python .venv and frontend/node_modules), so a
base with other locked dependencies runs on these.

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
# The regenerated evidence, at the same paths in each copy as in the repository.
WATCH_EVIDENCE = "watch/evidence"
BROWSER_EVIDENCE = "docs/acceptance/evidence"
# This tree's ignored dependencies, which both copies use.
VENV = "experiments/laptop-feasibility/.venv"
NODE_MODULES = "frontend/node_modules"


def files(directory: Path) -> set[str]:
    return {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}


# Provenance: hashes of the files that produced the evidence, not what they did.
PROVENANCE = {"source_sha256", "fingerprints", "trace_sha256"}
# In bundle.json the version is a hash of the watch sources, so the Storage names
# built from it, and the bundled files' sizes and checksums, change with any edit.
BUNDLE_SIZES_AND_CHECKSUMS = {"bytes", "required_bytes", "sha256", "crc32"}
ABSENT = object()


class Failed(Exception):
    """The comparison could not be made."""


def rendered(value) -> str:
    """A compared value as the report prints it: its JSON text, or `absent`."""
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


def parsed(relative: str, side: str, content: bytes):
    try:
        return json.loads(content)
    except ValueError as error:
        raise Failed(f"{relative}: the {side} copy is not valid JSON ({error})") from None


def file_differences(relative: str, base: bytes, tree: bytes) -> list[str]:
    if base == tree:
        return []
    if relative.endswith(".json"):
        base, tree = parsed(relative, "base", base), parsed(relative, "working tree", tree)
        if Path(relative).name == "bundle.json":
            base, tree = without_version(relative, "base", base), without_version(relative, "working tree", tree)
        return [f"{relative}: {field}: base {rendered(left)}, working tree {rendered(right)}"
                for field, left, right in json_differences(base, tree)]
    if relative.endswith(".svg"):
        return [f"{relative}: line {number}: base {rendered(left)}, working tree {rendered(right)}"
                for number, left, right in line_differences(base.decode().splitlines(), tree.decode().splitlines())]
    return [f"{relative}: bytes differ"]


def without_version(relative: str, side: str, bundle):
    """bundle.json with its version written as <version> and no sizes or checksums."""
    manifest = bundle.get("manifest") if isinstance(bundle, dict) else None
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        raise Failed(f"{relative}: the {side} copy has no manifest.version")

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


def git(*args, binary=False, allow_failure=False):
    """Run git in this repository. A failure raises Failed unless allow_failure is set."""
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if result.returncode and not allow_failure:
        raise Failed(f"git {' '.join(args)}: {result.stderr.decode().strip()}")
    return result.stdout if binary else result.stdout.decode()


def require_dependencies(browser: bool):
    """Fail before exporting anything if something both copies need is missing."""
    for relative in [VENV] + ([NODE_MODULES] if browser else []):
        if not (ROOT / relative).is_dir():
            raise Failed(f"{relative} is missing; run ./scripts/setup.sh")
    for command in ["node"] + (["npm"] if browser else []):
        if shutil.which(command) is None:
            raise Failed(f"{command} is not on PATH")


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


# The scripts that hold the suite and flow loops. A base from before #70 has no
# check-watch.sh: its watch suite loop is in check.sh.
CHECK_SCRIPTS = ["scripts/check.sh", "scripts/check-watch.sh"]


def listed(copy: Path, variable: str) -> list[str]:
    """The names a `for <variable> in ...; do` loop in the copy's check scripts runs."""
    for script in CHECK_SCRIPTS:
        path = copy / script
        match = re.search(rf"^\s*for {variable} in ([^;]+); do", path.read_text(), re.MULTILINE) if path.is_file() else None
        if match:
            return match.group(1).split()
    raise Failed(f"{copy.name}: no `for {variable} in ...` loop in {' or '.join(CHECK_SCRIPTS)}")


def run(copy: Path, command: list[str], **variables):
    """Run command in the copy with EUCWATCH_WRITE_EVIDENCE=1 and no other inherited EUCWATCH_* setting."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("EUCWATCH_")}
    try:
        result = subprocess.run(command, cwd=copy, env={**env, **variables, "EUCWATCH_WRITE_EVIDENCE": "1"},
                                capture_output=True, text=True)
    except OSError as error:
        raise Failed(f"{copy.name}: cannot run {command[0]}: {error.strerror}") from None
    if result.returncode:
        raise Failed(f"{copy.name}: {' '.join(command)} exited {result.returncode}\n{result.stdout}{result.stderr}")


def empty(directory: Path):
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)


def regenerate(copy: Path, browser: bool):
    """Regenerate the copy's evidence into empty directories."""
    # Dependencies are ignored, so neither export has them: use this tree's.
    venv = copy / VENV
    venv.symlink_to(ROOT / VENV, target_is_directory=True)
    empty(copy / WATCH_EVIDENCE)
    if browser:
        # The flows run first: they write the copy's laptop traces, and the watch
        # parity suites below replay those instead of the committed ones.
        empty(copy / BROWSER_EVIDENCE)
        (copy / NODE_MODULES).symlink_to(ROOT / NODE_MODULES, target_is_directory=True)
        run(copy, ["npm", "run", "build", "--prefix", "frontend"])
        for flow in listed(copy, "flow"):
            run(copy, [str(venv / "bin/python"), f"tests/{flow}.py"], PYTHONPATH="laptop:tests")
    for suite in listed(copy, "suite"):
        run(copy, ["node", f"watch/tests/{suite}.cjs"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", help="the base ref, e.g. HEAD or chore/retro-guardrails")
    parser.add_argument("--browser", action="store_true",
                        help="also compare the laptop browser flows' evidence (needs Chrome)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary copies and print where they are")
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="eucwatch-evidence-compare-"))
    try:
        require_dependencies(args.browser)
        commit = git("rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}", allow_failure=True).strip()
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
        for directory in compared:
            count += len(files(base / directory) | files(tree / directory))
            found += [f"{directory}/{difference}" for difference in differences(base / directory, tree / directory)]
        for difference in found:
            print(difference)
        names = " and ".join(compared)
        if found:
            print(f"{len(found)} difference(s) in {names} between {args.base} ({commit[:7]}) and the working tree")
            return 1
        print(f"no differences: {count} files in {names} match between {args.base} ({commit[:7]}) "
              "and the working tree, ignoring provenance")
        return 0
    except Failed as error:
        print(f"evidence-compare: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # Exit 1 means differences only, so anything unforeseen is a failed run.
        print(f"evidence-compare: the run failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    finally:
        if args.keep:
            print(f"kept: {scratch}", file=sys.stderr)
        else:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
