"""Local playlist registry stored as JSON."""

import json
import os
import tempfile
from pathlib import Path

STORE_FILE = Path(
    os.environ.get("SONORA_HOME", Path.home() / ".local/share/sonora")
) / "playlists.json"


class PlaylistError(Exception):
    """Raised for invalid playlist indices and corrupted storage."""


def load() -> dict:
    """Return {"playlists": [...], "active": int or None}."""
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"playlists": [], "active": None}
    except (json.JSONDecodeError, OSError):
        raise PlaylistError(
            f"cannot read playlist store at {STORE_FILE}; "
            "delete the file or restore it to valid JSON"
        )
    if not isinstance(data, dict) or not isinstance(data.get("playlists", []), list):
        raise PlaylistError(
            f"playlist store at {STORE_FILE} is corrupted; delete it to reset"
        )
    data.setdefault("playlists", [])
    if data.get("active") is not None and not _is_valid_index(data["active"], data["playlists"]):
        data["active"] = None
    return data


def save(data: dict) -> None:
    """Atomically write the registry, leaving it uncorrupted on failure."""
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STORE_FILE.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STORE_FILE)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise PlaylistError(f"cannot write playlist store at {STORE_FILE}")


def _is_valid_index(index, playlists: list) -> bool:
    return isinstance(index, int) and 0 <= index < len(playlists)


def add(store: dict, playlist: dict) -> bool:
    """Register a fetched playlist; return False if the URL already exists."""
    if any(p["id"] == playlist["id"] for p in store["playlists"]):
        return False
    store["playlists"].append(playlist)
    if store["active"] is None:
        store["active"] = len(store["playlists"]) - 1
    save(store)
    return True


def remove(store: dict, index: int) -> dict:
    """Remove the playlist at index; fix the active reference. Raise on bad index."""
    if not _is_valid_index(index, store["playlists"]):
        raise PlaylistError(f"invalid playlist index: {index}")
    removed = store["playlists"].pop(index)
    active = store["active"]
    if active is not None:
        if active == index:
            store["active"] = None
        elif active > index:
            store["active"] = active - 1
    save(store)
    return removed


def use(store: dict, index: int) -> dict:
    """Set the active playlist; return the newly selected playlist."""
    if not _is_valid_index(index, store["playlists"]):
        raise PlaylistError(f"invalid playlist index: {index}")
    store["active"] = index
    save(store)
    return store["playlists"][index]


def active_playlist(store: dict) -> dict | None:
    """Return the active playlist, or None when nothing is active."""
    index = store.get("active")
    if _is_valid_index(index, store["playlists"]):
        return store["playlists"][index]
    return None
