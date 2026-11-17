#!/usr/bin/env python3
"""How does the tracked evidence differ between a ref and the working tree?

Reads watch/evidence/** and docs/acceptance/evidence/** at <ref> and in the
working tree (tracked files with their uncommitted changes, plus untracked files
that are not ignored) and prints, for the commit message that explains a
regenerated-evidence diff:

  JSON differences   every changed field, by file. List indexes are collapsed
                     to [*], so a change repeated across list items prints once
                     with a count.
  Provenance only    JSON files whose only change is in the fields
                     scripts/evidence-compare.py ignores (the same list).
  PNG files          each changed PNG's sha256 at <ref> and in the working tree,
                     and every tracked file byte-identical to the new one.
  Other changes      added or removed files, SVG line counts, other bytes.

It only reads: nothing is regenerated and the working tree is not changed.
Exit 0: the report was printed. Exit 2: it could not be made.
"""

import argparse
import hashlib
import importlib.util
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("evidence_compare", Path(__file__).with_name("evidence-compare.py"))
compare = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare)

DIRECTORIES = [compare.WATCH_EVIDENCE, compare.BROWSER_EVIDENCE]
# Distinct changes shown for one collapsed field, and collapsed fields shown for one file.
SHOWN_CHANGES = 3
SHOWN_FIELDS = 12
VALUE_WIDTH = 80
INDEX = re.compile(r"\[\d+\]")
PROVENANCE_HEADING = ("Provenance only (the fields evidence-compare ignores: " + ", ".join(sorted(compare.PROVENANCE))
                      + "; bundle.json's version-derived names and its " + ", ".join(sorted(compare.BUNDLE_SIZES_AND_CHECKSUMS))
                      + ")")


def short(value) -> str:
    text = compare.rendered(value)
    return text if len(text) <= VALUE_WIDTH else text[:VALUE_WIDTH - 1] + "…"


def collapsed(relative: str, base: bytes, tree: bytes) -> list[str]:
    """The report lines for one changed JSON file: its changes grouped by field with
    list indexes collapsed. Empty if only provenance changed."""
    base, tree = compare.parsed(relative, "base", base), compare.parsed(relative, "working tree", tree)
    if Path(relative).name == "bundle.json":
        base, tree = compare.without_version(relative, "base", base), compare.without_version(relative, "working tree", tree)
    fields: dict[str, Counter] = {}
    for field, left, right in compare.json_differences(base, tree):
        fields.setdefault(INDEX.sub("[*]", field), Counter())[(short(left), short(right))] += 1
    lines = []
    for field, changes in list(fields.items())[:SHOWN_FIELDS]:
        total = sum(changes.values())
        ranked = changes.most_common()
        if len(ranked) == 1:
            (left, right), count = ranked[0]
            lines.append(f"    {field}: {'' if count == 1 else f'{count}× '}base {left}, working tree {right}")
            continue
        lines.append(f"    {field}: {total} changes")
        lines += [f"      {count}× base {left}, working tree {right}" for (left, right), count in ranked[:SHOWN_CHANGES]]
        if len(ranked) > SHOWN_CHANGES:
            more = len(ranked) - SHOWN_CHANGES
            lines.append(f"      … and {more} more distinct change{'' if more == 1 else 's'}")
    if len(fields) > SHOWN_FIELDS:
        more = len(fields) - SHOWN_FIELDS
        lines.append(f"    … and {more} more changed field{'' if more == 1 else 's'}")
    return lines


