"""followup.py — daftar follow-up baris anomali (v2.12.0).

Konsep: user mencentang baris mencurigakan di tabel Anomali → baris
terkumpul di tab "Follow Up" dalam format rekap (TOTAL · AVG · MAX ·
SOURCE DATA · JENIS · KETERANGAN · NAMA BARANG · NAMA RESTO · SATUAN ·
hari 1..31) — persis kolom inti DATA_WASTE, tanpa agregasi baru (nilai
tampil apa adanya dari barisnya; skor anomali TIDAK diubah).

Modul murni (tanpa Qt) — dipakai ui/state.py + view:

- ``fingerprint_series(df)`` — identitas baris STABIL lintas sesi:
  md5 atas 6 kolom kunci + nilai hari '1'..'31'. Kenapa BUKAN kunci
  bisnis saja: data asli memuat baris KEMBAR (diukur 25.901 baris:
  1.871 grup duplikat, maks 8 baris/grup — 3.760 identik nilai).
  Sidik jari nilai membedakan kembar yang nilainya beda; kembar yang
  PERSIS identik otomatis menyatu (didedup di select_followup_rows).
  Stabilitas dtype: kolom hari dinormalisasi float64 SEBELUM str
  (5 vs 5.0 lintas file → sidik jari sama).
- ``select_followup_rows(df, fps, keys)`` — baris ber-sidik jari ∈ keys
  + dedup kembar (keep first).
- ``suspicious_days(df, fps)`` — hari mencurigakan per baris utk
  penandaan warna (merah = HARI TERSANGKA/HARI MAX — konsisten peta
  hari pop-up detail; amber = nilai ≥ 2× rata-rata HARI AKTIF —
  lonjakan sekunder).
- ``load/save_followup_keys`` — persistensi followup.json (pola
  filters.json: atomic write + backup file korup + frozen-aware path).
- ``export_followup_xlsx`` — sheet "FOLLOW UP": kolom format rekap +
  3 kolom serah-terima kosong (PIC/KATEGORI/PENYEBAB — diisi petugas,
  konvensi REKAP MENTAH); hari mencurigakan diberi fill merah/amber.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .frozen import exe_dir, is_frozen

_LOG = logging.getLogger("waste_anomaly.followup")

# 6 kolom kunci rekap (urutan konvensi M code — group_keys_full).
KEY_COLS = [
    "SOURCE DATA", "JENIS", "KETERANGAN",
    "NAMA BARANG", "NAMA RESTO", "SATUAN",
]
# Kolom hari (dinormalisasi '1'..'31').
DAY_COLS = [str(i) for i in range(1, 32)]

# Kolom identitas tersembunyi di df tampilan (disembunyikan via
# visible_cols — ikut travel saat model di-sort).
FP_COL = "__FP"
CHECK_COL = "✓"

# Format tabel Follow Up — urutan PERSIS permintaan user (v2.12.0):
# TOTAL AVG MAX SOURCE DATA JENIS KETERANGAN NAMA BARANG NAMA RESTO
# SATUAN 1..31.
FOLLOWUP_COLS = [
    "TOTAL", "AVG", "MAX", "SOURCE DATA", "JENIS", "KETERANGAN",
    "NAMA BARANG", "NAMA RESTO", "SATUAN",
]
# Kolom serah-terima kosong di export (diisi petugas follow-up —
# konvensi sheet REKAP MENTAH).
HANDOVER_COLS = ["PIC", "KATEGORI", "PENYEBAB TERJADINYA WASTE"]

# Warna penanda hari (hex tanpa '#'; konsisten peta hari pop-up detail
# view_anomali._day_map: merah #fee2e2/#dc2626; amber = amber-100).
RED_BG, RED_FG = "FEE2E2", "DC2626"
AMBER_BG = "FEF3C7"


# ============================================================
# SIDIK JARI BARIS
# ============================================================

def day_cols(df: pd.DataFrame) -> list[str]:
    """Kolom hari '1'..'31' yang benar-benar ada di df (urut naik)."""
    return [c for c in DAY_COLS if c in df.columns]


def fingerprint_series(df: pd.DataFrame) -> pd.Series:
    """Sidik jari (md5 hex) per baris — 6 kolom kunci + nilai hari NON-NOL.

    Deterministik lintas sesi/file: kolom teks → ``astype(str)``; kolom
    hari → ``to_numeric → float64 → str`` (5 vs 5.0 samar). Hari bernilai
    0/kosong TIDAK ikut hash (segmen kosong) → dataset 30-hari vs 31-hari
    dengan hari ke-31 kosong menghasilkan sidik jari SAMA (baris yang
    sama tetap terlacak); hari bernilai hilang kolomnya → sidik jari
    berubah (nilai memang tak ada lagi — mark wajar terpangkas).
    Index hasil = index df (siap align/isin).
    """
    n = len(df)
    parts: list[pd.Series] = []
    for c in KEY_COLS:
        if c in df.columns:
            parts.append(df[c].astype(str))
        else:
            parts.append(pd.Series(["·"] * n, index=df.index, dtype="object"))
    for c in day_cols(df):
        num = pd.to_numeric(df[c], errors="coerce").astype("float64")
        seg = pd.Series("", index=df.index, dtype="object")
        nz = num.notna() & (num != 0)
        if nz.any():
            seg.loc[nz] = c + ":" + num[nz].astype(str)
        parts.append(seg)
    if not parts:  # degenerate — df tanpa kolom yang dikenal
        return pd.Series([""] * n, index=df.index)
    joined = parts[0].astype(str)
    for p in parts[1:]:
        joined = joined.str.cat(p.astype(str), sep="|")
    # segmen hari kosong (nilai 0/NaN) → run '|…|' kosong → rapikan agar
    # kolom hari yang tak ada ≡ kolom hari bernilai nol.
    joined = joined.str.replace(r"\|{2,}", "|", regex=True).str.rstrip("|")

    def _md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8", "surrogatepass")).hexdigest()

    return joined.map(_md5)


def select_followup_rows(df: pd.DataFrame, fps: pd.Series,
                         keys: Iterable[str]) -> pd.DataFrame:
    """Baris df ber-sidik jari ∈ keys (SALINAN + kolom __FP + dedup).

    - mask via ``fps.isin(set(keys))`` (fps = fingerprint_series(df),
      index identik df).
    - baris kembar identik-nilai → sidik jari sama → didedup
      (keep='first') — daftar follow-up per konten, bukan per salinan.
    """
    mask = fps.isin(set(keys))
    out = df[mask].copy()
    out[FP_COL] = fps[mask]
    if FP_COL in out.columns and len(out) > 1:
        out = out.drop_duplicates(subset=FP_COL, keep="first")
    return out


# ============================================================
# HARI MENCURIGAKAN (penanda warna)
# ============================================================

def suspicious_days(df: pd.DataFrame,
                    fps: pd.Series) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Hari mencurigakan per baris — utk pewarnaan tabel + export.

    Returns:
        red:   {fp: hari} — hari TERSANGKA (fallback HARI MAX) —
               merah, konsisten peta hari pop-up detail (v2.9.0).
        amber: {(fp, kolom_hari)} — nilai ≥ 2× rata-rata hari AKTIF
               (fallback AVG), nilai > 0, bukan hari merah —
               lonjakan sekunder (amber).

    v2.12.1 (perf): vektor numpy — dulu loop Python 797×31 dengan
    ``.iloc`` per sel (~68 ms data asli, laptop user 2-4× lebih lambat,
    dipanggil tiap render tab Follow Up); kini mask array + loop hanya
    atas HITUNGAN hasil (merah per baris, amber per sel lolos —
    semantik PERSIS: NaN/0/negatif dikecualikan, rday dari HARI
    TERSANGKA → fallback HARI MAX, amber tak menimpa hari merah).
    """
    red: dict[str, int] = {}
    amber: set[tuple[str, str]] = set()
    n = len(df)
    if n == 0:
        return red, amber
    dcols = day_cols(df)
    if not dcols:
        return red, amber
    fps_arr = (fps.to_numpy(dtype=object) if isinstance(fps, pd.Series)
               else np.asarray(list(fps), dtype="object"))
    # hari tersangka per BARIS (pola pop-up detail _day_map): HARI
    # TERSANGKA (hanya baris kandidat anomali) → fallback HARI MAX
    # (hari nilai terbesar) — fallback level NILAI, bukan level kolom.
    ters = hmax = None
    if "HARI TERSANGKA" in df.columns:
        ters = pd.to_numeric(
            df["HARI TERSANGKA"], errors="coerce").to_numpy(dtype="float64")
    if "HARI MAX" in df.columns:
        hmax = pd.to_numeric(
            df["HARI MAX"], errors="coerce").to_numpy(dtype="float64")
    # rday per baris: 0 = tidak ada (dulu None); valid = 1..31.
    rday = np.zeros(n, dtype="int64")
    for series in (ters, hmax):
        if series is None:
            continue
        ok = np.isfinite(series) & (series >= 1) & (series <= 31)
        m = (rday == 0) & ok
        if m.any():
            rday[m] = series[m].astype("int64")
    dcol_set = set(dcols)
    for i in np.nonzero(rday > 0)[0]:
        rd = int(rday[i])
        if str(rd) in dcol_set:
            red[str(fps_arr[i])] = rd
    # basis rata-rata: hari aktif lebih adil (hari kosong tak menarik
    # rata-rata turun) — fallback AVG bulanan.
    avg = None
    for src in ("AVG AKTIF", "AVG"):
        if src in df.columns:
            avg = pd.to_numeric(df[src], errors="coerce").to_numpy(
                dtype="float64")
            break
    if avg is not None:
        vals = df[dcols].apply(pd.to_numeric, errors="coerce").to_numpy(
            dtype="float64")
        # base > 0 (guard: base 0 → semua amber); nilai > 0; NaN tak lolos.
        base_ok = np.isfinite(avg) & (avg > 0)
        mask = (np.isfinite(vals) & (vals > 0)
                & (vals >= 2.0 * avg[:, None]) & base_ok[:, None])
        # hari merah dikecualikan (rday 0 = tak ada hari merah → semua
        # boleh, sama dgn `day != None` di implementasi lama).
        day_nums = np.array([int(c) for c in dcols], dtype="int64")
        mask &= day_nums[None, :] != rday[:, None]
        for i, j in zip(*np.nonzero(mask)):
            amber.add((str(fps_arr[i]), dcols[j]))
    return red, amber


