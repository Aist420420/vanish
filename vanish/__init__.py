"""Vanish — локальный разбор цифрового следа по архиву Gmail."""

from pathlib import Path

__version__ = "1.0.0"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
RESOURCES_DIR = PACKAGE_DIR / "resources"
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_DB = PROJECT_DIR / "state" / "vanish.db"
