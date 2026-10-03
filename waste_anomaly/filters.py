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
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .frozen import exe_dir, is_frozen


# ============================================================
# DEFAULT PROFILE PATH
# ============================================================

def profiles_path() -> Path:
    """Jalur filters.json (dinamis — v2.4.1 frozen-aware).

    Dev: repo root. Frozen exe: BERDAMPINGAN dengan exe — dulu resolve dari
    ``__file__`` yang menunjuk _MEIPASS temp (dihapus saat exit → profil
    filter user hilang senyap di mode exe).
    """
    if is_frozen():
        return exe_dir() / "filters.json"
    return Path(__file__).resolve().parent.parent / "filters.json"


PROFILES_PATH = profiles_path()


# ============================================================
# LOAD / SAVE
# ============================================================

def _backup_corrupt_file(p: Path) -> None:
    """Rename file filters korup ke .bak (suffix timestamp bila .bak sudah ada).

    Supaya file korup tidak menahan profile baru selamanya (sebelumnya load
    terus gagal dan save berikutnya menimpanya — profile lama hilang tanpa
    jejak). Best-effort: kegagalan rename diabaikan (load tetap return {}).
    """
    try:
        bak = p.with_name(p.name + ".bak")
        if bak.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            bak = p.with_name(f"{p.name}.bak.{stamp}")
        os.replace(p, bak)
    except OSError:
        pass


def load_profiles(path: Path | str | None = None) -> dict[str, dict]:
    """Muat semua profiles dari JSON file. Return dict {name: profile_dict}.

    File korup (JSONDecodeError) di-rename ke <name>.bak dulu — lihat
    _backup_corrupt_file — lalu return {} (mulai bersih, tidak crash).
    """
    p = Path(path) if path else profiles_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("profiles", {}) if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        _backup_corrupt_file(p)
        return {}
    except OSError:
        return {}


def save_profiles(profiles: dict[str, dict], path: Path | str | None = None) -> bool:
    """Simpan dict profiles ke JSON file (atomic — M8).

    Tulis ke ``filters.json.tmp`` lalu ``os.replace`` ke tujuan, sehingga
    proses yang terputus di tengah menulis tidak meninggalkan filters.json
    korup (profile lama tetap utuh sampai replace berhasil).
    """
    p = Path(path) if path else profiles_path()
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"profiles": profiles}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)  # atomic pada filesystem yang sama
        return True
    except OSError:
        # Bersihkan tmp yang tertinggal bila replace gagal (mis. file terkunci)
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


# ============================================================
# CRUD OPERATIONS
# ============================================================

def save_profile(name: str, profile: dict, path: Path | str | None = None) -> bool:
    """Simpan 1 profile dengan nama tertentu. Update kalau sudah ada.

    Dict caller di-copy dulu (M8/L) — save_profile tidak lagi memutasi input.
    """
    profiles = load_profiles(path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    profile = dict(profile)  # jangan mutasi dict milik caller
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