# ============================================================
# PERSISTENSI (followup.json — pola filters.json)
# ============================================================

def followup_path() -> Path:
    """Jalur followup.json (dinamis, frozen-aware — pola profiles_path)."""
    if is_frozen():
        return exe_dir() / "followup.json"
    return Path(__file__).resolve().parent.parent / "followup.json"


def _backup_corrupt_file(p: Path) -> None:
    """File korup di-rename .bad (tidak hilang) — pola filters.py.

    os.replace menimpa .bad lama → hanya salinan korup TERBARU yang
    disimpan (tidak menumpuk)."""
    try:
        os.replace(p, p.with_suffix(p.suffix + ".bad"))
    except OSError:
        pass  # rename gagal (file terkunci?) — muat ulang dari nol


def load_followup_keys(path: Path | str | None = None) -> list[str]:
    """Muat daftar sidik jari tersimpan (urutan centang dipertahankan).

    File absen → []. File korup → backup .bad + [] (bukan crash).
    """
    p = Path(path) if path else followup_path()
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("bentuk 'rows' bukan list")
        keys = [str(k) for k in rows if k]
        return keys
    except (json.JSONDecodeError, ValueError, OSError) as e:
        _LOG.warning("followup.json korup (%s) — mulai dari daftar kosong", e)
        _backup_corrupt_file(p)
        return []


