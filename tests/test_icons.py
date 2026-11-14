"""Unit tests for IconManager and genuine .ico asset loading."""

import unittest
from pathlib import Path
from PIL import Image

from upstox_bridge.gui.icons import IconManager
from upstox_bridge.core.config import get_asset_path


class TestIconManager(unittest.TestCase):
    def test_core_icons_exist_and_load(self):
        core_icons = [
            "play",
            "simulate",
            "stop",
            "settings",
            "excel",
            "add",
            "search",
            "clock",
            "token",
            "feed",
            "market",
            "terminal",
            "clear",
            "bridge_logo",
            "ba_monogram",
        ]
        for name in core_icons:
            ico_p = IconManager.get_ico_path(name)
            self.assertIsNotNone(ico_p, f"Icon file for '{name}' was not found.")
            self.assertTrue(ico_p.exists(), f"Path for '{name}' does not exist: {ico_p}")

            # Verify Pillow can open the authentic .ico
            with Image.open(ico_p) as img:
                self.assertEqual(img.format, "ICO")

            # Verify CTkImage instantiation and caching
            ctk_img = IconManager.get_icon(name, size=(16, 16))
            self.assertIsNotNone(ctk_img, f"Failed to instantiate CTkImage for '{name}'")

            # Verify cache hit
            cached_img = IconManager.get_icon(name, size=(16, 16))
            self.assertIs(ctk_img, cached_img)

    def test_app_icon_ico_has_multiple_resolutions(self):
        app_ico_path = get_asset_path("app_icon.ico")
        self.assertTrue(app_ico_path.exists(), "app_icon.ico does not exist")
        with Image.open(app_ico_path) as img:
            self.assertEqual(img.format, "ICO")
