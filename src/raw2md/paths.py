"""Locations under the ~/.raw2md service directory.

Service files live in the user's home directory, not at the install location, so
the same configuration applies regardless of how raw2md was installed.
"""

from pathlib import Path


def home_dir() -> Path:
    return Path.home() / ".raw2md"


def settings_file() -> Path:
    return home_dir() / "settings.json"


def prompts_file() -> Path:
    return home_dir() / "prompts.yaml"


def keywords_file() -> Path:
    return home_dir() / "keywords.yaml"


def state_dir() -> Path:
    return home_dir() / "state"


def lock_file() -> Path:
    return state_dir() / "lock"


def queue_file() -> Path:
    return state_dir() / "queue.json"


def rpd_file() -> Path:
    return state_dir() / "rpd.json"


def default_temp_dir() -> Path:
    return home_dir() / "tmp"


def logs_dir() -> Path:
    return home_dir() / "logs"
