"""Icon and brand visual asset management for BSA Trading Bridge."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from PIL import Image
import customtkinter as ctk

from upstox_bridge.core.config import get_asset_path

logger = logging.getLogger(__name__)


class IconManager:
    """Manages high-resolution .ico visual assets and CTkImage instances."""

    _cache: Dict[Tuple[str, Tuple[int, int]], ctk.CTkImage] = {}

    @classmethod
    def get_ico_path(cls, name: str) -> Optional[Path]:
        """Resolve path to a specific .ico asset file."""
        candidates = [
            f"icons/{name}.ico",
            f"{name}.ico",
            f"icons/{name}.png",
            f"{name}.png",
        ]
        for rel in candidates:
            p = get_asset_path(rel)
            if p.exists():
                return p
        return None

    @classmethod
    def get_icon(cls, name: str, size: Tuple[int, int] = (16, 16)) -> Optional[ctk.CTkImage]:
        """
        Retrieve a cached ctk.CTkImage backed by an authentic .ico file.

        Args:
            name: Base name of icon (e.g. 'play', 'simulate', 'stop', 'bridge_logo', 'excel')
            size: Display size in logical pixels (width, height)
        """
        key = (name, size)
        if key in cls._cache:
            return cls._cache[key]

        ico_path = cls.get_ico_path(name)
        if not ico_path:
            logger.debug("Icon asset not found: %s", name)
            return None

        try:
            with Image.open(ico_path) as pil_img:
                pil_copy = pil_img.copy()
            ctk_img = ctk.CTkImage(light_image=pil_copy, dark_image=pil_copy, size=size)
            cls._cache[key] = ctk_img
            return ctk_img
        except Exception as e:
            logger.warning("Failed to load icon '%s' from %s: %s", name, ico_path, e)
            return None