def save_followup_keys(keys: list[str],
                       path: Path | str | None = None) -> bool:
    """Simpan daftar sidik jari (atomic: tulis .tmp → replace)."""
    p = Path(path) if path else followup_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "rows": list(keys)}, f,
                      ensure_ascii=False, indent=0)
        os.replace(tmp, p)
        return True
    except OSError as e:
        _LOG.warning("gagal simpan followup.json: %s", e)
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


# ============================================================
# HASIL TINDAK LANJUT (re-import sheet terisi) — v2.13.3 ⑯
# ============================================================

def resolved_path() -> Path:
    """Jalur followup_resolved.json (samping followup.json)."""
    return followup_path().with_name("followup_resolved.json")


def load_resolved(path: Path | str | None = None) -> dict:
    """Muat status tindak lanjut {fp: {PIC, KATEGORI, PENYEBAB..., ts}}.

    File absen → {}. File korup → backup .bad + {} (pola load_followup_keys).
    """
    p = Path(path) if path else resolved_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("rows", {})
        return rows if isinstance(rows, dict) else {}
    except Exception:  # noqa: BLE001 — korup dibackup, bukan crash
        _LOG.warning("followup_resolved.json korup → backup .bad")
        _backup_corrupt_file(p)
        return {}


def save_resolved(resolved: dict,
                  path: Path | str | None = None) -> bool:
    """Simpan status tindak lanjut (atomic — pola save_followup_keys)."""
    p = Path(path) if path else resolved_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "rows": dict(resolved)},
                      f, ensure_ascii=False, indent=0)
        tmp.replace(p)
        return True
    except Exception:  # noqa: BLE001 — gagal simpan ≠ crash app
        _LOG.warning("gagal simpan followup_resolved.json")
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


