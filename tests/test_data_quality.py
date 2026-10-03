"""Unit test — data_quality.run_checks (7 pemeriksaan data quality Detail).

Setiap pemeriksaan diuji tiga sisi: kasus trigger, kasus non-trigger, dan
kasus kolom hilang (check di-skip — tidak muncul di hasil, tidak raise).
Ditambah test urutan hasil (severity lalu kode), df kosong, defensif nilai
aneh, immutability df input, dan smoke data asli DATA_WASTE.xlsx dengan
angka deterministik untuk fixture tersebut.

Run: python -m pytest tests/test_data_quality.py -v
(smoke data asli ~5-10 detik; unit test sisanya cepat)
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest

from waste_anomaly.data_quality import SEVERITY_ORDER, CheckResult, run_checks

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "DATA_WASTE.xlsx"


def detail(rows: list[dict], drop: tuple[str, ...] = ()) -> pd.DataFrame:
    """Frame Detail mini dengan kolom default; kolom di `drop` dibuang."""
    base = {
        "NAMA RESTO": "R1",
        "NAMA BARANG": "ITEM A",
        "JENIS": "WASTE",
        "KETERANGAN": "Handling",
        "SATUAN": "GR",
        "SOURCE DATA": "WASTE BAHAN dan PACKAGING",
        "TOTAL": 0.0,
        "TOTAL BOM": 100.0,
    }
    records = []
    for r in rows:
        merged = {**base, **r}
        for k in drop:
            merged.pop(k, None)
        records.append(merged)
    return pd.DataFrame(records)


def codes(results: list[CheckResult]) -> list[str]:
    return [r.code for r in results]


def one(results: list[CheckResult], code: str) -> CheckResult:
    got = [r for r in results if r.code == code]
    assert got, f"{code} tidak muncul (hasil: {codes(results)})"
    return got[0]


# ============================================================
# DQ_NEGATIVE (error)
# ============================================================

class TestDQNegative:
    def test_trigger_total_negatif(self):
        res = run_checks(detail([{"TOTAL": -5}]))
        r = one(res, "DQ_NEGATIVE")
        assert r.severity == "error"
        assert r.count == 1
        assert r.sample[0] == "ITEM A @ R1 = -5"

    def test_trigger_kolom_hari(self):
        res = run_checks(detail([{"TOTAL": 0, "3": -2}]))
        r = one(res, "DQ_NEGATIVE")
        assert r.count == 1
        assert "= -2" in r.sample[0]

    def test_key_akhir_membatasi_kolom_hari(self):
        df = detail([{"TOTAL": 0, "31": -7}])
        assert "DQ_NEGATIVE" not in codes(run_checks(df, key_akhir=30))
        r = one(run_checks(df, key_akhir=31), "DQ_NEGATIVE")
        assert r.count == 1
        # tanpa key_akhir semua kolom hari ikut diperiksa
        assert one(run_checks(df), "DQ_NEGATIVE").count == 1

    def test_count_baris_bukan_sel_nilai(self):
        # 1 baris dengan 2 nilai negatif tetap dihitung 1 baris
        res = run_checks(detail([{"TOTAL": -1, "3": -4}, {"TOTAL": -2}]))
        r = one(res, "DQ_NEGATIVE")
        assert r.count == 2
        assert r.sample[0] == "ITEM A @ R1 = -4"  # terbesar magnitude-nya

    def test_non_trigger(self):
        res = run_checks(detail([{"TOTAL": 10}, {"TOTAL": 0}]))
        assert "DQ_NEGATIVE" not in codes(res)

    def test_skip_tanpa_total_dan_hari(self):
        res = run_checks(detail([{}], drop=("TOTAL",)))
        assert "DQ_NEGATIVE" not in codes(res)


# ============================================================
# DQ_NBSP_SATUAN (warning)
# ============================================================

class TestDQNbspSatuan:
    def test_trigger_nbsp(self):
        res = run_checks(detail([{"SATUAN": "PACK\xa0"}]))
        r = one(res, "DQ_NBSP_SATUAN")
        assert r.severity == "warning"
        assert r.count == 1
        assert r.sample[0] == "'PACK\\xa0' (1 baris)"

    def test_duplikat_tersembunyi_satu_dapat_satu_bersih(self):
        # 'PACK' bersih + 'PACK\xa0' kotor = satu kelompok satuan terduplikasi
        res = run_checks(detail([{"SATUAN": "PACK\xa0"}, {"SATUAN": "PACK"}]))
        r = one(res, "DQ_NBSP_SATUAN")
        assert r.count == 2
        assert "'PACK\\xa0' (1 baris)" in r.sample
        assert "'PACK' (1 baris)" in r.sample

    @pytest.mark.parametrize(
        "satuan", ["PACK ", " PACK", "PA  CK", "PACK\u200b", "PACK\t"]
    )
    def test_varian_whitespace_lain(self, satuan):
        res = run_checks(detail([{"SATUAN": satuan}, {"SATUAN": "GR"}]))
        assert one(res, "DQ_NBSP_SATUAN").count == 1

    def test_non_trigger(self):
        res = run_checks(detail([{"SATUAN": "GR"}, {"SATUAN": "PCS"}]))
        assert "DQ_NBSP_SATUAN" not in codes(res)

    def test_skip_tanpa_kolom_satuan(self):
        res = run_checks(detail([{"TOTAL": 0}], drop=("SATUAN",)))
        assert "DQ_NBSP_SATUAN" not in codes(res)

    def test_satuan_nan_diabaikan(self):
        res = run_checks(detail([{"SATUAN": None}, {"SATUAN": None}]))
        assert "DQ_NBSP_SATUAN" not in codes(res)


# ============================================================
# DQ_SOURCE_VARIANT (warning)
# ============================================================

class TestDQSourceVariant:
    def test_trigger_bedakapitalisasi(self):
        res = run_checks(
            detail(
                [
                    {"SOURCE DATA": "WASTE BAHAN dan PACKAGING"},
                    {"SOURCE DATA": "WASTE BAHAN dan PACKAGING"},
                    {"SOURCE DATA": "WASTE BAHAN DAN PACKAGING"},
                ]
            )
        )
        r = one(res, "DQ_SOURCE_VARIANT")
        assert r.severity == "warning"
        assert r.count == 3  # semua baris kelompok terdampak
        assert (
            r.sample[0]
            == "WASTE BAHAN dan PACKAGING (2) ~ WASTE BAHAN DAN PACKAGING (1)"
        )

    def test_trigger_bedawhitespace(self):
        res = run_checks(
            detail([{"SOURCE DATA": "SRC"}, {"SOURCE DATA": "SRC "}])
        )
        assert one(res, "DQ_SOURCE_VARIANT").count == 2

    def test_non_trigger_ejaan_sama(self):
        res = run_checks(detail([{"SOURCE DATA": "SRC"}, {"SOURCE DATA": "SRC"}]))
        assert "DQ_SOURCE_VARIANT" not in codes(res)

    def test_skip_tanpa_kolom_source_data(self):
        res = run_checks(detail([{"TOTAL": 0}], drop=("SOURCE DATA",)))
        assert "DQ_SOURCE_VARIANT" not in codes(res)

    def test_source_nan_diabaikan(self):
        res = run_checks(detail([{"SOURCE DATA": None}, {"SOURCE DATA": None}]))
        assert "DQ_SOURCE_VARIANT" not in codes(res)


# ============================================================
# DQ_KETERANGAN_PREFIX (info)
# ============================================================

class TestDQKeteranganPrefix:
    def test_trigger(self):
        res = run_checks(
            detail([{"KETERANGAN": "Kualitas"}, {"KETERANGAN": "Kualitas Internal"}])
        )
        r = one(res, "DQ_KETERANGAN_PREFIX")
        assert r.severity == "info"
        assert r.count == 1  # hanya baris keterangan yang lebih pendek
        assert r.sample[0] == "Kualitas ⊂ Kualitas Internal"

    def test_case_insensitive(self):
        res = run_checks(
            detail([{"KETERANGAN": "kualitas"}, {"KETERANGAN": "KUALITAS INTERNAL"}])
        )
        assert one(res, "DQ_KETERANGAN_PREFIX").count == 1

    def test_bedakapitalisasi_sama_panjang_bukan_prefix(self):
        # 'KUALITAS' vs 'Kualitas': beda kapital saja, bukan fragmentasi prefix
        res = run_checks(detail([{"KETERANGAN": "KUALITAS"}, {"KETERANGAN": "Kualitas"}]))
        assert "DQ_KETERANGAN_PREFIX" not in codes(res)

    def test_keterangan_kosong_bukan_prefix(self):
        res = run_checks(detail([{"KETERANGAN": ""}, {"KETERANGAN": "Kualitas"}]))
        assert "DQ_KETERANGAN_PREFIX" not in codes(res)

    def test_non_trigger(self):
        res = run_checks(detail([{"KETERANGAN": "Handling"}, {"KETERANGAN": "SUSUT"}]))
        assert "DQ_KETERANGAN_PREFIX" not in codes(res)

    def test_skip_tanpa_kolom_keterangan(self):
        res = run_checks(detail([{"TOTAL": 0}], drop=("KETERANGAN",)))
        assert "DQ_KETERANGAN_PREFIX" not in codes(res)


# ============================================================
# DQ_WASTE_NO_BOM (warning)
# ============================================================

class TestDQWasteNoBom:
    def test_trigger_bom_nan(self):
        res = run_checks(detail([{"TOTAL": 5, "TOTAL BOM": None}]))
        r = one(res, "DQ_WASTE_NO_BOM")
        assert r.severity == "warning"
        assert r.count == 1
        assert "5" in r.detail  # sum TOTAL disebut di detail

    def test_trigger_bom_nol_dan_negatif(self):
        res = run_checks(
            detail([{"TOTAL": 5, "TOTAL BOM": 0}, {"TOTAL": 5, "TOTAL BOM": -1}])
        )
        assert one(res, "DQ_WASTE_NO_BOM").count == 2

    def test_non_trigger(self):
        res = run_checks(detail([{"TOTAL": 5, "TOTAL BOM": 10}, {"TOTAL": 0, "TOTAL BOM": None}]))
        assert "DQ_WASTE_NO_BOM" not in codes(res)

    def test_sample_urut_total_desc(self):
        res = run_checks(
            detail(
                [
                    {"NAMA BARANG": "B", "TOTAL": 3, "TOTAL BOM": 0},
                    {"NAMA BARANG": "A", "TOTAL": 9, "TOTAL BOM": 0},
                ]
            )
        )
        r = one(res, "DQ_WASTE_NO_BOM")
        assert r.count == 2
        assert r.sample[0] == "A @ R1 (9)"
        assert "12" in r.detail  # 3 + 9

    def test_skip_tanpa_kolom_total_bom(self):
        res = run_checks(detail([{"TOTAL": 5}], drop=("TOTAL BOM",)))
        assert "DQ_WASTE_NO_BOM" not in codes(res)


# ============================================================
# DQ_SPLIT_SOURCE (warning)
# ============================================================

class TestDQSplitSource:
    def test_trigger(self):
        res = run_checks(
            detail(
                [
                    {"TOTAL": 6, "SOURCE DATA": "WASTE BAHAN dan PACKAGING"},
                    {"TOTAL": 3, "SOURCE DATA": "WASTEPORSI DINEIN KARNAHANDLING"},
                ]
            )
        )
        r = one(res, "DQ_SPLIT_SOURCE")
        assert r.severity == "warning"
        assert r.count == 1  # jumlah GRUP, bukan jumlah baris
        assert r.sample[0] == "R1 / ITEM A / Handling → 2 baris aktif"

    def test_tiga_baris_aktif(self):
        res = run_checks(detail([{"TOTAL": 1}, {"TOTAL": 2}, {"TOTAL": 3}]))
        r = one(res, "DQ_SPLIT_SOURCE")
        assert r.count == 1
        assert r.sample[0] == "R1 / ITEM A / Handling → 3 baris aktif"

    def test_non_trigger_satu_baris_aktif(self):
        res = run_checks(detail([{"TOTAL": 6}, {"TOTAL": 0}]))
        assert "DQ_SPLIT_SOURCE" not in codes(res)

    def test_non_trigger_kunci_beda(self):
        res = run_checks(
            detail([{"TOTAL": 6, "KETERANGAN": "Handling"}, {"TOTAL": 6, "KETERANGAN": "SUSUT"}])
        )
        assert "DQ_SPLIT_SOURCE" not in codes(res)

    def test_count_grup_bukan_baris(self):
        res = run_checks(
            detail(
                [
                    {"NAMA BARANG": "A", "TOTAL": 1},
                    {"NAMA BARANG": "A", "TOTAL": 1},
                    {"NAMA BARANG": "B", "TOTAL": 1},
                    {"NAMA BARANG": "B", "TOTAL": 1},
                ]
            )
        )
        assert one(res, "DQ_SPLIT_SOURCE").count == 2

    def test_skip_tanpa_kolom_jenis(self):
        res = run_checks(detail([{"TOTAL": 6}], drop=("JENIS",)))
        assert "DQ_SPLIT_SOURCE" not in codes(res)


# ============================================================
# DQ_ZERO_ROWS (info)
# ============================================================

class TestDQZeroRows:
    def test_trigger(self):
        res = run_checks(detail([{"TOTAL": 0}, {"TOTAL": 5}]))
        r = one(res, "DQ_ZERO_ROWS")
        assert r.severity == "info"
        assert r.count == 1
        assert "50" in r.detail  # persentase disebut di detail

    def test_total_nan_dihitung(self):
        res = run_checks(detail([{"TOTAL": None}]))
        assert one(res, "DQ_ZERO_ROWS").count == 1

    def test_non_trigger_semua_positif(self):
        res = run_checks(detail([{"TOTAL": 5}, {"TOTAL": 7}]))
        assert "DQ_ZERO_ROWS" not in codes(res)

    def test_skip_tanpa_kolom_total(self):
        res = run_checks(detail([{}], drop=("TOTAL",)))
        assert "DQ_ZERO_ROWS" not in codes(res)


# ============================================================
# URUTAN, KONTRAK, DEFENSIF
# ============================================================

class TestOrdering:
    def test_severity_lalu_kode_alfabetis(self):
        # satu frame yang memicu semua 7 pemeriksaan
        df = detail(
            [
                # r1: negatif + satuan NBSP + keterangan pendek
                {"TOTAL": -1, "SATUAN": "PACK\xa0", "KETERANGAN": "Kualitas", "TOTAL BOM": 0},
                # r2: aktif tanpa BOM + satuan 'PACK' bersih (duplikat r1)
                {"TOTAL": 5, "SATUAN": "PACK", "KETERANGAN": "Kualitas", "TOTAL BOM": 0},
                # r3: aktif tanpa BOM, split key sama dgn r2, SOURCE beda kapital
                {"TOTAL": 7, "SATUAN": "GR", "KETERANGAN": "Kualitas",
                 "TOTAL BOM": 0, "SOURCE DATA": "WASTE BAHAN DAN PACKAGING"},
                # r4: placeholder nol + keterangan panjang (pasangan prefix)
                {"TOTAL": 0, "KETERANGAN": "Kualitas Internal"},
            ]
        )
        res = run_checks(df)
        assert codes(res) == [
            "DQ_NEGATIVE",                       # error duluan
            "DQ_NBSP_SATUAN",                    # warning, alfabetis
            "DQ_SOURCE_VARIANT",
            "DQ_SPLIT_SOURCE",
            "DQ_WASTE_NO_BOM",
            "DQ_KETERANGAN_PREFIX",              # info, alfabetis
            "DQ_ZERO_ROWS",
        ]

    def test_severity_order_map(self):
        assert SEVERITY_ORDER == {"error": 0, "warning": 1, "info": 2}


class TestContract:
    def test_checkresult_frozen(self):
        r = CheckResult(code="X", severity="info", title="t", detail="d")
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.count = 5  # type: ignore[misc]

    def test_sample_maks_5(self):
        rows = [{"TOTAL": -i, "NAMA BARANG": f"B{i}"} for i in range(1, 9)]
        res = run_checks(detail(rows))
        assert len(one(res, "DQ_NEGATIVE").sample) == 5

    def test_df_tidak_dimutasi(self):
        df = detail(
            [
                {"TOTAL": -1, "SATUAN": "PACK\xa0"},
                {"TOTAL": 5, "TOTAL BOM": 0},
                {"TOTAL": 0},
            ]
        )
        before = df.copy()
        run_checks(df)
        pd.testing.assert_frame_equal(df, before)


class TestDefensive:
    def test_df_kosong(self):
        assert run_checks(pd.DataFrame()) == []
        assert run_checks(detail([])) == []

    def test_none(self):
        assert run_checks(None) == []

    def test_nilai_aneh_tidak_raise(self):
        df = pd.DataFrame(
            {
                "TOTAL": ["abc", None, 5],
                "TOTAL BOM": ["x", 0, None],
                "SATUAN": [123, None, "GR"],
                "SOURCE DATA": [42, "SRC", "src"],
                "KETERANGAN": ["A", None, "AB"],
                "NAMA RESTO": ["R", "R", "R"],
                "NAMA BARANG": ["I", "I", "I"],
                "JENIS": ["WASTE", "WASTE", "WASTE"],
            }
        )
        res = run_checks(df)  # tidak boleh raise
        assert isinstance(res, list)
        # TOTAL non-numerik → NaN → dihitung baris nol
        assert one(res, "DQ_ZERO_ROWS").count == 2

    def test_kolom_hari_tipe_campur(self):
        df = pd.DataFrame({"TOTAL": [1], 5: [-2], "7": ["x"]})
        res = run_checks(df)
        assert one(res, "DQ_NEGATIVE").count == 1


# ============================================================
# SMOKE DATA ASLI (deterministik untuk fixture ini)
# ============================================================

@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture DATA_WASTE.xlsx tidak ada")
class TestRealDataSmoke:
    @pytest.fixture(scope="class")
    def raw_detail(self) -> pd.DataFrame:
        # Detail-shaped raw (Sheet1) — run_checks hanya butuh kolom yang ada
        return pd.read_excel(FIXTURE, sheet_name="Sheet1")

    @pytest.fixture(scope="class")
    def results(self, raw_detail: pd.DataFrame) -> list[CheckResult]:
        return run_checks(raw_detail, key_akhir=31)

    def test_kode_yang_muncul(self, results: list[CheckResult]):
        # data asli bersih dari nilai negatif → DQ_NEGATIVE tidak muncul
        assert codes(results) == [
            "DQ_NBSP_SATUAN",
            "DQ_SOURCE_VARIANT",
            "DQ_SPLIT_SOURCE",
            "DQ_WASTE_NO_BOM",
            "DQ_KETERANGAN_PREFIX",
            "DQ_ZERO_ROWS",
        ]

    def test_nbsp_satuan(self, results: list[CheckResult]):
        r = one(results, "DQ_NBSP_SATUAN")
        # 2.033 baris 'PACK\xa0' + 6 baris 'PACK' = kelompok duplikat 2.039
        assert r.count == 2039
        assert r.sample[0] == "'PACK\\xa0' (2033 baris)"
        assert "'PACK' (6 baris)" in r.sample

    def test_source_variant(self, results: list[CheckResult]):
        r = one(results, "DQ_SOURCE_VARIANT")
        # 11.654 + 432 = 12.086 baris, 1 kelompok, 2 ejaan
        assert r.count == 12086
        assert (
            r.sample[0]
            == "WASTE BAHAN dan PACKAGING (11654) ~ WASTE BAHAN DAN PACKAGING (432)"
        )

    def test_waste_no_bom(self, results: list[CheckResult]):
        r = one(results, "DQ_WASTE_NO_BOM")
        assert r.count == 119
        assert "190.836" in r.detail  # total qty terdampak
        assert len(r.sample) == 5

    def test_split_source(self, results: list[CheckResult]):
        r = one(results, "DQ_SPLIT_SOURCE")
        # 8.221 grup ter-split total, tapi grup dengan >= 2 baris AKTIF
        # (TOTAL > 0) = 318 (probe langsung pada fixture)
        assert r.count == 318
        assert " baris aktif" in r.sample[0]

    def test_keterangan_prefix(self, results: list[CheckResult]):
        r = one(results, "DQ_KETERANGAN_PREFIX")
        assert r.count == 97  # baris 'Kualitas' (yang pecah)
        assert any("Kualitas ⊂" in s for s in r.sample)
        assert "Kualitas" in r.detail

    def test_zero_rows(self, results: list[CheckResult]):
        r = one(results, "DQ_ZERO_ROWS")
        assert r.count == 23470
        assert "90,6" in r.detail
