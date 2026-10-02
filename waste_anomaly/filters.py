"""
filters.py — persistence layer untuk filter profiles.

Simpan/muat state filter dashboard ke JSON file. Berguna untuk:
  - Save profile "Prioritas PWKTAM" supaya bisa di-load lagi besok
  - Save profile "WASTE Cancel Nota" untuk audit recurring
  - Multiple profiles dengan nama custom

Format JSON:
{
  "profiles": {
    "Prioritas PWKTAM": {
      "search": "",
      "cabang": "RESTO.PWKTAM",
      "item": null,
      "jenis": ["WASTE"],
      "keterangan": null,
      "status": "Prioritas Tinggi",
      "day_min": 1,
      "day_max": 31,
      "created": "2024-01-01 10:00:00",
      "updated": "2024-01-01 10:30:00"
    }
  }
}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# DEFAULT PROFILE PATH
# ============================================================

PROFILES_PATH = Path(__file__).resolve().parent.parent / "filters.json"


# ============================================================
# LOAD / SAVE
# ============================================================

def load_profiles(path: Path | str | None = None) -> dict[str, dict]:
    """Muat semua profiles dari JSON file. Return dict {name: profile_dict}."""
    p = Path(path) if path else PROFILES_PATH
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("profiles", {}) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_profiles(profiles: dict[str, dict], path: Path | str | None = None) -> bool:
    """Simpan dict profiles ke JSON file."""
    p = Path(path) if path else PROFILES_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"profiles": profiles}, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# ============================================================
# CRUD OPERATIONS
# ============================================================

def save_profile(name: str, profile: dict, path: Path | str | None = None) -> bool:
    """Simpan 1 profile dengan nama tertentu. Update kalau sudah ada."""
    profiles = load_profiles(path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    profile["updated"] = now
    if name not in profiles:
        profile["created"] = now
    else:
        # Preserve original created date
        profile["created"] = profiles[name].get("created", now)
    profiles[name] = profile
    return save_profiles(profiles, path)


def delete_profile(name: str, path: Path | str | None = None) -> bool:
    """Hapus profile berdasarkan nama. Return True kalau berhasil/exists."""
    profiles = load_profiles(path)
    if name not in profiles:
        return False
    del profiles[name]
    return save_profiles(profiles, path)


def get_profile(name: str, path: Path | str | None = None) -> dict | None:
    """Ambil 1 profile by name."""
    profiles = load_profiles(path)
    return profiles.get(name)


def list_profile_names(path: Path | str | None = None) -> list[str]:
    """List semua nama profile (sorted by name)."""
    profiles = load_profiles(path)
    return sorted(profiles.keys())


# ============================================================
# SNAPSHOT BUILDER — capture current filter state
# ============================================================

def snapshot_filters(
    search: str = "",
    cabang: str | None = None,
    item: str | None = None,
    jenis: list[str] | None = None,
    keterangan: str | None = None,
    status: str | None = None,
    day_min: int | None = None,
    day_max: int | None = None,
) -> dict:
    """Buat snapshot dict dari state filter aktif."""
    return {
        "search": search,
        "cabang": cabang,
        "item": item,
        "jenis": jenis or [],
        "keterangan": keterangan,
        "status": status,
        "day_min": day_min,
        "day_max": day_max,
    }


def restore_filters(profile: dict) -> dict:
    """Restore profile dict ke state filter. Return kwargs untuk apply."""
    return {
        "search": profile.get("search", ""),
        "cabang": profile.get("cabang"),
        "item": profile.get("item"),
        "jenis": profile.get("jenis", []),
        "keterangan": profile.get("keterangan"),
        "status": profile.get("status"),
        "day_min": profile.get("day_min"),
        "day_max": profile.get("day_max"),
    }