def import_followup_workbook(path: str | os.PathLike,
                             config: dict | None = None) -> dict:
    """Baca workbook HASIL tindak lanjut (sheet 'FOLLOW UP' format ekspor)
    → dict {"error": pesan} ATAU {"resolved": {fp: info}, "n_rows": int,
    "n_filled": int, "file": nama}.

    Baris dianggap TERISI bila minimal satu kolom serah-terima (PIC /
    KATEGORI / PENYEBAB TERJADINYA WASTE) non-kosong. Kecocokan baris =
    sidik jari nilai (fingerprint_series: 6 kolom kunci + nilai hari
    non-nol — kolom hari int/float Excel dinormalisasi ke string nama).
    Kolom '✓' hasil ekspor diabaikan. Defensif: gagal baca → "error"
    (tidak pernah raise).
    """
    p = Path(path)
    base = {"file": p.name}
    try:
        if not p.exists():
            return {**base, "error": f"File tidak ditemukan: {p.name}"}
        df = pd.read_excel(p, sheet_name="FOLLOW UP")
        if df is None or df.empty:
            return {**base, "error": "Sheet 'FOLLOW UP' kosong / tidak ada "
                                     "di file ini (pakai file hasil ekspor "
                                     "tab Follow Up)."}
        # normalisasi nama kolom (int/float 1..31 → '1'..'31'; strip teks).
        # v2.18.0 audit (L-4): header hari numerik terbaca float ("1.0")
        # dulu hanya di-str() — "1.0" DITOLAK day_cols() → SEMUA sidik
        # jari beda dgn aplikasi → hasil tindak lanjut tak pernah match.
        # Mirror _normalize_columns loader: float integral → int → str.
        _ren = {}
        for c in df.columns:
            cn = c
            if isinstance(cn, float) and cn.is_integer():
                cn = int(cn)
            cn = str(cn).strip()
            if cn != c:
                _ren[c] = cn
        if _ren:
            df = df.rename(columns=_ren)
            df = df.loc[:, ~df.columns.duplicated()]
        missing = [c for c in KEY_COLS if c not in df.columns]
        if missing:
            return {**base, "error": f"Kolom kunci hilang: {missing} — pakai "
                                     "file hasil ekspor tab Follow Up "
                                     "(jangan ubah kolomnya)."}
        # buang kolom centang ekspor (tak ikut sidik jari)
        df = df.drop(columns=[c for c in (CHECK_COL,) if c in df.columns])
        fps = fingerprint_series(df)
        resolved: dict = {}
        n_filled = 0
        from datetime import datetime as _dt
        ts = _dt.now().isoformat(timespec="seconds")  # noqa: DTZ005 — konvensi timestamp naif (pola state.py)
        for i in range(len(df)):
            fp = str(fps.iloc[i])
            if not fp or fp == "nan":
                continue
            info = {}
            for col in HANDOVER_COLS:
                if col in df.columns:
                    v = df.iat[i, df.columns.get_loc(col)]
                    text = "" if pd.isna(v) else str(v).strip()
                    if text:
                        info[col] = text
            if not info:
                continue
            n_filled += 1
            resolved[fp] = {**info, "ts": ts, "file": p.name}
        return {**base, "resolved": resolved, "n_rows": len(df),
                "n_filled": n_filled}
    except Exception as e:  # noqa: BLE001 — defensif (sheet salah dsb.)
        return {**base, "error": f"{type(e).__name__}: {e}"}


