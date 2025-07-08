import logging
from pathlib import Path

from site_profile_manager import SiteProfileManager


def test_load_profile_logs_warning(tmp_path, caplog):
    bad = tmp_path / "bad.json"
    bad.write_text("{ bad json }", encoding="utf-8")

    spm = SiteProfileManager(tmp_path)
    with caplog.at_level(logging.WARNING):
        data = spm.load_profile(bad)

    assert data == {}
    assert any("Failed to load profile" in record.message for record in caplog.records)
