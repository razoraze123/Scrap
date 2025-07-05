import json
from pathlib import Path
from typing import Any, Dict


class SiteProfileManager:
    """Handle saving/loading of site profiles."""

    def __init__(self, directory: str = "profiles") -> None:
        self.dir = Path(directory)
        self.dir.mkdir(exist_ok=True)

    def load_profile(self, path: str | Path) -> Dict[str, Any]:
        """Return profile data from *path*."""
        p = Path(path)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_profile(self, path: str | Path, data: Dict[str, Any]) -> None:
        """Save *data* into *path* as JSON."""
        p = Path(path)
        try:
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def apply_profile_to_ui(self, profile: Dict[str, Any], main_window) -> None:
        """Apply CSS selectors from *profile* to the main window UI."""
        selectors = profile.get("selectors", {})
        if hasattr(main_window.page_images, "input_options"):
            main_window.page_images.input_options.setText(
                selectors.get("images", "")
            )
        if hasattr(main_window.page_images, "input_alt_json"):
            main_window.page_images.input_alt_json.setText(
                profile.get("sentences_file", "")
            )
        if hasattr(main_window.page_desc, "input_selector"):
            main_window.page_desc.input_selector.setText(
                selectors.get("description", "")
            )
        if hasattr(main_window.page_scrap, "input_selector"):
            main_window.page_scrap.input_selector.setText(
                selectors.get("collection", "")
            )

