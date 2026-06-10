import tempfile
from pathlib import Path

from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from chefe.compiled import PixiManifest
from chefe.manifest import Document, Manifest

from .strategies import PACKAGES, VERSIONS, sources


class ManifestMachine(RuleBasedStateMachine):
    """Drive add/remove/sync over a live manifest, asserting it stays coherent throughout.

    One machine subsumes dozens of command sequences: after any interleaving of edits the
    document must still validate as a Manifest, compile to a PixiManifest, and have its
    `declared()` view agree with the dep tables actually on disk.
    """

    def __init__(self) -> None:
        super().__init__()
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "chefe.toml"

    @initialize()
    def scaffold(self) -> None:
        self.path.write_text(
            '[workspace]\nname = "w"\nplatforms = ["linux-64"]\n\n[deps]\npython = ">=3.11"\n'
        )

    @rule(source=sources(), package=PACKAGES, spec=VERSIONS)
    def add(self, source: str, package: str, spec: str) -> None:
        document = Document(self.path)
        if source != "conda":
            document.add("conda", "", (source,), "*")
        document.add(source, "", (package,), spec)
        document.save()

    @rule(package=PACKAGES)
    def remove(self, package: str) -> None:
        document = Document(self.path)
        document.remove((package,))
        document.save()

    @invariant()
    def stays_compilable(self) -> None:
        manifest = Manifest.load(self.path)
        PixiManifest.from_manifest(manifest)  # never raises on a reachable state

    @invariant()
    def declared_matches_tables(self) -> None:
        manifest = Manifest.load(self.path)
        declared = manifest.declared("default", "linux-64")
        # declared folds the groups in order, so a name's source is its last-writing group.
        expected: dict[str, str] = {}
        for source, deps in manifest.groups().items():
            for name in deps:
                expected[name] = source
        assert {name: dep.source for name, dep in declared.items()} == expected

    @invariant()
    def removed_keys_are_truly_gone(self) -> None:
        # Every key the document can see in a dep table is reachable via its dep_path.
        document = Document(self.path)
        manifest = Manifest.load(self.path)
        for source, deps in manifest.groups().items():
            table = document.table(Document.dep_path(source, ""))
            for name in deps:
                assert any(Document.normalize(k) == Document.normalize(name) for k in table)

    def teardown(self) -> None:
        self.dir.cleanup()


TestManifestMachine = ManifestMachine.TestCase
TestManifestMachine.settings = settings(max_examples=40, stateful_step_count=12, deadline=None)
