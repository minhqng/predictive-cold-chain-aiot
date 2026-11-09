import subprocess

import pytest

from scripts.export_s1 import clean_backend_commit


@pytest.fixture
def export_checkout(tmp_path):
    git = ["git", "-C", str(tmp_path)]
    subprocess.run([*git, "init", "-q"], check=True)
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "tracked.py").write_text("value = 1\n")
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([
        *git, "-c", "user.name=ColdGuard Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "test: initialize disposable fixture",
    ], check=True)
    return backend, subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()


@pytest.mark.parametrize("state", ["staged", "unstaged", "untracked"])
def test_export_rejects_backend_changes(export_checkout, state):
    backend, _ = export_checkout
    source = backend / ("untracked.py" if state == "untracked" else "tracked.py")
    source.write_text("value = 2\n")
    if state == "staged":
        subprocess.run(["git", "-C", str(backend.parent), "add", str(source)], check=True)
    with pytest.raises(ValueError, match="commit backend changes"):
        clean_backend_commit(backend.parent)


def test_export_accepts_clean_backend_and_ignores_caches(export_checkout):
    backend, expected = export_checkout
    assert clean_backend_commit(backend.parent) == expected
    cache = backend / "__pycache__"
    cache.mkdir()
    (cache / "fixture.pyc").write_bytes(b"cached")
    (backend.parent / "outside-backend.md").write_text("outside backend scope")
    assert clean_backend_commit(backend.parent) == expected


def test_export_fails_closed_when_git_cannot_resolve_commit(tmp_path):
    with pytest.raises(ValueError, match="cannot verify backend Git provenance"):
        clean_backend_commit(tmp_path)
