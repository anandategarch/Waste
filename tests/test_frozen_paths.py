"""Test resolusi path frozen-mode PyInstaller (v2.4.1).

KONTEKS BUG yang di-lock di sini:
``CONFIG_PATH`` / ``APP_DIR`` dulunya resolve dari
``Path(__file__)`` — di exe PyInstaller itu menunjuk dir ekstraksi temp
``_MEIPASS`` yang DIHAPUS saat aplikasi ditutup. Akibat: threshold yang
disimpan user (tab Konfigurasi) hilang senyap di mode exe — kebalikan
klaim BUILD_EXE.bat.

Perilaku baru yang dikunci:
  1. Dev mode → path lama persis (tidak boleh berubah — golden regression
     memakai config dev).
  2. Frozen + sidecar belum ada → SEED otomatis dari bundled, lalu pakai
     sidecar (klaim BUILD_EXE.bat "config.json disimpan berdampingan dengan
     exe saat pertama kali dijalankan").
  3. Frozen + sidecar ada → sidecar dipakai (edit user bertahan).
  4. Frozen + seed gagal (folder exe read-only) → fallback bundled read-only.
  5. ui app_dir() → folder exe saat frozen (folder data/ writable).

v2.13.8 (gel-C): seksi FILTERS PATH DIHAPUS bersama modul
waste_anomaly/filters.py (yatim sejak sidebar/filter-profile dihapus
v2.12.4 — nol konsumen produksi; frozen-sidecar pattern tetap terkunci
penuh lewat TestConfigPath di bawah, mekanismenya identik).

Monkeypatch menargetkan nama yang di-bind di modul konsumen
(``waste_anomaly.utils.is_frozen`` dst.) karena ``from .frozen import ...``
menyalin referensi saat import.
"""

import json
from pathlib import Path

import pytest

import waste_anomaly.utils as wu


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture()
def frozen_env(tmp_path, monkeypatch):
    """Direktori exe + _MEIPASS palsu + aplikasi 'dibekukan'.

    Returns:
        (exe_dir, meipass, bundled_cfg, freeze, unfreeze)
    """
    exe_dir = tmp_path / "dist"
    exe_dir.mkdir()
    meipass = tmp_path / "meipass"
    (meipass / "waste_anomaly").mkdir(parents=True)
    bundled_cfg = meipass / "waste_anomaly" / "config.json"
    bundled_cfg.write_text(
        json.dumps({"version": "2.4.1", "thresholds": {"TH_SPIKE": 3}}),
        encoding="utf-8",
    )

    def freeze():
        monkeypatch.setattr(wu, "is_frozen", lambda: True)
        monkeypatch.setattr(wu, "exe_dir", lambda: exe_dir)
        monkeypatch.setattr(wu, "bundle_dir", lambda: meipass)

    def unfreeze():
        monkeypatch.setattr(wu, "is_frozen", lambda: False)

    return exe_dir, meipass, bundled_cfg, freeze, unfreeze


# ============================================================
# CONFIG PATH (waste_anomaly/utils.py)
# ============================================================

class TestConfigPath:
    def test_dev_mode_path_tidak_berubah(self, frozen_env):
        _, _, _, freeze, unfreeze = frozen_env
        unfreeze()
        # Dev: CONFIG_PATH klasik di dalam paket — golden regression
        # tergantung path ini.
        assert wu._active_config_path() == wu.CONFIG_PATH
        assert wu.CONFIG_PATH.name == "config.json"
        assert wu.CONFIG_PATH.parent.name == "waste_anomaly"

    def test_frozen_seed_sidecar_first_run(self, frozen_env):
        exe_dir, meipass, bundled_cfg, freeze, _ = frozen_env
        freeze()
        sidecar = exe_dir / "config.json"
        assert not sidecar.exists()
        got = wu._active_config_path()
        # First run: seed dari bundled → sidecar, lalu pakai sidecar
        assert got == sidecar
        assert sidecar.exists()
        assert json.loads(sidecar.read_text(encoding="utf-8")) == \
            json.loads(bundled_cfg.read_text(encoding="utf-8"))

    def test_frozen_sidecar_ada_seed_tidak_jalan(self, frozen_env):
        exe_dir, meipass, bundled_cfg, freeze, _ = frozen_env
        sidecar = exe_dir / "config.json"
        sidecar.write_text(json.dumps({"version": "USER-EDITED"}), encoding="utf-8")
        freeze()
        got = wu._active_config_path()
        assert got == sidecar
        # Edit user bertahan — bundled tidak menimpa
        assert json.loads(sidecar.read_text(encoding="utf-8"))["version"] == "USER-EDITED"

    def test_frozen_readonly_fallback_bundled(self, frozen_env, monkeypatch):
        exe_dir, meipass, bundled_cfg, freeze, _ = frozen_env
        freeze()
        # Simulasikan folder exe read-only: seed gagal
        monkeypatch.setattr(wu, "_seed_sidecar_config", lambda b, s: False)
        got = wu._active_config_path()
        assert got == bundled_cfg  # fallback read-only

    def test_load_config_frozen_baca_sidecar(self, frozen_env):
        exe_dir, _, _, freeze, _ = frozen_env
        freeze()
        # load_config() tanpa argumen harus pakai _active_config_path()
        cfg = wu.load_config()
        assert cfg.get("version") == "2.4.1"
        assert (exe_dir / "config.json").exists()


# ============================================================
# UI APP DIR (ui/shared.py — folder data/ & ikon)
# ============================================================

class TestUiAppDir:
    def test_dev_mode_repo_root(self):
        from ui import shared
        assert shared.app_dir() == Path(shared.__file__).resolve().parent.parent

    def test_frozen_mode_exe_dir(self, frozen_env, monkeypatch):
        exe_dir, _, _, _, _ = frozen_env
        from ui import shared
        monkeypatch.setattr(shared, "_exe_dir", lambda: exe_dir)
        monkeypatch.setattr(shared, "_bundle_dir", lambda: exe_dir / "meipass_fake")
        assert shared.app_dir() == exe_dir
        assert shared.bundle_res_dir() == exe_dir / "meipass_fake"
