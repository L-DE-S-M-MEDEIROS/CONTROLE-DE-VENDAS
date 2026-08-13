from __future__ import annotations

import json
import os
from pathlib import Path


THEMES = {
    "dark": {
        "name": "Dark moderno",
        "description": "Grafite profundo com detalhes em azul neon",
        "navy": "#0B0F14",
        "navy_light": "#171D26",
        "accent": "#00A8FF",
        "accent_hover": "#38BBFF",
        "accent_pressed": "#0086CC",
        "cyan": "#37D7FF",
        "success": "#35C98A",
        "success_hover": "#28A972",
        "danger": "#FF6B72",
        "danger_bg": "#3A2027",
        "danger_hover": "#512931",
        "background": "#10151C",
        "panel": "#181E27",
        "text": "#F2F6F9",
        "muted": "#9CA8B5",
        "border": "#2B3440",
        "field": "#111720",
        "soft": "#202833",
        "soft_hover": "#2A3542",
        "heading": "#222C38",
        "selected": "#153C52",
        "nav_text": "#D9E4EC",
        "nav_muted": "#7E91A3",
        "hero_text": "#D8F3FF",
        "purple": "#A88BFF",
        "shadow": "#080B0F",
    },
    "light": {
        "name": "Light clean",
        "description": "Off-white elegante com detalhes em verde-oliva",
        "navy": "#30362C",
        "navy_light": "#414A3A",
        "accent": "#6F7C4B",
        "accent_hover": "#82915A",
        "accent_pressed": "#59643C",
        "cyan": "#718C7A",
        "success": "#617A49",
        "success_hover": "#52683E",
        "danger": "#B84A50",
        "danger_bg": "#F8E8E7",
        "danger_hover": "#F1D6D4",
        "background": "#F3F1EA",
        "panel": "#FFFEFA",
        "text": "#2E332D",
        "muted": "#70776C",
        "border": "#DDDCD2",
        "field": "#FFFFFF",
        "soft": "#ECEBE3",
        "soft_hover": "#E2E2D8",
        "heading": "#E8E9DE",
        "selected": "#E1E6D3",
        "nav_text": "#F3F4EF",
        "nav_muted": "#B9C2AF",
        "hero_text": "#F3F6EC",
        "purple": "#8174A0",
        "shadow": "#D8D6CB",
    },
}


def get_theme(key: str):
    return THEMES.get(key, THEMES["light"])


def preferred_font(root) -> str:
    try:
        from tkinter import font as tkfont

        installed = {name.casefold(): name for name in tkfont.families(root)}
        for candidate in ("Inter", "Roboto", "Montserrat", "Segoe UI"):
            if candidate.casefold() in installed:
                return installed[candidate.casefold()]
    except Exception:
        pass
    return "Segoe UI"


class ThemePreferences:
    def __init__(self, path: str | Path | None = None):
        default_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "ControleDeVendas"
        self.path = Path(path or default_dir / "configuracoes.json")

    def load(self) -> str:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            key = str(data.get("theme", "light"))
            return key if key in THEMES else "light"
        except (OSError, ValueError, TypeError):
            return "light"

    def save(self, key: str):
        if key not in THEMES:
            raise ValueError("Tema inválido.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"theme": key}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
