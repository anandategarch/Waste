"""test_v2137.py — regresi Gelombang B deep-audit v2.13.7 (engine cepat).

Sumber: audit menyeluruh perf engine (laporan audit-B-engine.md).
Gelombang B = akselerasi pipeline 5,68 → 2,67 dtk data asli (−53%)
dengan OUTPUT IDENTIK — dikunci di sini lewat uji EKIVALENSI ORACLE:
tiap titik yang divektorkan diuji lawan REPLIKA ALGORISMA LAMA
(pola test_v2121 "suspicious_days ekuivalensi oracle loop lama"):

- [A] stage_03: kontribusi/gabungan (loop 2.500 grup → vektor) vs oracle.
- [B] stage_02: median-aktif / second-max / HARI MAX (loop per-baris →
  matrix numpy) vs oracle per-baris lama.
- [C] stage_12_6: quadrant (apply axis=1 → np.select) vs oracle.
- [D] stage_10: % to BOM / STATUS (apply axis=1 → loop kolom-numpy)
  vs oracle apply lama (semantik None-vs-NaN & urutan cabang).
- [E] loader: normalisasi float 15-digit — kolom bulat < 10^15 di-SKIP
  karena terbukti no-op ("%.15g" mencetak bulat ≤ 15 digit persis);
  kolom desimal tetap dinormalisasi per-sel.
- [F] period_history: jalur num= pra-hitung ≡ jalur num=None (4 agregat).
- [G] workers: blob pencarian tak lagi dibangun eager (fitur cari
  dihapus v2.12.4 — 1,2 dtk/run terbuang); jalur lazy state tetap hidup.

Data acak deterministik (seed) menjamin edge: None/NaN, string kosong,
tie kontribusi, duplikat nilai, baris tanpa hari aktif.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent


# ============================================================
# Helper umum: frame acak deterministik
# ============================================================

def _rand_frame(n: int = 400, seed: int = 1234) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    restos = [f"R{i%5}" for i in range(n)]
    barang = [f"B{i%7}" for i in range(n)]
    jenis = rng.choice(["WASTE", "SUSUT", "TRIAL"], n)
    ket = rng.choice(["Cancel Nota", "Internal", " Kualitas ", None, ""], n,
                     p=[0.35, 0.2, 0.15, 0.2, 0.1])
    src = rng.choice(["GABUNG_A", "GABUNG_B", None], n)
    total = rng.choice([0.0, 1.0, 2.0, 5.0, 7.5, 10.0, np.nan], n)
    return pd.DataFrame({
        "NAMA RESTO": restos, "NAMA BARANG": barang, "JENIS": jenis,
        "KETERANGAN": ket, "SOURCE DATA": src, "TOTAL": total,
    })


# ============================================================
# [A] stage_03 — kontribusi & gabungan vs oracle loop lama
# ============================================================

class TestStage03Ekivalen:
    def test_kontribusi_gabungan_vs_oracle(self):
        """Oracle = replika persis algoritma lama (loop grup + lambda
        _join_distinct + apply lookup dict) — hasil HARUS sama kolom
        demi kolom dengan implementasi vektor v2.13.7."""
        from waste_anomaly.stages import stage_03_reason

        df = _rand_frame(600, seed=99)
        new = stage_03_reason(df.copy(), 31, {})

        # ---------- ORACLE (algoritma lama, disalin dari git v2.13.6) ----
        group_keys_full = ["NAMA RESTO", "NAMA BARANG", "JENIS",
                           "KETERANGAN", "SOURCE DATA"]
        rt = (df[group_keys_full + ["TOTAL"]]
              .groupby(group_keys_full, dropna=False, as_index=False)
              .agg(TOTAL_REASON=("TOTAL", "sum")))
        rt = rt.sort_values("TOTAL_REASON", ascending=False, kind="stable")
        group_keys_short = ["NAMA RESTO", "NAMA BARANG", "JENIS"]
        is_waste = rt["JENIS"] == "WASTE"
        rt["_waste_valid"] = (is_waste & rt["TOTAL_REASON"].notna()
                              & (rt["TOTAL_REASON"] > 0))
        ket_nonempty = (rt["KETERANGAN"].notna()
                        & (rt["KETERANGAN"].astype(str).str.strip() != ""))
        src_nonempty = (rt["SOURCE DATA"].notna()
                        & (rt["SOURCE DATA"].astype(str).str.strip() != ""))
        rt["_ket_for_gabungan"] = np.where(
            is_waste,
            np.where(rt["_waste_valid"] & ket_nonempty, rt["KETERANGAN"], None),
            np.where(ket_nonempty, rt["KETERANGAN"], None))
        rt["_src_for_gabungan"] = np.where(
            is_waste,
            np.where(rt["_waste_valid"] & src_nonempty, rt["SOURCE DATA"], None),
            np.where(src_nonempty, rt["SOURCE DATA"], None))

        def _join_distinct(series):
            vals = [v for v in series if v is not None
                    and (not isinstance(v, float) or not np.isnan(v))]
            if not vals:
                return ""
            return ", ".join(list(dict.fromkeys(vals)))

        old_rs = (rt.groupby(group_keys_short, dropna=False, as_index=False)
                  .agg(**{
                      "KETERANGAN GABUNGAN": ("_ket_for_gabungan", _join_distinct),
                      "SOURCE DATA GABUNGAN": ("_src_for_gabungan", _join_distinct),
                  }))
        waste_groups = rt[is_waste].groupby(group_keys_short, dropna=False)
        kontribusi_map = {}
        for key, t in waste_groups:
            f = t[t["TOTAL_REASON"].notna() & (t["TOTAL_REASON"] > 0)
                  & t["KETERANGAN"].notna()
                  & (t["KETERANGAN"].astype(str).str.strip() != "")]
            if f.empty:
                continue
            grand_total = f["TOTAL_REASON"].sum()
            if grand_total == 0:
                continue
            ket_totals = f.groupby("KETERANGAN")["TOTAL_REASON"].sum()
            top_ket = ket_totals.idxmax()
            top_sum = ket_totals.max()
            pct_val = round(float(top_sum / grand_total) * 100, 0)
            kontribusi_map[key] = f"{top_ket} {int(pct_val)}%"

        def _lookup(row):
            key = (row["NAMA RESTO"], row["NAMA BARANG"], row["JENIS"])
            return kontribusi_map.get(key)
        old_rs["KONTRIBUSI TERBESAR"] = (old_rs.apply(_lookup, axis=1)
                                         if len(old_rs) > 0 else None)
        old = df.merge(old_rs, on=group_keys_short, how="left",
                       validate="many_to_one")

        # ---------- bandingkan ------------------------------------------
        for c in ("KETERANGAN GABUNGAN", "SOURCE DATA GABUNGAN",
                  "KONTRIBUSI TERBESAR"):
            a, b = old[c], new[c]
            neq = (~(a.eq(b) | (a.isna() & b.isna()))).sum()
            assert neq == 0, f"{c}: {neq} baris beda oracle vs vektor"

    def test_tie_kontribusi_ambil_keterangan_terkecil(self):
        """Tie jumlah sama → idxmax lama = KETERANGAN pertama urut naik —
        vektor stable-sort + drop_duplicates harus mereplikanya."""
        from waste_anomaly.stages import stage_03_reason
        df = pd.DataFrame({
            "NAMA RESTO": ["R", "R", "R", "R"],
            "NAMA BARANG": ["B", "B", "B", "B"],
            "JENIS": ["WASTE"] * 4,
            "KETERANGAN": ["Zeta", "Alpha", None, "Alpha"],
            "SOURCE DATA": ["S"] * 4,
            "TOTAL": [10.0, 5.0, 5.0, 5.0],  # Zeta=10, Alpha=5+5=10 → TIE
        })
        out = stage_03_reason(df, 31, {})
        # tie 10=10, grand 20 → idxmax di index terurut (Alpha < Zeta)
        assert out["KONTRIBUSI TERBESAR"].iloc[0] == "Alpha 50%"


# ============================================================
# [B] stage_02 — median/second-max/HARI MAX vs oracle per-baris
# ============================================================

class TestStage02Ekivalen:
    def test_median_secondmax_harimax_vs_oracle(self):
        from waste_anomaly.stages import stage_02_stats

        rng = np.random.default_rng(7)
        n, ka = 300, 12
        data = {"NAMA RESTO": [f"R{i%4}" for i in range(n)],
                "NAMA BARANG": [f"B{i%6}" for i in range(n)],
                "JENIS": ["WASTE"] * n, "KETERANGAN": ["X"] * n}
        for d in range(1, ka + 1):
            # campur: nilai bulat, desimal, 0, NaN
            col = rng.choice([0.0, 1.5, 3.0, np.nan, 10.0, 2.25], n)
            data[str(d)] = col
        df = pd.DataFrame(data)
        out = stage_02_stats(df, ka, {})

        # oracle per-baris (algoritma lama)
        day_cols = [str(d) for d in range(1, ka + 1)]
        dm = out[day_cols].apply(pd.to_numeric, errors="coerce")
        filled = dm.fillna(0).to_numpy()
        am = (dm.notna() & (dm > 0)).to_numpy()
        nnm = dm.notna().to_numpy()
        max_arr = np.where(nnm.any(axis=1),
                           np.where(nnm, filled, -np.inf).max(axis=1), np.nan)
        max_arr = np.where(np.isinf(max_arr) | np.isnan(max_arr), 0, max_arr)

        med_old, sec_old, hm_old = [], [], []
        for i in range(n):
            vals = filled[i][am[i]]
            med_old.append(np.median(vals) if len(vals) > 0 else np.nan)
            if len(vals) < 2:
                sec_old.append(np.nan)
            else:
                sec_old.append(np.partition(vals, len(vals) - 2)[-2])
            if max_arr[i] > 0:
                row_vals = dm.iloc[i].to_numpy()
                m = (row_vals == max_arr[i]) & nnm[i]
                hm_old.append(int(float(day_cols[int(np.argmax(m))]))
                              if m.any() else None)
            else:
                hm_old.append(None)

        assert np.allclose(out["MEDIAN AKTIF"].to_numpy(dtype=float),
                           np.array(med_old, dtype=float),
                           equal_nan=True)
        assert np.allclose(out["SECOND MAX"].to_numpy(dtype=float),
                           np.array(sec_old, dtype=float),
                           equal_nan=True)
        got = out["HARI MAX"].tolist()
        assert [None if v is None or (isinstance(v, float) and np.isnan(v))
                else int(v) for v in got] == [
            None if v is None else int(v) for v in hm_old]

    def test_baris_tanpa_hari_aktif(self):
        from waste_anomaly.stages import stage_02_stats
        df = pd.DataFrame({"NAMA RESTO": ["R"], "NAMA BARANG": ["B"],
                           "JENIS": ["WASTE"], "KETERANGAN": ["X"],
                           "1": [np.nan], "2": [0.0], "3": [np.nan]})
        out = stage_02_stats(df, 3, {})
        assert np.isnan(out["MEDIAN AKTIF"].iloc[0])
        assert np.isnan(out["SECOND MAX"].iloc[0])
        assert out["HARI MAX"].iloc[0] is None


# ============================================================
# [C] stage_12_6 — quadrant vs oracle
# ============================================================

class TestQuadrantEkivalen:
    def test_vs_oracle(self):
        from waste_anomaly.stages import stage_12_6_quadrant

        rng = np.random.default_rng(11)
        n = 500
        df = pd.DataFrame({
            "NAMA BARANG": [f"B{i%9}" for i in range(n)],
            "NAMA RESTO": [f"R{i%6}" for i in range(n)],
            "cabangActive": rng.integers(0, 7, n),
            "daysActive": rng.integers(0, 32, n),
        })
        out = stage_12_6_quadrant(df, 31, {})

        total_cabang = df["NAMA RESTO"].nunique()
        p = df["cabangActive"] / total_cabang
        s = np.where(31 > 0, df["daysActive"] / 31, 0)
        th = 0.5

        def _quad(pv, sv):
            if pv >= th and sv >= th:
                return "SISTEMIK"
            if pv >= th and sv < th:
                return "MUSIMAN"
            if pv < th and sv >= th:
                return "LOKAL-KRONIS"
            return "INSIDEN"
        expect = [_quad(pv, sv) for pv, sv in zip(p, s)]
        assert out["QUADRANT"].tolist() == expect

    def test_nan_prevalence_insiden(self):
        from waste_anomaly.stages import stage_12_6_quadrant
        df = pd.DataFrame({"NAMA BARANG": ["B", "B"],
                           "NAMA RESTO": ["R", "R2"],
                           "cabangActive": [np.nan, 1],
                           "daysActive": [31, 1]})
        out = stage_12_6_quadrant(df, 31, {})
        assert out["QUADRANT"].tolist()[0] == "INSIDEN"
        assert out["QUADRANT"].tolist()[1] == "MUSIMAN"


# ============================================================
# [D] stage_10 — % to BOM / STATUS vs oracle apply lama
# ============================================================

class TestStage10Ekivalen:
    def test_pct_bom_dan_helper_vs_oracle(self):
        from waste_anomaly.stages import stage_10_helper

        rng = np.random.default_rng(21)
        n = 300
        df = pd.DataFrame({
            "NAMA RESTO": [f"R{i%4}" for i in range(n)],
            "NAMA BARANG": [f"B{i%5}" for i in range(n)],
            "JENIS": ["WASTE"] * n,
            "KETERANGAN": rng.choice(
                ["Cancel Nota", "Internal", None, ""], n),
            "TOTAL": rng.choice([0.0, 3.0, 7.5, np.nan], n),
            "TOTAL BOM": rng.choice([0.0, 10.0, np.nan, 100.0], n),
            "MAX": rng.choice([0.0, 1.0, 5.5], n),
            "ALAT MESIN": rng.choice([None, 0.0, 1.0, "x"], n),
            "INTERNAL": rng.choice([None, 0.0, 1.0], n),
        })
        new = stage_10_helper(df, 31, {})

        # oracle apply lama
        def _pct(row):
            tv, bv = row.get("TOTAL"), row.get("TOTAL BOM")
            if (tv is None or bv is None
                    or (isinstance(bv, float) and np.isnan(bv))):
                return "Cek"
            try:
                if float(bv) == 0:
                    return None
                return float(tv) / float(bv)
            except (ValueError, TypeError):
                return None

        def _helper(row):
            ket = row.get("KETERANGAN")
            if (ket is None or (isinstance(ket, float) and np.isnan(ket))
                    or str(ket).strip() == ""):
                return None, None
            col = {"Cancel Nota": "CANCEL NOTA",
                   "Internal": "INTERNAL"}.get(str(ket).strip())
            # cat_map default: Internal → INTERNAL; Cancel Nota → CANCEL NOTA
            colmap = {"Cancel Nota": "CANCEL NOTA", "Internal": "INTERNAL"}
            col = colmap.get(str(ket).strip())
            if col is None or col not in row.index:
                return None, None
            hv = row.get(col)
            try:
                if hv is None or (isinstance(hv, float) and np.isnan(hv)):
                    hv_num = None
                else:
                    hv_num = float(hv)
            except (ValueError, TypeError):
                hv_num = None
            mv = row.get("MAX")
            mv_num = (float(mv) if mv is not None
                      and not (isinstance(mv, float) and np.isnan(mv)) else 0)

            def _st(h, m):
                if h is None:
                    return None
                if (h == 1 and m >= 0) or (h == 0 and m == 0):
                    return "Sesuai"
                return "Tidak Sesuai"
            return hv_num, _st(hv_num, mv_num)

        pct_old = [_pct(r) for _, r in df.iterrows()]
        hp_old = [_helper(r) for _, r in df.iterrows()]
        helper_old = [h for h, _ in hp_old]
        status_old = [s for _, s in hp_old]

        # jalur HELPER-absen dipakai (tidak ada kolom HELPER di input)
        assert "HELPER" not in df.columns
        for name, old_vals in (("% to BOM", pct_old),
                               ("HELPER", helper_old),
                               ("STATUS", status_old)):
            a = pd.Series(old_vals)
            b = new[name].reset_index(drop=True)
            neq = (~(a.eq(b) | (a.isna() & b.isna()))).sum()
            assert neq == 0, f"{name}: {neq} baris beda oracle vs kolom-numpy"

    def test_jalur_helper_carried(self):
        from waste_anomaly.stages import stage_10_helper
        df = pd.DataFrame({
            "NAMA RESTO": ["R", "R"], "NAMA BARANG": ["B", "B"],
            "JENIS": ["WASTE"] * 2, "KETERANGAN": ["X", "X"],
            "HELPER": [1.0, 0.0], "MAX": [5.0, 0.0],
            "TOTAL": [2.0, 4.0], "TOTAL BOM": [4.0, 4.0],
        })
        out = stage_10_helper(df, 31, {})
        assert out["STATUS"].tolist() == ["Sesuai", "Sesuai"]
        assert out["% to BOM"].tolist() == [0.5, 1.0]


# ============================================================
# [E] loader — normalisasi float: skip no-op terbukti
# ============================================================

class TestNormalisasiFloat:
    def test_kolom_bulat_skip_identik_map(self):
        """Kolom bulat < 10^15 di-skip — hasil HARUS sama dgn .map lama
        (skip terbukti no-op: '%.15g' mencetak bulat ≤ 15 digit persis)."""
        from waste_anomaly.loader import _float15, _normalize_float_precision
        df = pd.DataFrame({
            "hari": [0.0, 1.0, 999999.0, np.nan, 123456789.0],
            "besar": [1e14, 0.0, np.nan, 42.0, 999999999999999.0],
        })
        out = _normalize_float_precision(df.copy())
        for c in df.columns:
            expect = df[c].map(_float15)
            assert out[c].equals(expect), f"kolom {c} berubah padahal no-op"

    def test_kolom_desimal_tetap_dinormalisasi(self):
        from waste_anomaly.loader import _normalize_float_precision
        df = pd.DataFrame({"v": [21.299999999999997, 0.30000000000000004]})
        out = _normalize_float_precision(df.copy())
        assert out["v"].tolist() == [21.3, 0.3]

    def test_nan_inf_passthrough(self):
        from waste_anomaly.loader import _normalize_float_precision
        df = pd.DataFrame({"v": [np.nan, 1.5, np.inf]})
        out = _normalize_float_precision(df.copy())
        assert np.isnan(out["v"].iloc[0]) and np.isinf(out["v"].iloc[2])


# ============================================================
# [F] period_history — num pra-hitung ≡ num None
# ============================================================

class TestPeriodHistoryNum:
    def test_agregat_identik_dengan_tanpa_num(self):
        from waste_anomaly.period_history import (
            _aggregate,
            _base_keys_totals,
            _jenis_item_totals,
            _jenis_totals,
        )
        df = _rand_frame(300, seed=5).copy()
        rng = np.random.default_rng(5)
        for d in range(1, 32):
            df[str(d)] = rng.choice([0.0, 1.5, np.nan, 4.0], len(df))
        num = df[[str(d) for d in range(1, 32)]].apply(
            pd.to_numeric, errors="coerce")

        for fn, args in (
                (_aggregate, (31,)),
                (_jenis_totals, ()),
                (_jenis_item_totals, ()),
                (_base_keys_totals, (["NAMA RESTO", "NAMA BARANG", "JENIS",
                                      "KETERANGAN"],))):
            a = fn(df, *args, num=None)
            b = fn(df, *args, num=num)
            pd.testing.assert_frame_equal(a.reset_index(drop=True),
                                          b.reset_index(drop=True))


# ============================================================
# [G] workers — blob pencarian tidak lagi dibangun eager
# ============================================================

class TestWorkerBlob:
    def test_worker_tak_membangun_blob_eager(self):
        """Fitur cari dihapus v2.12.4 — membangun blob ±1,2 dtk per run
        di worker murni terbuang (audit P7/D11). Kunci: worker tak lagi
        MEMANGGIL pembangun blob / menaruhnya di summary (jalur lazy
        state tetap sah — dites terpisah di bawah)."""
        src = (REPO / "ui" / "workers.py").read_text(encoding="utf-8")
        assert 'from .shared import' not in src, (
            "worker tidak boleh lagi mengimpor pembangun blob")
        assert 'search_blob' not in src, (
            "worker tidak boleh lagi menaruh blob di summary")

    def test_jalur_lazy_state_masih_hidup(self):
        """Semantik filter cari tetap teruji via state (blob dibangun
        malas saat search di-set) — kontrak test lama utuh."""
        from ui.shared import _build_search_blob
        df = pd.DataFrame({"A": ["kunci satu", "kunci dua", None]})
        blob = _build_search_blob(df)
        assert blob.str.contains("satu", regex=False, na=False).tolist()[0]
        assert not blob.str.contains("tiga", regex=False, na=False).any()
