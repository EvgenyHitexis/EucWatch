"""Evidence manifests still describe the files on disk (#72).

An acceptance pass records the sha256 of each evidence file it produced in its
manifest under docs/acceptance/evidence/: an `artifact_sha256` map keyed by
repository-relative paths, or (the laptop-31 pass) an `artifacts_sha256` map
keyed by paths relative to the manifest's own directory. A browser
flow or watch suite that later regenerates one of those files in place changes
it under the earlier pass. That must be said in the same manifest: a
`superseded` entry for the path records the file's current sha256 and the commit
that changed it. The originally recorded hash stays as it was.

`source_sha256` and `final_source_sha256` record the code a pass ran on, which
is expected to change, so they are not checked.
"""
import json
import tempfile
import unittest
from pathlib import Path

from support import ROOT, sha256

EVIDENCE = 'docs/acceptance/evidence'


# Each artifact map's key, and whether its paths start from the manifest's directory.
ARTIFACT_MAPS = {'artifact_sha256': False, 'artifacts_sha256': True}


def artifact_maps(value):
    """(mapping, key) for every mapping in a manifest that holds an artifact map, however deeply nested."""
    if isinstance(value, dict):
        for key in ARTIFACT_MAPS:
            if isinstance(value.get(key), dict):
                yield value, key
        for item in value.values():
            yield from artifact_maps(item)
    elif isinstance(value, list):
        for item in value:
            yield from artifact_maps(item)


def manifest_problems(root):
    """Each artifact map entry under root/docs/acceptance/evidence/ that no longer
    matches its file and has no superseded entry for the file as it is now."""
    problems = []
    for manifest in sorted((root / EVIDENCE).rglob('*.json')):
        name = manifest.relative_to(root).as_posix()
        try:
            content = json.loads(manifest.read_text())
        except ValueError as error:
            # A manifest that no longer parses would otherwise drop its artifact_sha256 from the check.
            problems.append(f'{name}: not valid JSON ({error})')
            continue
        for holder, key in artifact_maps(content):
            base = manifest.parent if ARTIFACT_MAPS[key] else root
            superseded = holder.get('superseded', {})
            for path in sorted(set(superseded) - set(holder[key])):
                problems.append(f'{name}: {path}: superseded, but not in {key}')
            for path, recorded in sorted(holder[key].items()):
                file = base / path
                if not file.is_file():
                    problems.append(f'{name}: {path}: missing')
                    continue
                actual = sha256(file.read_bytes())
                entry = superseded.get(path)
                if entry is None:
                    if actual != recorded:
                        problems.append(f'{name}: {path}: sha256 is {actual}, {key} records {recorded}; '
                                        'restore the file or add a superseded entry naming the commit that changed it')
                elif not isinstance(entry, dict) or not entry.get('sha256') or not entry.get('commit'):
                    problems.append(f'{name}: {path}: its superseded entry needs a sha256 and a commit')
                elif actual != entry['sha256']:
                    problems.append(f'{name}: {path}: sha256 is {actual}, its superseded entry records '
                                    f"{entry['sha256']} (commit {entry['commit']}); the file changed again")
    return problems


class TrackedManifestTests(unittest.TestCase):
    def test_every_recorded_artifact_matches_its_file_or_is_superseded(self):
        self.assertEqual(manifest_problems(ROOT), [])


