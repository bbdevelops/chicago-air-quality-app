import os
from pathlib import Path
from unittest import mock

from scripts._common import cache_is_fresh
from scripts._socrata import load_token


def test_cache_is_fresh(tmp_path: Path) -> None:
    # Test that cache_is_fresh returns False for missing files
    test_file = tmp_path / "test.csv"
    assert not cache_is_fresh(test_file, max_age_hours=24)

    # Test that cache_is_fresh returns True for newly created files
    test_file.touch()
    assert cache_is_fresh(test_file, max_age_hours=24)


def test_load_token_detects_placeholders() -> None:
    # 1.5 fix regression: make sure we correctly detect 'PASTE_YOUR_APP_TOKEN_HERE'
    # and 'YOUR_APP_TOKEN_HERE' placeholders
    with mock.patch.dict(os.environ, {"SOCRATA_APP_TOKEN": "YOUR_APP_TOKEN_HERE"}, clear=True):
        assert load_token("SOCRATA_APP_TOKEN", "SOCRATA_APP_SECRET") == (None, None)

    with mock.patch.dict(os.environ, {"SOCRATA_APP_TOKEN": "PASTE_YOUR_APP_TOKEN_HERE"}, clear=True):
        assert load_token("SOCRATA_APP_TOKEN", "SOCRATA_APP_SECRET") == (None, None)

    with mock.patch.dict(os.environ, {"SOCRATA_APP_TOKEN": "REAL_TOKEN", "SOCRATA_APP_SECRET": "REAL_SECRET"}, clear=True):
        assert load_token("SOCRATA_APP_TOKEN", "SOCRATA_APP_SECRET") == ("REAL_TOKEN", "REAL_SECRET")