def explain(base: dict[str, bytes], tree: dict[str, bytes], identical_to) -> list[str]:
    """The report for evidence files at base and in the working tree, by path.

    identical_to(content) lists the tracked files whose bytes are content.
    """
    json_lines, provenance, png_lines, other = [], [], [], []
    changed = [path for path in sorted(base.keys() | tree.keys()) if base.get(path) != tree.get(path)]
    for path in changed:
        left, right = base.get(path), tree.get(path)
        if path.endswith(".png"):
            png_lines.append(f"  {path}")
            png_lines.append(f"    base         {hashlib.sha256(left).hexdigest() if left is not None else 'absent'}")
            png_lines.append(f"    working tree {hashlib.sha256(right).hexdigest() if right is not None else 'absent'}")
            if right is not None:
                same = [other_path for other_path in identical_to(right) if other_path != path]
                png_lines += [f"    identical to {other_path}" for other_path in same] or ["    identical to no other tracked file"]
        elif left is None or right is None:
            other.append(f"  {path}: only {'in the working tree' if left is None else 'at base'}")
        elif path.endswith(".json"):
            try:
                lines = collapsed(path, left, right)
            except compare.Failed as error:
                other.append(f"  {error}")
                continue
            if lines:
                json_lines += [f"  {path}", *lines]
            else:
                provenance.append(f"  {path}")
        elif path.endswith(".svg"):
            count = sum(1 for _ in compare.line_differences(left.decode().splitlines(), right.decode().splitlines()))
            other.append(f"  {path}: {count} changed line(s)")
        else:
            other.append(f"  {path}: bytes differ")
    report = []
    for heading, lines in [("JSON differences", json_lines), (PROVENANCE_HEADING, provenance),
                           ("PNG files", png_lines), ("Other changes", other)]:
        if lines:
            report += [heading, *lines, ""]
    report.append(f"{len(changed)} evidence file(s) differ" if changed else "no tracked evidence differs")
    return report


def git(*args) -> bytes:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if result.returncode:
        raise compare.Failed(f"git {' '.join(args)}: {result.stderr.decode().strip()}")
    return result.stdout


def at_commit(commit: str) -> dict[str, bytes]:
    """The evidence files at commit, read in one git cat-file batch."""
    entries = [line.split("\t", 1) for line in git("ls-tree", "-r", "-z", commit, "--", *DIRECTORIES).decode().split("\0") if line]
    blobs = [(path, info.split()[2]) for info, path in entries if info.split()[1] == "blob"]
    batch = subprocess.run(["git", "-C", str(ROOT), "cat-file", "--batch"], capture_output=True,
                           input="".join(f"{sha}\n" for _, sha in blobs).encode())
    if batch.returncode:
        raise compare.Failed(f"git cat-file --batch: {batch.stderr.decode().strip()}")
    contents, offset = {}, 0
    for path, _ in blobs:
        header_end = batch.stdout.index(b"\n", offset)
        size = int(batch.stdout[offset:header_end].split()[2])
        contents[path] = batch.stdout[header_end + 1:header_end + 1 + size]
        offset = header_end + 1 + size + 1
    return contents


def in_working_tree() -> dict[str, bytes]:
    listed = git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *DIRECTORIES).decode().split("\0")
    return {path: (ROOT / path).read_bytes() for path in listed if path and (ROOT / path).is_file()}


def tracked_identical_to():
    """identical_to for explain(): the tracked working-tree files with the same bytes."""
    by_size: dict[int, list[Path]] = {}
    for path in git("ls-files", "-z").decode().split("\0"):
        if path and (ROOT / path).is_file():
            by_size.setdefault((ROOT / path).stat().st_size, []).append(Path(path))

    def identical_to(content: bytes) -> list[str]:
        return sorted(path.as_posix() for path in by_size.get(len(content), []) if (ROOT / path).read_bytes() == content)
    return identical_to


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ref", help="the ref to compare the working tree with, e.g. HEAD or 6ddf5e5^")
    args = parser.parse_args()
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet", f"{args.ref}^{{commit}}"],
                                capture_output=True, text=True).stdout.strip()
        if not commit:
            raise compare.Failed(f"{args.ref} is not a commit")
        report = explain(at_commit(commit), in_working_tree(), tracked_identical_to())
    except compare.Failed as error:
        print(f"evidence-explain: {error}", file=sys.stderr)
        return 2
    print(f"Tracked evidence, {args.ref} ({commit[:7]}) against the working tree\n")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