# ============================================================
# EXPORT EXCEL
# ============================================================

def export_followup_xlsx(rows: pd.DataFrame, path: str,
                         red: dict[str, int],
                         amber: set[tuple[str, str]]) -> str:
    """Tulis sheet 'FOLLOW UP' — format rekap + kolom serah-terima.

    - Kolom: FOLLOWUP_COLS + hari yang ada + HANDOVER_COLS (kosong).
    - Hari merah (tersangka) → fill FEE2E2 + font DC2626 tebal;
      amber (≥ 2× rata-rata hari aktif) → fill FEF3C7.
    - Freeze header + auto-filter (nyaman di-sort di Excel).
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    fill_red = PatternFill("solid", start_color=RED_BG)
    fill_amber = PatternFill("solid", start_color=AMBER_BG)
    font_red = Font(bold=True, color=RED_FG)
    font_head = Font(bold=True)

    cols = ([c for c in FOLLOWUP_COLS if c in rows.columns]
            + day_cols(rows)
            + [c for c in HANDOVER_COLS])
    wb = Workbook()
    ws = wb.active
    ws.title = "FOLLOW UP"
    ws.append(cols)
    for cell in ws[1]:
        cell.font = font_head
        cell.alignment = Alignment(horizontal="center")
    fps = rows[FP_COL] if FP_COL in rows.columns else None
    for i in range(len(rows)):
        fp = str(fps.iloc[i]) if fps is not None else ""
        rday = red.get(fp)
        excel_row = i + 2
        for j, c in enumerate(cols):
            if c in HANDOVER_COLS:
                v = None
            elif c in rows.columns:
                v = rows[c].iloc[i]
                if pd.isna(v):
                    v = None
                elif isinstance(v, (np.integer, np.floating)):
                    # Bug-hunt 3-a: np.int64 BUKAN subclass int python —
                    # tanpa ini 16/31 kolom hari di data asli (int64)
                    # terekspor sebagai TEKS ('0'), SUM/sort Excel rusak
                    # (jebakan yang sama dgn V26-M1 models.py).
                    v = v.item()  # int tetap int, float tetap float
                elif isinstance(v, (int, float)):
                    v = float(v)
                else:
                    v = str(v)
            else:
                v = None
            cell = ws.cell(row=excel_row, column=j + 1, value=v)
            # v2.18.0 audit (M-1): anti formula injection — teks berawalan
            # '='/'+','-','@' dipaksa STRING (pola exporter._force_text_row;
            # file ini di-edit & dibuka petugas lapangan).
            if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
                cell.data_type = "s"
            if c in DAY_COLS and v is not None:
                day = int(c)
                if rday is not None and day == rday:
                    cell.fill = fill_red
                    cell.font = font_red
                elif (fp, c) in amber:
                    cell.fill = fill_amber
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = (f"A1:{get_column_letter(len(cols))}"
                          f"{len(rows) + 1}")
    for j, c in enumerate(cols, start=1):
        width = 10 if c in DAY_COLS else (
            26 if c in ("NAMA BARANG", "KETERANGAN", "SOURCE DATA",
                        "PENYEBAB TERJADINYA WASTE") else 16)
        ws.column_dimensions[get_column_letter(j)].width = width
    wb.save(path)
    return path
