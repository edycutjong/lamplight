"""find_fixtures — explicit > env > cwd > repo-root resolution order."""

from __future__ import annotations

import pytest

from lamplight_memory import paths


def test_explicit_path_wins(fixtures_root):
    # explicit argument is candidate #1, appended and resolved first
    got = paths.find_fixtures(fixtures_root)
    assert got == fixtures_root.resolve()


def test_env_var_used_when_no_explicit_arg(monkeypatch, fixtures_root):
    monkeypatch.delenv("LAMPLIGHT_FIXTURES", raising=False)
    monkeypatch.setenv("LAMPLIGHT_FIXTURES", str(fixtures_root))
    got = paths.find_fixtures(None)
    assert got == fixtures_root.resolve()


def test_explicit_beats_env(monkeypatch, fixtures_root, tmp_path):
    # a bogus env value must not be preferred over a valid explicit arg
    monkeypatch.setenv("LAMPLIGHT_FIXTURES", str(tmp_path / "nowhere"))
    got = paths.find_fixtures(fixtures_root)
    assert got == fixtures_root.resolve()


def test_repo_root_guess_points_at_checkout():
    root = paths.repo_root_guess()
    assert (root / "fixtures" / "ward_5day").exists()


def test_find_fixtures_raises_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.delenv("LAMPLIGHT_FIXTURES", raising=False)
    monkeypatch.chdir(tmp_path)
    # neutralize the last candidate (repo-root guess) too, so every
    # candidate genuinely misses and the function must raise.
    monkeypatch.setattr(paths, "repo_root_guess", lambda: tmp_path / "no-such-repo")
    with pytest.raises(FileNotFoundError):
        paths.find_fixtures(None)