class ManifestCheckTests(unittest.TestCase):
    """The check on temporary manifests, never the tracked ones."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.png = 'docs/acceptance/evidence/touch-layout/invalid-save.png'
        self.json = 'watch/evidence/touch-layout/editor.json'
        self.write(self.png, b'first frame')
        self.write(self.json, b'{"states": []}\n')
        self.manifest = {'checks': [], 'source_sha256': {'laptop/eucwatch/application.py': 'not checked'},
                         'artifact_sha256': {self.png: sha256(b'first frame'),
                                             self.json: sha256(b'{"states": []}\n')}}

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def problems(self, manifest='docs/acceptance/evidence/touch-layout/validation.json'):
        self.write(manifest, json.dumps(self.manifest).encode())
        return manifest_problems(self.root)

    def test_a_manifest_whose_artifacts_match_has_no_problems(self):
        self.assertEqual(self.problems(), [])

    def test_an_edited_artifact_names_the_manifest_and_path(self):
        self.write(self.png, b'regenerated frame')
        self.assertEqual(len(self.problems()), 1)
        self.assertTrue(self.problems()[0].startswith(
            f'docs/acceptance/evidence/touch-layout/validation.json: {self.png}: sha256 is {sha256(b"regenerated frame")}'))

    def test_a_deleted_artifact_names_the_manifest_and_path(self):
        (self.root / self.json).unlink()
        self.assertEqual(self.problems(), [f'docs/acceptance/evidence/touch-layout/validation.json: {self.json}: missing'])

    def test_a_superseded_entry_acknowledges_the_file_as_it_is_now(self):
        self.write(self.png, b'regenerated frame')
        self.manifest['superseded'] = {self.png: {'sha256': sha256(b'regenerated frame'), 'commit': '6ddf5e5'}}
        self.assertEqual(self.problems(), [])

    def test_a_superseded_file_that_changes_again_fails(self):
        self.write(self.png, b'regenerated again')
        self.manifest['superseded'] = {self.png: {'sha256': sha256(b'regenerated frame'), 'commit': '6ddf5e5'}}
        problems = self.problems()
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith(f'docs/acceptance/evidence/touch-layout/validation.json: {self.png}: '))
        self.assertIn('the file changed again', problems[0])

    def test_a_superseded_entry_must_name_its_commit(self):
        self.write(self.png, b'regenerated frame')
        self.manifest['superseded'] = {self.png: {'sha256': sha256(b'regenerated frame')}}
        self.assertEqual(self.problems(), [f'docs/acceptance/evidence/touch-layout/validation.json: {self.png}: '
                                           'its superseded entry needs a sha256 and a commit'])

    def test_a_superseded_entry_for_an_unrecorded_path_fails(self):
        self.manifest['superseded'] = {'watch/evidence/other.json': {'sha256': 'aa', 'commit': '6ddf5e5'}}
        self.assertEqual(self.problems(), ['docs/acceptance/evidence/touch-layout/validation.json: '
                                           'watch/evidence/other.json: superseded, but not in artifact_sha256'])

    def test_a_manifest_that_is_not_valid_json_fails_rather_than_going_unchecked(self):
        self.write('docs/acceptance/evidence/touch-layout/review.json', b'{"artifact_sha256": {')
        problems = self.problems()
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith('docs/acceptance/evidence/touch-layout/review.json: not valid JSON'))

    def test_artifacts_sha256_paths_are_relative_to_their_manifest(self):
        # The laptop-31 pass names its files from its own directory.
        self.write('docs/acceptance/evidence/laptop-31/launch.json', b'{"outcome": "passed"}\n')
        manifest = 'docs/acceptance/evidence/laptop-31/validation.json'
        self.write(manifest, json.dumps({'artifacts_sha256': {
            'launch.json': sha256(b'{"outcome": "passed"}\n'), 'replay.json': 'gone'}}).encode())
        self.assertEqual(self.problems(), [f'{manifest}: replay.json: missing'])
        self.write('docs/acceptance/evidence/laptop-31/launch.json', b'{"outcome": "failed"}\n')
        self.assertEqual([problem.split(': ')[:2] for problem in self.problems()],
                         [[manifest, 'launch.json'], [manifest, 'replay.json']])

    def test_nested_maps_in_any_manifest_are_found_and_source_hashes_are_not_checked(self):
        self.manifest['source_sha256'] = {self.png: 'stale'}
        self.manifest['final_source_sha256'] = {self.png: 'stale'}
        nested = {'passes': [{'artifact_sha256': {self.png: 'stale'}}]}
        self.write('docs/acceptance/evidence/local-presets/review.json', json.dumps(nested).encode())
        self.assertEqual([problem.split(': ')[:2] for problem in self.problems()],
                         [['docs/acceptance/evidence/local-presets/review.json', self.png]])


if __name__ == '__main__':
    unittest.main()
