"""Watch-folder URL parsing and file-processing behavior."""
from __future__ import annotations

import asyncio
import os

from app.automation import _read_urls, _scan_once


def test_read_urls_ignores_blanks_and_comments(tmp_path):
    p = tmp_path / "list.txt"
    p.write_text("https://a\n# comment\n\n  https://b  \n")
    assert _read_urls(str(p)) == ["https://a", "https://b"]


def test_scan_renames_processed_file(tmp_path):
    # Comment-only file: no URLs, so no DB writes, but it must be marked done.
    p = tmp_path / "empty.txt"
    p.write_text("# nothing to import\n")
    asyncio.run(_scan_once(str(tmp_path), "%(title)s.%(ext)s"))
    assert not p.exists()
    assert any(name.endswith(".imported") for name in os.listdir(tmp_path))


def test_scan_noop_when_folder_missing():
    # Should not raise for a nonexistent folder.
    asyncio.run(_scan_once("/nonexistent/watch/folder", "%(title)s.%(ext)s"))
