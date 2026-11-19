"""Tests for the EnvManager .env reader and writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.env_manager import EnvManager


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    """Return a temporary .env file with two pre-populated keys."""
    f = tmp_path / ".env"
    f.write_text('EXISTING_KEY="old_value"\nOTHER_KEY="keep"\n')
    return f


def test_read_env_file(env_file: Path) -> None:
    """Reading should parse existing quoted values into a plain dict."""
    mgr = EnvManager(env_file)
    data = mgr.read()
    assert data["EXISTING_KEY"] == "old_value"
    assert data["OTHER_KEY"] == "keep"


def test_read_missing_file(tmp_path: Path) -> None:
    """Reading a non-existent file should return an empty dict."""
    mgr = EnvManager(tmp_path / "missing.env")
    assert mgr.read() == {}


def test_update_existing_key(env_file: Path) -> None:
    """Updating an existing key should overwrite it and leave others intact."""
    mgr = EnvManager(env_file)
    mgr.update({"EXISTING_KEY": "new_value"})
    data = mgr.read()
    assert data["EXISTING_KEY"] == "new_value"
    assert data["OTHER_KEY"] == "keep"


def test_add_new_key(env_file: Path) -> None:
    """Updating an unseen key should append it without disturbing existing keys."""
    mgr = EnvManager(env_file)
    mgr.update({"NEW_KEY": "new_value"})
    data = mgr.read()
    assert data["NEW_KEY"] == "new_value"
    assert data["EXISTING_KEY"] == "old_value"


def test_file_permissions_set_to_600(env_file: Path) -> None:
    """Writing should restrict the file permissions to owner read/write only."""
    mgr = EnvManager(env_file)
    mgr.update({"KEY": "val"})
    assert oct(env_file.stat().st_mode)[-3:] == "600"


def test_comments_preserved(tmp_path: Path) -> None:
    """Comment lines should survive an update unchanged."""
    f = tmp_path / ".env"
    f.write_text("# This is a comment\nKEY=value\n")
    mgr = EnvManager(f)
    mgr.update({"KEY": "new"})
    content = f.read_text()
    assert "# This is a comment" in content


def test_update_rejects_values_that_would_add_lines(tmp_path):
    env = EnvManager(tmp_path / ".env")
    env.update({"WIKIJS_URL": "http://wiki"})
    with pytest.raises(ValueError):
        env.update({"WIKIJS_API_TOKEN": "x\nAUTH_MODE=off"})
    assert env.read() == {"WIKIJS_URL": "http://wiki"}


@pytest.mark.parametrize("value", ['pa"ss"', "'quoted'", '"', "x'", " padded secret ", "a=b"])
def test_values_with_quotes_round_trip(tmp_path: Path, value: str) -> None:
    """A saved secret reads back byte for byte, even with quotes at either end."""
    mgr = EnvManager(tmp_path / ".env")
    mgr.update({"SECRET": value})
    assert mgr.read()["SECRET"] == value


def test_hand_written_quoting_still_reads(tmp_path: Path) -> None:
    """Unquoted, double-quoted and single-quoted lines all give the bare value."""
    f = tmp_path / ".env"
    f.write_text('A=plain\nB="double"\nC=\'single\'\nD = "spaced" \nE=""\n')
    assert EnvManager(f).read() == {
        "A": "plain",
        "B": "double",
        "C": "single",
        "D": "spaced",
        "E": "",
    }
