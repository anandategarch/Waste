# Waste Anomaly Detection

Python + PySide6 (Qt) **anomaly workbench** untuk deteksi anomali waste di cabang resto. Replika 1:1 dari **Power Query M code** untuk analisa waste per item, per cabang, per kategori — lengkap dengan **12 sinyal anomali**, composite scoring, **drill-down interaktif**, **filter profile persistence**, **benchmark peer aktif (pop-up detail + sinyal S8/S9)**, **kolom % to BOM (waste vs penjualan kuantiti)**, **data quality otomatis (pipeline & export)**, **compare periode bulan-ke-bulan**, **banding vs beberapa bulan lalu (multi-file, kuantiti tanpa BOM, v2.10.0)**, dan **filter funnel di judul SEMUA kolom tabel (v2.12.3/v2.12.4 — sidebar filter & slicer dihapus)**, dan **tab Follow Up: centang ✓ baris mencurigakan → shortlist rekap + warna hari + ekspor + impor hasil tindak lanjut (v2.12.0/v2.13.3)**, dan **tab Scorecard Cabang: urutan kunjungan audit + potensi hemat + detektor input kosong + top kerugian + pola hari kalender + hari sistemik + kualitas data + tren multi-bulan (v2.13.1-3)** (v2.8.1: 5 → 3 view — tab Jelajah & Waktu + seluruh modul chart dihapus; v2.8.0: 8 → 5 view — tab Uang/Peer/Kualitas Data dihapus).

> **v2.13.3** — **TREN MULTI-BULAN + PRATINJAU AMBANG + LOOP RESOLUSI FOLLOW-UP** (gelombang "analisa tambahan" Task 5 — penutup): (1) **⑧ TREN per cabang** — kolom TREN di tabel Scorecard (aktif dengan ≥ 1 pembanding): "↗ Naik / ↘ Turun (batas ±10%) / → Stabil / Baru / Pulih" vs pembanding terbaru; + **kartu 📈 Tren Bulanan per Cabang** (tabel per-bulan + Bulan Ini + TREN — butuh ≥ 2 file pembanding; kurang dari itu PESAN JUJUR "tambahkan ≥ 2 file bulan lalu", kolom TREN tetap aktif). (2) **⑮ Tombol 👀 Pratinjau Ambang** di editor threshold tab Pipeline — jawab "kalau kubah X jadi Y, berapa perubahannya?" SEBELUM menyimpan: hitung ulang 12 sinyal + status dengan nilai form saat ini (murni vektor 0,36 dtk data asli; validasi seperti Simpan; dialog SEBELUM → SESUDAH per status; contoh: TH_SPIKE 3→2 = Potensi Anomali 358 → 406). (3) **⑯ LOOP RESOLUSI FOLLOW-UP** — tombol **📥 Impor Hasil TL** di tab Follow Up: baca kembali file ekspor yang SUDAH DIISI petugas (kolom PIC/KATEGORI/PENYEBAB di sheet FOLLOW UP) → baris cocok diberi **status "Selesai" + kolom STATUS TL & PIC** (posisi pertama — terlihat tanpa scroll) + label "selesai X/Y"; kecocokan = sidik jari nilai (kolom kunci + hari — aman walau sheet di-sort/filter di Excel); tersimpan di **followup_resolved.json** (atomic + backup korup — pola followup.json); baris terisi yang belum ada di daftar tetap disimpan (status aktif otomatis bila dicentang lagi) — aplikasi kini menutup siklus deteksi → ekspor → tindak lanjut → impor → selesai. 837+20 = **857 test**; E2E data asli **45/45** (+ TREN kolom & kartu jujur, tombol ⑮/⑯; preview smoke 0,36 dtk).

> **v2.13.2** — **PERSENTIL PEER + BENFORD (DQ) + PANEL KUALITAS DATA** (gelombang "analisa tambahan" Task 4): (1) **⑨ DI ATAS % CABANG** di kartu Top Kerugian — persentil TOTAL baris di antara cabang lain yang memang ber-waste pada item sama (100 = paling boros, 0 = paling hemat) — padanan robust z-score dgn istilah awam: tahan distribusi miring, unit-free (per-item satu satuan), tidak seperti rasio yang meledak pada median kecil (data asli: SURAI NAGA @1042.KWGGAL = 100 — paling boros dari 19 cabang; KULIT PANGSIT @1151.GGPDAA = 100; @1327.CKRBOS = 89,5). (2) **⑪ Benford** — pemeriksaan baru DQ_BENFORD (info): pola digit pertama nilai waste vs distribusi wajar; JUJUR by design — hanya dibenderai bila deviasi ≥ 10 pp (data asli: 6,4 pp → TIDAK dibenderai; sampel < 500 nilai → skip; detail menegaskan "alat forensik kasar — deviasi BUKAN bukti manipulasi"). (3) **⑩ Panel 🧪 Kualitas Data di tab Scorecard** — resurface run_checks yang sejak v2.8.0 hanya hidup di sheet export: 6 pemeriksaan (satuan kembar NBSP 2.039 baris, SOURCE DATA beda kapital 12.086, business key terpecah 318, waste tanpa BOM 119, prefix KETERANGAN 97, baris nol 23.470) + Benford — table dgn funnel + penjelasan lengkap di tooltip kolom PENJELASAN. 830+7 = **837 test**; E2E data asli **41/41** (+ kartu DQ terisi, Benford tidak dibenderai, kolom persentil hadir).

> **v2.13.1** — **TAB SCORECARD CABANG (urutan kunjungan audit) + KARTU PENDUKUNG** (gelombang "analisa tambahan" Task 2-3): tab baru **🏢 Scorecard Cabang** (setelah Hari Mencurigakan) menjawab pertanyaan manajemen "kunjungi cabang mana dulu, bawa bukti apa, berapa bisa dihemat?" — satu halaman: (1) **Tabel scorecard per cabang** (RANK = urutan kunjungan, TOTAL WASTE, INTENSITAS % = waste vs penjualan/BOM, KELEBIHAN = potensi hemat vs tipikal, ALASAN DOMINAN + share, ITEM TIAP HARI, ANOMALI, HARI TERSANGKA, BARU/PULIH = pasangan item baru & sudah pulih vs pembanding, STATUS INPUT verdict) — klik 2× = rincian cabang (top kerugian vs tipikal + profil alasan + verdict input); ⤢/⛶ pola tab lain. (2) **KPI**: POTENSI HEMAT (data asli: 1,29 juta unit) · INTENSITAS TIPIKAL (median 0,29%) · CABANG #1 (1042.KWGGAL) · HARI SISTEMIK. (3) **Kartu Top Kerugian vs Tipikal** — ranking UANG berdasar KELEBIHAN (bukan TOTAL; SATUAN tampil jujur; funnel bisa memilah GR/PCS). (4) **Kartu Pola Hari Kalender asli** (Senin–Minggu dari label bulan file — data asli: Sabtu/Minggu rata waste tertinggi ±391-396rb/hari vs Senin 268rb, +47%) — fix proxy hari%7 yang tak sebanding antar bulan (1 Agustus 2026 = Sabtu vs 1 September 2026 = Selasa). (5) **Kartu Hari Sistemik** — hari naik serentak di ≥ 3 cabang (masalah BERSAMA: pengiriman/hari besar/POS — bukan kecurigaan satu cabang; data asli: 0 hari sistemik = semua lonjakan lokal, itu sendiri informasi). (6) **Detektor INPUT KOSONG** (coverage_report): item umum (dilaporkan ≥ 75% cabang) yang tak dilaporkan satu cabang + verdict jujur "Berhenti Input" (aktif bulan lalu, kosong sekarang — sinyal terkuat) / "Memang Tak Pernah" (kosong dua-duanya) / "Perlu Pembanding" / "Lengkap" — data asli: B.1001.MLGPAR 35/40 item umum tak dilaporkan, 3 cabang "Berhenti Input". Mesin: modul baru waste_anomaly/insights.py (6 fungsi vektor defensif: resto_intensity, money_ranking, coverage_report, systemic_days, weekday_real, scorecard) + 25 test baru; render terukur data asli 265 ms pertama → 39 ms memo (busy feedback + memo per data/pembanding); summary pipeline + key "workbook_path" (label bulan file); funnel SEMUA kolom semua tabel (lokal tampilan, pola v2.12.4). Tab kini 5 → 6 (test struktur + E2E diperbarui dgn alasan tercatat). 805+25 = **830 test**; E2E data asli **38/38** (+ seksi 11: 20 cabang, KPI hemat 1,29jt, drill rincian 15 baris, memo 26 ms, 0 judul terpotong).

> **v2.13.0** — **PROFIL BARIS ("Tiap Hari / Kadang / Sekali Ini") + KELEBIHAN VS TIPIKAL CABANG LAIN** (gelombang "analisa tambahan" hasil riset data asli): riset menemukan tensi sentral — top-20 waste terbesar SEMUA kronis (17-30 hari aktif) dengan skor anomali 0-6: 12 sinyal menangkap LONJAKAN sesaat, sedangkan mayoritas nilai waste ada di baris stabil tiap hari; tab anomali belum menjawab pertanyaan audit pertama "ini salah input, atau memang bocor setiap hari?". (1) **Kolom PROFIL** (Stage 15b, murni additive): "Tiap Hari" (≥ 20 hari ber-waste, masalah proses/kronis) · "Kadang" (2-19 hari) · "Sekali Ini" (1 hari — kandidat salah input/kejadian tunggal, sepupu S10) · "—" (baris placeholder nol); funnel di header otomatis (filter "tunjukkan cuma anomali Sekali Ini — Baru"). **Suffix "— Baru"** muncul bila pembanding bulan lalu dimuat (pasangan cabang×item tidak ada/nol bulan lalu — dari kolom BULAN LALU; idempoten; data asli: 73 dari 797 anomali ber-suffix Baru). (2) **Kolom KELEBIHAN + PEER MEDIAN (AKTIF) + PEER AKTIF**: TOTAL sebulan − tipikal (median) cabang lain pada item yang sama — median HANYA dari peer yang memang punya waste (baris nol 90,6% data tidak menarik tipikal turun — pelajaran benchmark v2.5.0); peer < 3 = kosong (sample kecil); nilai minus = lebih hemat (jujur ditampilkan); tampil di pop-up detail (tooltip kamus istilah) — contoh data asli: SURAI NAGA (V.30) @ 1042.KWGGAL total 296rb vs tipikal peer 1.695 → **kelebihan 294rb (174×)**. (3) **Jawab pertanyaan user "pembanding hanya ada hari 30, error?"** — BUKAN error, sudah benar: bulan 30-hari (September/April/Juni/November) terdeteksi otomatis (`auto_key_akhir`), baris "Hari Data" informasional (bukan metrik kinerja), metrik **"Waste per Hari" menormalkan beda panjang bulan** supaya 30 vs 31 hari tidak dibaca sebagai perubahan performa; tooltip status file pembanding kini menjelaskan ini. 805 test (781+24); E2E data asli 29/29 (10 kolom tampak + funnel PROFIL + domain kanonik).

> **v2.12.5** — **HEADER ANTI-TERPOTONG + GUARD KLIK-GANDA FUNNEL** (2 keluhan user pasca funnel header v2.12.3–4): (1) **"Nama header jadi terpotong semenjak ada icon filter"** — akar terukur: judul kolom dilukis QSS dgn **font-weight 600 + font global \*{} 13px**, sedangkan `fontMetrics()` widget (weight 400, font default) mengukur 8–12% lebih pendek → lantai header kurang; ditambah backing funnel lama menutup zona [kanan−32, kanan−12] yang menabrak ekor judul (bukti piksel data asli 1366×700: "ANOMALY SCORE" terlukis sampai x=132, backing mulai x=125 → ekornya tertutup). Fix struktural: `FilterHeader.paintSection` melukis judul + panah sort di **rect yang disempitkan 22px** (teks ter-ELIDE sebelum funnel — tidak pernah tertutup ikon), strip kanan dilukis manual (bg QSS + ikon funnel + border replica); lantai lebar diukur dgn **font QSS asli** (`_header_font()` — family chain + 13px + DemiBold dari konstanta theme `UI_FONT_*`; `self.font()` tidak mewarisi font QSS — di Windows default 9pt vs QSS 13px). Geometri 1366 dipertahankan: 9 kolom tampak, Σ header = viewport, tanpa scrollbar horizontal, viewport 342px. (2) **"Waktu apply filter sepertinya ketrigger double klik sehingga pop-up / drill down detail muncul"** — mekanisme terbukti empiris: menu funnel menutupi baris tabel; klik penutup menu yang jatuh di tabel **di-replay Qt sebagai tekan#1 pada baris**, klik ke-2 user pada posisi sama = tekan#2 → Qt menyintesis klik-ganda → `doubleClicked` → DetailDialog terbuka sendiri saat/ setelah apply filter. Fix: `DataTable.mouseDoubleClickEvent` **menelan klik-ganda dalam <0,6 dtk** setelah menu funnel tertutup (`aboutToHide` → `_hf_hide`; klik tunggal pilih-baris tetap hidup; klik ganda sah sesudah selang itu tetap hidup — terverifikasi end-to-end). 769+12 = **781 test**; E2E data asli 27/27 (piksel strip bersih semua tab, guard, jalur funnel utuh).

> **v2.12.4** — **SIDEBAR & SLICER DIHAPUS + FUNNEL DI SEMUA KOLOM + KALIMAT PENJELAS DIHAPUS**: (1) **Sidebar filter kiri (v2.8.0) + tombol ☰ Filter di toolbar DIHAPUS TOTAL** (permintaan user) — QTabWidget langsung jadi central widget: **tabel memakai lebar PENUH jendela** (dulu sidebar 300px + splitter). Filter kini murni lewat funnel judul kolom + tombol **✕ Hapus Filter** (tab Anomali & Hari — pengganti tombol "Hapus Semua Filter" sidebar: lepas global + lokal + skor sekaligus). SlicerBar chip (v2.11.0) ikut dihapus (lanjutan permintaan v2.12.3 "ganti slicer dengan filter header") — tabel anomali tambah tinggi ±120px (slicer 100px + hint 20px hilang). (2) **SEMUA kolom punya funnel** (permintaan user "harusnya semua kolom punya filter") — tab Anomali & Hari: kolom RESTO/BARANG/JENIS/KETERANGAN/STATUS tetap GLOBAL (state `ctx.active_filters` — antar-tab sinkron, KPI ikut terfilter); **kolom lain (mis. TOTAL, skor, hari) = filter LOKAL tampilan** (mask isin per kolom + memo LRU per state — objek stabil → cache fit DataTable tetap kena; KPI & daftar Follow Up tak tersentuh). Tab Follow Up: semua kolom termasuk hari 1-31 (lokal — shortlist/ekspor tak tersentuh). Tab Banding Periode: funnel per halaman (bahan halaman disimpan — ganti filter tanpa compare ulang). Kolom ✓ & kolom identitas di-skip. (3) **Kalimat penjelas 💡 dihapus dari semua tab** ("Bukti hari = ...", "Klik baris = detail pop-up · ...", legenda merah/amber, instruksi file banding — permintaan user: kalimat tidak penting dihapus; penjelasan tetap di tooltip + Bantuan; legenda warna pindah ke tooltip judul kartu Follow Up). Infra: conftest menghancurkan widget sisa test secara aman antar test (close + deleteLater + processEvents) — diagnosa: cyclic gc menghapus widget yatim tepat saat Qt melukis tabel test lain → heap rusak → Segfault (v2.12.3 "lolos" karena timing alokasi, bukan perbaikan; pola yatim tak ada di app asli — semua view berparent). 753−12+28 = **769 test**; E2E data asli lihat bawah.
> **v2.12.3** — **OPS A "1 ITEM PER RESTO" + TOTAL BULAN LALU + FILTER DI HEADER TABEL + REDESAIN PETA HARI**: (1) **✓ Banding kini hanya memasukkan baris ANOMALI** — analisa data asli menemukan akar desain: peta ✓ dibangun dari dataset PENUH (25.901 baris, 97% STATUS Normal) → 1 centang item memasukkan 6-14 baris yang mayoritas baris placeholder Normal TOTAL=0 (5 KETERANGAN standar × duplikat pengajuan; terukur: baris item teratas punya 0 anomali tapi tetap memasukkan 8 baris noise; centang cabang = +968 baris!). Dengan saringan ANOMALY STATUS ≠ Normal: **75% item×resto punya TEPAT 1 baris anomali** → centang = "1 item per resto" sesuai permintaan; sisanya 2-4 baris anomali NYATA (semua relevan — ekuivalen centang manual di tab Anomali). Lepas ✓ juga membersihkan fps noise warisan v2.12.2 dari followup.json; baris tanpa anomali ditolak dengan pesan. (2) **Kolom TOTAL BULAN LALU + PERUBAHAN % di tab Follow Up** (muncul bila file pembanding dimuat — match resto×item×jenis×keterangan; PERUBAHAN % negatif otomatis merah; judul via alias headerData — kanonik tetap `BULAN LALU`). (3) **Tab Hari Mencurigakan: kolom JENIS selalu tampil** (dulu narrow-hidden di layar 1366 — padahal SUSUT/TRIAL/WASTE pembeda penting) **+ tombol ⤢ Perbesar Tabel & ⛶ Layar Penuh** (pola tab Anomali: viewport 166→344px). (4) **FILTER DI HEADER TABEL (Excel AutoFilter ala app)** — ikon funnel di ujung kanan judul kolom (NAMA RESTO/NAMA BARANG/JENIS/KETERANGAN/STATUS di tab Anomali & Hari; 6 kolom kategorik di tab Follow Up): klik → menu [↗ Urut Naik] [↘ Urut Turun] + kotak CARI + daftar nilai bercentang (jumlah barisnya) + Pilih Semua/Selesai. Semantik = slicer (nilai tercentang = ikut tampil); state TETAP SATU di `ctx.active_filters` → chip slicer sinkron otomatis; live-apply di-debounce 120ms; tab Anomali & Hari memfilter dataset global, tab Follow Up filter LOKAL tampilan (shortlist & ekspor tak tersentuh). Klik judul seperti biasa = sort. (5) **Peta hari pop-up di-redesain** — dulu `13:1245` (tanggal:nilai — membingungkan, user kira "13" bagian nilai): kini DUA BARIS — tanggal kecil redup di atas + NILAI TEBAL di bawah; sel merah tetap hari tersangka. 726+27 = **753 test**; E2E data asli 37/37 OK.
> **v2.12.2** — **UI/UX FIX BATCH (review "kenapa tabel anomali jadi kecil setelah slicer" + permintaan baru)**: (1) **Bug `WLabel` heightForWidth** — `setSizePolicy` eksplisit lama tanpa sengaja menghapus flag hfw yang dipasang `setWordWrap` → layout memberi hint tabel sizeHint "persegi" (hint 2 baris = 28px diberi **112px**); terukur di data asli jendela 1366×700: tabel Anomali jatuh ke minimum 200px = **6-7 baris terlihat** (rugi 45% viewport vs tanpa slicer). Flag dipulihkan → hint menyusut jujur (14-28px) di **SEMUA tab** (hint ada di setiap kartu). (2) **Slicer kompak gaya Excel** — label dimensi kini INLINE dengan chip (dulu label makan satu baris sendiri: 38px/dimensi; slicer total 147px): 3 baris × 24px + baris ✕ = **100px** (hemat 47px). (3) **Tombol ⤢ Perbesar Tabel & ⛶ Layar Penuh di tab Anomali** (pola tab Banding Periode — permintaan user): ⤢ ciutkan KPI+bar kontrol (viewport 267→405px ≈ 15 baris), ⛶ pop-out **tabel ASLI** (reparent, bukan salinan — centang ✓/sort/pop-up detail tetap hidup; Esc/kembali pulihkan posisi layout utuh). (4) **Angka MINUS otomatis MERAH global** (semua tabel — level model `ForegroundRole`; 0/plus/teks/bool tidak; E2E data asli: 294/294 sel negatif merah). (5) **Judul kolom banding pakai NAMA BULAN** (bukan kata "Pembanding" — alias hanya di `headerData`, data/sort/record tetap kanonik: kontrak `dataframe['Pembanding']` utuh; Tipikal → "Tipikal — median N bulan"). (6) **Kolom JENIS di tabel banding** (Cabang/Item/Baru/Hilang — sumber `agg_jenis` yang sudah dihitung loader; item yang sama tercatat di 2 jenis kini 2 baris terpisah; bulan tanpa agg_jenis = perilaku lama persis → golden v2.10.0 utuh; drill dari baris cabang langsung ter-filter jenis itu). (7) **✓ Follow Up di tab Banding Periode** (halaman Cabang/Item/Baru — Opsi A disetujui): satu centang = SEMUA baris anomali terkait masuk daftar Follow Up yang sama (bulk `add/remove_followup_many` — satu broadcast, satu tulis disk; data asli: 12ms); lepas = keluar sekaligus; baris tanpa pasangan anomali (mis. item hilang) = revert centangan + pesan; sinkron in-place antar-tabel. (8) **Auto-ciut daftar file banding** setelah muat-otomatis sukses (dulu kartu file 299px + tabel hasil cuma 72px ≈ 2 baris; tambah/muat-ulang manual tidak dikejut ciut). (9) Jargon `key_akhir` → "31 hari data"; hint tabel dipendekkan. Hasil ukur data asli 1366×700: tabel Anomali **6-7 → 10 baris** default, **15 baris** sekali klik ⤢, ⛶ tanpa batas; render banding dengan semua fitur baru 87ms; jalur tombol lain tetap level v2.12.1 (chip 1-4ms, ✓ 30ms, buka Follow Up 5ms). 695+31 = **726 test**; E2E 24/24 OK.

> **v2.12.1** — **PERF TOMBOL (permintaan "cek lagi yang bikin lemot tombol tombol dan fix")**: 6 akar lemot dibongkar via profil cProfile data asli 25.901 baris, semua difix TANPA mengubah satu angka pun (golden 484 & skor anomali utuh). (1) `_apply_filters` dulu **menyalin df penuh (25.901×53) SEBELUM mask apa pun** di setiap ganti filter — jalur "kembali/bersihkan/hapus filter" membayar ~21 ms sia-sia per klik; kini state tanpa filter mengembalikan objek apa adanya (mask tetap menghasilkan objek baru — kontrak baca-saja utuh). (2) Pengukuran lebar/tinggi tabel membaca sel via **pandas `iat` per sel** (42.927 panggilan = 1,7 dtk saat render tab Follow Up 797×41) — kini `text_at()`: snapshot numpy dibangun sekali per set/sort + sinkron di jalur mutasi resmi (`setData`/`notify_column_changed`); `data()` Qt tetap live-iat (paint hanya sel terlihat). (3) **Memo display satu slot** membuat toggle slicer bolak-balik (A→B→A) SELALU miss → fingerprint md5 + salinan + objek display baru → **cache fit DataTable tak pernah kena lagi** (regresi v2.12.0 pada skenario unfilter/drill-balik v2.9.0): kini LRU-8 per objek df (weakref) — objek display PERSIS sama per state. (4) **Fingerprint dataset penuh (0,3 dtk) pindah ke thread worker** (pola search_blob) — dulu dibangun malas di thread UI saat pertama dibutuhkan (prune/buka Follow Up) = beku sesaat pasca-pipeline; view memakai reindex O(n). (5) `suspicious_days` vektor numpy (loop 797×31 `.iloc` → mask array; ekuivalensi dikunci oracle). (6) Tabel **lebar** (>24 kolom tampak, mis. rekap Follow Up) memakai konvensi tabel raksasa: wrap mati + elide kanan + tooltip penuh → pengukuran tinggi per sel (32 ribu ukuran) di-skip. Bonus: status bar hanya `setStyleSheet` saat warna berganti; memo enrich perubahan vs bulan-lalu jadi LRU weakref. **Hasil ukur (sandbox, laptop user 2-4× lebih lambat)**: chip slicer balik-state 348→37 ms · bersihkan/hapus filter 350-460→45-60 ms · buka tab Follow Up 3.835→0,305 dtk (**12,6×**) · lepas ✓ di tab Follow Up 0,55→0,13 dtk · render pertama 1,4→0,5 dtk. 663+32 = **695 test**.

> **v2.12.0** — **Tab Follow Up (centang ✓ → shortlist investigasi)**: kolom **✓** di tabel Anomali — klik = baris masuk tab **Follow Up** (tepat setelah Anomali; badge jumlah di judul tab) dalam **format rekap persis buku kerja**: `TOTAL · AVG · MAX · SOURCE DATA · JENIS · KETERANGAN · NAMA BARANG · NAMA RESTO · SATUAN · hari 1..31` (nilai apa adanya — tanpa agregasi baru; skor anomali TIDAK diubah, golden utuh). **Hari mencurigakan diberi warna**: 🔴 merah = hari tersangka (HARI TERSANGKA/HARI MAX — konsisten peta hari pop-up) · 🟠 amber = nilai ≥ 2× rata-rata hari aktif. Tombol **☑ Centang yang tampil** = centang massal hasil filter/slicer saat ini; **lepas centang ✓** (di kedua tab) = keluarkan baris. Daftar **menetap terhadap filter** (shortlist tidak ikut hilang saat menyaring) + **tersimpan otomatis** (`followup.json`, pola filters.json — atomic + backup korup); dataset baru → centangan yang barisnya tak ada lagi **dipangkas otomatis** (notifikasi jujur). Baris kembar identik didedup (data asli: 1.871 grup duplikat — identitas = **sidik jari nilai baris**: 6 kolom kunci + nilai hari non-nol, stabil lintas dtype int/float). **💾 Ekspor Excel**: format rekap + kolom kosong PIC/KATEGORI/PENYEBAB utk diisi petugas (konvensi REKAP MENTAH) — hari mencurigakan ikut berwarna. Anti-lemot: toggle ✓ = 1 sel repaint (dataChanged index tunggal — bukan render ulang; cache fit DataTable tak tersentuh); sinkron antar-tab = update kolom in-place; objek display di-memo per objek df. 621+42 = **663 test**.

> **v2.11.0** — **Slicer multi-select di atas tabel** (tab Anomali + Hari Mencurigakan): baris tombol kilat ala Excel untuk **JENIS** (WASTE·SUSUT·TRIAL) · **KETERANGAN** (dari data) · **STATUS** (4 tingkat, warna severity saat aktif). Klik = toggle nilai, **bisa beberapa sekaligus** (hasil = gabungan); tombol **✕ Bersihkan slicer** mengosongkan ketiganya. State = filter global yang sudah ada (`ctx.active_filters`, list — semantik `_apply_filters` v2.5.1), jadi **chip antar-tab otomatis sinkron** + combo sidebar mengikuti (menampilkan "▪ beberapa dipilih"; pilih nilai di combo = override jadi single — perilaku lama utuh). Anti-lemot: klik beruntun di-*coalesce* debounce 150 ms → **satu broadcast `set_filters_multi`** (satu render, bukan satu per klik); tabel tetap virtualized; profil filter tersimpan kompatibel dengan nilai multi. **Banding Periode sengaja TANPA slicer** (membandingkan file bulan, bukan baris data — keputusan desain). Skor anomali TIDAK diubah (golden utuh). 605+16 = **621 test**.

> **v2.10.3** — **audit deep v2.10.2** (empiris di data asli 25.901 baris + pembanding riil — 40+ cek kontrak: agregat konsisten, tanpa mutasi input, tanpa ±inf, kunci pencocokan per-bulan=0 false-BARU): 2 fix. (1) **nama bulan dari nama file kini toleran underscore** — `WASTE_SEPTEMBER_2026.xlsx` / `01-31_SEPTEMBER_2026.xlsx` dulu terbaca TANPA bulan (regex `\b` menolak underscore = word-character) sehingga label combo & pilihan "bulan lalu TERBARU" diam-diam meleset; kini lookbehind non-huruf menerima `_`/digit, tetap menolak bulan yang menempel huruf (`XSEPTEMBER`/`SEPTEMBERS`). (2) **pop-up drill/layar penuh basi kini ditutup otomatis** — bila hasil banding digambar ulang (run baru / pembanding berganti / combo ditukar) sementara pop-up masih terbuka, tabelnya menampilkan angka konteks LAMA (drill lanjutan sudah ter-guard, tapi tampilannya menyesatkan); toggle ⤢ tetap TIDAK menutup (murni layout). 598+7 = **605 test**.

> **v2.10.2** — **Tabel banding besar + pop-up drill-down + kolom perubahan di anomali**: (1) tab Banding Periode kini punya tombol **⤢ Perbesar Tabel** (ciutkan daftar file → tabel makan seluruh tinggi) dan **⛶ Layar Penuh** (tabel tab aktif di jendela maximized, Esc kembali); (2) **klik 2× baris di SEMUA tab banding** = pop-up rantai rincian **Total → resto → item → hari** — jawaban "total naik, resto mana yang naik, sampai item apa, hari berapa" (`compare_level` per resto/item/per-JENIS + `drill_day_detail` hari 1–31, termasuk normalisasi Waste-per-Hari 30/31 hari); (3) tabel Anomali menambah kolom **BULAN LALU / PERUBAHAN % / PERUBAHAN** (muncul bila ada pembanding; kunci pencocokan resto×item×jenis×keterangan, abaikan besar/kecil huruf) + filter **"Perubahan:"** — memisahkan **lonjakan baru** (Naik Tinggi = kandidat salah input) dari **waste kronis** (Stabil tiap bulan; threshold `TH_CHANGE_*` di config.json); persen perubahan kini bertanda & jelas terbaca (`+35,5%`, `BARU`). Skor anomali TIDAK diubah (golden utuh). 538+60 = **598 test** (+7 audit v2.10.3).

> **v2.10.1** — hotfix Banding Periode: **kolom Status file pembanding tetap "⏳ belum dimuat" padahal notif pemuatan sukses** (laporan user di Windows). Akar: hasil pemuatan dikunci dgn path ternormalisasi `str(Path(...))` — di Windows `pathlib` membalik pemisah path dari dialog Qt (`C:/a/b.xlsx` → `C:\a\b.xlsx`) — sementara daftar file mengunci string path DARI DIALOG, jadi semua lookup (status baris, cache mtime, combo bulan) meleset; efek tersembunyinya: combo pembanding & tabel banding juga kosong. Fix: `load_history_file` kini mempertahankan string path input PERSIS (kunci = apa yang daftar file simpan) + notif jujur "⚠ semua file gagal dimuat" bila 0 bulan aktif (dulu menyesatkan "✓ 0 bulan pembanding aktif"). Daftar file yang sudah tersimpan langsung sembuh tanpa setup ulang. 534+4 = **538 test**.

> **v2.10.0** — **Banding Periode multi-file (history bulan-bulan lalu)**: pembanding kini **DAFTAR workbook** (1 file = 1 bulan, template "REKAP MENTAH" — kolom NAMA BARANG/NAMA RESTO/SATUAN/hari 1–31, **tanpa angka BOM**; file yang Anda upload terverifikasi kompatibel). **Nama bulan dibaca otomatis dari nama file** ("…AGUSTUS 2026…" → "Agustus 2026"; klik 2× baris untuk koreksi manual) dan **daftar file diingat antar sesi** (`history_files.json`, atomic). Dimuat berurutan **di background** (`HistoryWorker` QThread: progress per-file + tombol ⏹ Batal + cache mtime — file tak berubah tidak dibaca ulang; file gagal ditandai merah tanpa menghentikan file lain; ±2–3 dtk/file, UI tetap responsif). Banding **dua-duanya**: (a) **satu bulan pilihan** — ringkasan (Total Waste, **Waste per Hari** menormalkan beda panjang bulan 30/31 hari, cabang/item aktif), per-JENIS, cabang & item mover terbesar, item baru/hilang; (b) **📊 Tipikal** — **median gabungan ≥ 2 bulan** sebagai baseline deteksi perubahan. **Tab Hari Mencurigakan** kini menambah kolom **NILAI BULAN LALU** (nilai item+cabang sama di **tanggal yang sama** bulan sebelumnya), **RASIO VS BULAN LALU** (mis. **4,2×**; golden data asli: MIE 24-Sept 808 vs 194 Agustus), dan **TIPIKAL BEBERAPA BULAN** — plus kalimat bukti tambahan di ALASAN HARI bila ≥ 3× (threshold `TH_HARI_HIST_RATIO`). Saringan **JENIS ∈ {WASTE, TRIAL, SUSUT}** wajib diterapkan saat agregat (bukti data asli: tanpa saringan MIE hari-24 = 43.115 tercampur baris BOM/SO vs **194** yang benar). 476+58 = **534 test**.

> **v2.9.0** — **Tab baru "Hari Mencurigakan"** (jawaban: "potensi salah angka terjadi di **tanggal berapa** 1–31?"): Stage 15 pipeline menghitung bukti per-hari — **HARI TERSANGKA** (tanggal nilai terbesar), **TIPIKAL CABANG LAIN** (median item sama di hari sama di outlet lain), **RASIO VS CABANG LAIN** (mis. **404×**), **SHARE HARI TERSANGKA**, dan **ALASAN HARI** satu kalimat siap baca; BUKTI HARI = YES bila rasio ≥ 5× ATAU share ≥ 50% ATAU pola 10× ATAU waste cuma 1 hari (golden data asli: 484/797 baris non-Normal = 60,7%). **Istilah dimudahkan + tooltip di SEMUA tempat** (permintaan: "bukan hanya S-1"): 12 fragmen sinyal jadi Bahasa awam ("Spike vs AVG" → "Lonjakan vs rata-rata"), kamus `COLUMN_TOOLTIPS` di judul kolom semua tabel, label metrik pop-up, chip S1–S12, KPI, dan kontrol filter — hover = penjelasan sehari-hari; pop-up detail kini punya **peta nilai per hari 1–31** dengan hari tersangka disorot merah. **Perf anti-lambat** (diukur data asli, sandbox): **Hapus Filter 461 → 87–95 ms (≈5×)**, **pencarian 1.456 → ~95 ms (≈15×)** — memo `anomali_df` LRU per tanda tangan filter + cache teks sel model + cache fit lebar/tinggi tabel LRU + blob pencarian (dibangun di worker thread; jebol NUL-separator numpy ditemukan & dihindari). 436+40 = 476 test.

> **v2.8.3** — UX anti-freeze: **apply/unapply filter kini memberi feedback "masih proses"** (keluhan nyata: "waktu aku apply unfilter kok kaya lag/freeze"). Diagnosa terukur di data asli 25.901 baris: rantai filter → refresh tabel berjalan **sinkron di thread UI 75–460 ms** (sandbox) — auto-fit kolom + pengukuran tinggi baris per sel — di laptop user bisa **1–2+ detik beku tanpa umpan balik**. Fix: helper `busy_feedback` membungkus titik tunggal render tabel — **cursor sibuk + pesan status "⏳ Menyarkan & menampilkan data…" dipasang SEBELUM kerja berat** (dijamin tergambar via `processEvents`), **pulih + laporan durasi "✓ … selesai (X ms)"** setelahnya; semua pintu masuk tercakup otomatis (search, dropdown, rentang hari, Hapus Filter, drill-down, dataset baru). Aman bersarang (Qt cursor stack). 436 test.

> **v2.8.2** — hotfix installer: **`SETUP.bat` gagal di langkah [5/5] Verifikasi** pada instalasi baru ("`ModuleNotFoundError: No module named 'matplotlib'`" lalu "[ERROR] Verifikasi gagal") — akarnya BUKAN instalasi gagal, melainkan baris verifikasi `SETUP.bat` masih mengimpor **matplotlib** yang sudah dihapus dari dependensi sejak v2.8.1 (instalasi sebenarnya sukses, hanya ceknya yang basi). Fix: verifikasi & banner `SETUP.bat` kini sinkron dengan `requirements.txt` (5 paket: pandas, numpy, openpyxl, python-calamine, PySide6); daftar dependensi di README diperbaiki; referensi matplotlib mati di `logging_setup.py` dibersihkan; **test kontrak baru** mengunci baris verifikasi `SETUP.bat` ↔ `requirements.txt` agar tidak diverver lagi (431 test). Jika Anda kena error ini: `git pull` (atau unduh ulang) → jalankan `SETUP.bat` ulang — tidak perlu hapus `.venv`.

> **v2.8.1** — penyederhanaan lanjutan + detail pop-up: **5 → 3 view** — tab **Jelajah** & **Waktu** dihapus total bersama modul `charts.py` / `dashboard.py` / `chart_helpers.py` + infrastruktur chart di UI (widget matplotlib tidak lagi diimpor saat start-up). **Panel detail kini POP-UP**: klik baris di Tabel Anomali Ter-ranking membuka jendela non-modal berisi 12 sinyal S1–S12, angka peer, uang, dan tombol drill-down — tabel memenuhi seluruh tinggi view (splitter & tombol "Rapikan Detail" dihapus; hint lama "pilih baris utk detail" dihapus). **Kolom baru "% to BOM"** di tabel anomali per-ranking (waste dibanding penjualan kuantiti — nilai rasio ditampilkan sebagai persen `1,34%`; penanda `Cek` = item tanpa data penjualan); kolom rasio lain (MAX / BOM, TOTAL / BOM, MAX SHARE, LAST DAY SHARE) kini juga tampil sebagai persen. Sheet analisa export (Waste per Hari, Alasan×Hari, Money View, Data Quality) TETAP diexport — modul temporal/priority/data_quality tetap hidup di jalur pipeline & export. Golden regression utuh (25.901/399/41).

> **v2.8.0** — penyederhanaan UI atas permintaan user + ruang vertikal tabel: **8 → 5 view** — tab **Uang**, **Peer**, **Kualitas Data** dihapus total (file view terkait dihapus dari repo; fitur banding 2 cabang A/B, kuadran sistemik, rate league, dan tampilan pemeriksaan DQ ikut pensiun — **cek data_quality TETAP jalan di pipeline & export, sheet export tidak berubah**). **Tabel anomali memanjang ke bawah**: header kartu dirampingkan (judul satu baris + hint digabung — dulu judul wrap 2-3 baris makan ±100px), rasio splitter tabel:detail 3:2 → 5:2, tinggi minimum tabel 200px, tombol baru **"⌃ Rapikan Detail"** menyembunyikan panel detail → tabel memenuhi seluruh tinggi view (diagnostik geometri: di laptop 1024×700 tabel v2.7.0 hanya menampilkan ±3 baris). **Sidebar bisa disembunyikan/dimunculkan**: tombol **☰ Filter** di toolbar / shortcut **Ctrl+Shift+F** — tabel & chart memakai lebar penuh jendela saat sidebar disembunyikan; ukuran splitter dipulihkan saat dimunculkan. Golden regression utuh (25.901/399/41).

> **v2.7.0** — hasil "deep audit v2.6.x + fix" (45 temuan unik dari 3 auditor read-only + audit lanjutan, dipecah 4 gelombang fix paralel): **CRITICAL** — 2 tab Mover "Banding Periode" selalu kosong sejak v2.6.0 (kunci hasil `compare_periods` salah dipetakan); 12 chip sinyal panel detail selalu abu-abu di data riil (panel membaca kolom `_s1.._s12` yang di-drop pipeline sebelum df sampai UI — kini tabel memegang DataFrame PENUH dan chip membaca fragmen teks `ANOMALY REASONS`). **HIGH** — sinyal S11 periode-B hidup lagi (key_akhir pipeline B kini auto-detect dari data mentah, seperti v2.5.1); validasi threshold editor dipulihkan dari v2.5.1 (tolak non-numerik "0,5"/"abc" & nilai ≤ 0 — dulu tersimpan senyap sebagai string ke config.json); `closeEvent` kini menghentikan SEMUA worker — pipeline + export + banding periode (dulu QThread dihancurkan saat masih berjalan = crash/UB); sidebar filter jujur lagi pasca re-run (combo/search/chip tak lagi menampilkan filter lama yang sudah di-reset); breakdown satuan KPI menampilkan total waste sesungguhnya (dulu jumlah baris tampil seolah waste). **MEDIUM/LOW** — `fmt_cell` memformat numpy int/float (pemisah ribuan + rata kanan); tabel >3.000 baris anti-terpotong vertikal (wrap mati + elide kanan "…", tooltip sel tetap teks penuh); 3 chart duplikat Jelajah dihapus (12→9); placeholder pra-run di 5 view (dulu area blank senyap); drill-down nilai kosong/NaN ditolak dengan pesan (bukan tabel kosong senyap); Reset Default 14/20→20/20 key threshold; memo cache filter (perf — `_apply_filters` tak lagi dijalankan 2× per refresh); tombol batal banding periode; penanda hasil banding basi saat data periode A berubah; koersi numerik TOTAL di sheet turunan (string tak lagi ter-`sum` jadi teks); `fmt_id(None)` → ""; plus bersihan dead code era Tkinter (`embed_figure`/FigureCanvasTkAgg, sinyal `run_state_changed` tanpa pelanggan, QSS rule & import mati) dan manifest metode ui/ kini dikunci DUA-ARAH (def baru tanpa update manifest = test gagal). `sample_workbook.xlsx` ikut repo sebagai fixture test (generate ulang via `make_sample.py`). Test: 420 → **432**. Golden regression utuh (25.901/399/41).
>
> **v2.6.1** — fix installer Windows: **`SETUP.bat` kini otomatis membuat `.venv` lokal** (virtual environment) sebelum `pip install` — menutup batas panjang path Windows 260 karakter yang membuat instalasi `PySide6` gagal dengan `OSError: [Errno 2]` di Python Microsoft Store (site-packages-nya terlalu dalam), sekaligus tidak mencemari Python global; `MULAI.bat` otomatis memakai `.venv`; `BUILD_EXE.bat` ikut memakai `.venv`; pesan error install kini memberi 2 solusi konkret (repo di path pendek / aktifkan `LongPathsEnabled` + restart); banner `MULAI.bat` disegarkan ke 8 view v2.6.x. Plus **hardening anti-terpotong UI**: header tabel kini punya lantai lebar = lebar teksnya (tak pernah ter-elide lagi — dulu "NAMA RESTO" tampil "MA REST" di jendela sempit), tabel re-fit saat window di-resize, tabel anomali dirampingkan 10→7 kolom (kolom duplikat panel detail dihapus — mandat "hapus yang tidak perlu"), sidebar menyusut proporsional, kolom JENIS disembunyikan responsif saat sempit — 0 scrollbar horizontal di 1440×900 maupun 1024×700 (dulu 2 kolom tersembunyi di balik scroll bahkan di ukuran default). Core `waste_anomaly/` tak tersentuh.
>
> **v2.6.0** — hasil "rebuild ulang UI": **UI baru PySide6/Qt berorientasi penemuan anomali** — landing langsung ke tabel anomali ter-ranking (skor ↓) + panel detail (12 sinyal, peer, uang, drill-down 1-klik), KPI mengikuti filter, **8 view** (Anomali · Jelajah · Waktu · Uang · Peer · Kualitas Data · Banding Periode · Pipeline) menggantikan 14 tab Tkinter, tabel tanpa cap baris (25.901 baris di-render virtualized + wrap + pewarnaan severity), **jaminan anti-terpotong struktural** (word-wrap semua teks; chart punya lantai ukuran + scroll; kolom tabel auto-fit proporsional; grid chart responsif 2↔1 kolom; tab tidak di-elide tanpa ellips), tombol duplikat/tak perlu dihapus (refresh global & popup log), tombol & fitur lama dipertahankan SEMUA (profil filter, export 10 sheet, compare periode, threshold editor), 2 bug core chart ikut diperbaiki (legend rate-league terpotong sejak lama; label tick weekday saling tumpuk). Core `waste_anomaly/` TIDAK tersentuh — golden regression utuh (25.901/399/41). Dependensi UI baru: `PySide6` (offline, satu kali `pip install`).
>
> **v2.5.1** — hasil "deep audit fitur baru + fix": audit ulang v2.5.0 atas kode asli (23 temuan: 4 HIGH / 12 MEDIUM / 7 LOW) → **isolasi exception per-chart di Dashboard** (DD-H1: sebelumnya satu chart gagal = chip ter-update + chart kosong + tabel stale), **sinkronisasi dropdown KETERANGAN lengkap di 6 titik** (DD-H2: Clear Filter & Muat Profil dulu membiarkan dropdown bohong), **KPI mengikuti filter + label konteks "X dari N baris"** (DD-M3), **rentang hari ketat** (DD-M1: 23.470 baris nol tidak lagi lolos — chip "(baris aktif)"), **search tak lagi cocok 'nan'/'&lt;NA&gt;'** (DD-L4), **FOCUS SCORE rank di subset aktif** (MO-M2: komponen magnitude kini berdaya-pembeda penuh, dulu terkompresi 90,6–100 oleh baris nol), **satuan eksplisit di money_top/judul temporal** (MO-M1), **normalisasi whitespace KETERANGAN** di dropdown/filter/agregat (DQ-M1), **min 30 entri aktif untuk tabel rasio alasan** (TE-M3: rasio sampel-kecil = artefak), **Compare Periode + kolom Hari Data & Waste/Hari** (PE-M1: bias 30-vs-31 hari), **split-source jujur "318 aktif dari 8.221 grup"** (DQ-L1), **format angka Indonesia tunggal** (IN-L1), **coalesce klik ganda** (DD-L2), + hardening `_on_pick` try/except + logging, label 'weekend' → 'pola hari mod-7' + catatan asumsi (TE-M1), + **test kontrak chart interaktif** (klik disimulasikan di Agg → nilai on_click ∈ kolom data; PR-H2).
>
> **v2.5.0** — hasil "kerjakan semua" (gelombang analisa): **4 tab analisa baru** (Temporal — pola hari/weekday; Money View + Benchmark — prioritas magnitude & peer aktif; Data Quality — 7 pemeriksaan otomatis; Compare Periode — bandingkan 2 workbook), **drill-down kini ada di SEMUA tab analisa** (klik chart di Visualisasi, double-click baris di Hasil/Quadrant/Money → filter + lompat ke Dashboard; + dropdown KETERANGAN), **5 chart baru** (waste per hari + highlight hari peak mod-7, weekday effect, heatmap alasan×hari, Pareto item per satuan, top money rows per FOCUS), **export Excel 10 sheet** (+Waste per Hari, Alasan×Hari, Money View, Data Quality), **KPI jujur per satuan**. 4 modul analisa baru + **320 test** (naik dari 150). Detail di **Changelog v2.5.0**.
>
> **v2.4.1** (hasil "double check") — perbaikan **path frozen-mode PyInstaller**: config.json / filters.json / folder data / log kini disimpan BERDAMPINGAN EXE (dulu hilang senyap karena menulis ke _MEIPASS temp yang terhapus saat exit — kebalikan klaim BUILD_EXE.bat), + **12 pesan log duplikat dibersihkan**, + **10 test baru path frozen** (total 150 test).
>
> **v2.4.0** — hasil "kerjakan semua" (2025): **arsitektur modular** (god-object 3.256 baris / 102 metode dipecah jadi paket `ui/` — 14 file mixin, verbatim terverifikasi + 11 test struktural), **cancel run jujur** (hook antar-stage — CPU benar-benar berhenti), **validasi skema input** (anti degradasi senyap header lowercase), **exporter streaming** (anti OOM 100k baris), **logging framework** (rotating file + hook exception Tk), **140 test**, **CI GitHub Actions**, **packaging .exe** + ikon aplikasi. Detail di **Changelog v2.4.0**.

## Cara Pakai

### 1. Setup (sekali saja)
Jalankan `SETUP.bat` di root folder. Script otomatis membuat **`.venv`** (virtual environment lokal) lalu menginstall dependencies ke situ:
- pandas, numpy (data processing)
- openpyxl (Excel I/O)
- python-calamine (Excel READ engine cepat, Rust-based)
- PySide6 (framework UI Qt6)

> **Hardening v2.7.0:** `SETUP.bat` menerima `python` ATAU launcher `py -3`; setelah `.venv` dibuat ia memvalidasi interpreter-nya jalan (`.venv` setengah jadi / rusak otomatis dibuat ulang satu kali); tiap langkah `pip` dicek `errorlevel`-nya — gagal = pesan error jelas + berhenti, bukan lanjut senyap.

> **Kenapa `.venv`? (v2.6.1)** Python dari Microsoft Store menyimpan package di path sangat dalam (`C:\Users\...\AppData\Local\Packages\PythonSoftwareFoundation...\LocalCache\local-packages\...`, ±137 karakter), sedangkan wheel PySide6 memuat file dengan path internal ±143 karakter. 137+143 = 280 > batas Windows **260 (MAX_PATH)** → `pip install PySide6` gagal `OSError: [Errno 2] No such file or directory`. Install ke `.venv` di folder repo memotong total path ±100 karakter → aman, sekaligus mengisolasi dari Python global Anda. `MULAI.bat` otomatis memakai `.venv` kalau ada. Kalau masih gagal: (a) pindahkan repo ke path pendek seperti `C:\Waste`, atau (b) aktifkan Windows Long Path sebagai admin — `reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f` — lalu restart PC.

### 2. Siapkan Workbook Input — `DATA_WASTE.xlsx`

**Workflow Anda:**
```
Query data → Olah di Excel → Save as DATA_WASTE.xlsx → Replace file lama → Run pipeline
```

**Format standar input = `DATA_WASTE.xlsx`** (53 kolom). Anda olah data di Excel dulu (manual / Power Query / formula), lalu save dengan struktur standar ini. Pipeline idempotent — bisa di-run di file yang sudah berisi output sekalipun, semua derived columns akan di-drop & dihitung ulang otomatis.

**Letakkan `DATA_WASTE.xlsx` di mana saja** (folder Downloads, Documents, dll). Browse lewat UI saat run pipeline.

**Struktur 53 kolom yang diharapkan:**

| # | Kolom | Wajib? | Contoh |
|---|-------|--------|--------|
| 0-8 | STATUS, HELPER, MAX TOTAL, AVG TOTAL, TOTAL BOM, % to BOM, TOTAL, AVG, MAX | Opsional (akan dihitung ulang) | kosong / 0 |
| 9 | SOURCE DATA | ✅ Wajib | WASTE BAHAN DAN PACKAGING |
| 10 | JENIS | ✅ Wajib (filter: WASTE/SUSUT/TRIAL) | WASTE |
| 11 | KETERANGAN | ✅ Wajib | Alat/ Mesin, Cancel Nota, Eksternal, Internal, Over Stock, Handling, Kualitas, dll |
| 12 | NAMA BARANG | ✅ Wajib | ADONAN GORENG MEKAR |
| 13 | NAMA RESTO | ✅ Wajib | B.1001.MLGPAR |
| 14 | SATUAN | ✅ Wajib | GR, KG, PORSI |
| 15-45 | 1 .. 31 | ✅ Wajib (qty waste per hari) | 0 / 50 / 100 |
| 46-52 | Status2, KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA GABUNGAN, Count Hari, RANGKING WASTE, Rill % to BOM | Opsional (akan dihitung ulang) | kosong |

> **Idempotent:** Kalau ada kolom output (MAX, AVG, KETERANGAN GABUNGAN, dll) di file Anda — tidak masalah. Stage 1 akan auto-drop semua derived columns & recompute dari kolom hari 1..31.

**Opsional — sheet tambahan untuk aktifkan sinyal BOM & STATUS:**

| Sheet | Nama Kandidat | Kolom |
|-------|---------------|-------|
| BOM | `BOM`, `2  22 05`, `MASTER BOM` | `Nomor #` (= NAMA RESTO), `Nama Barang` (= NAMA BARANG), `TOTAL BOM` |
| DATABASE_SATUAN | `DATABASE_SATUAN`, `Database Satuan`, `SATUAN` | `NAMA ITEM`, `SUSUT`, `TRIAL`, `HANDLING`, `KUALITAS EKSTERNAL`, `KUALITAS`, `KUALITAS INTERNAL`, `EKSTERNAL`, `INTERNAL`, `ALAT MESIN`, `OVERSTOCK`, `CANCEL NOTA` |

Kalau sheet BOM/DATABASE_SATUAN tidak ada, sinyal BOM (S6/S7) & STATUS (Sesuai/Tidak Sesuai) tidak akan trigger tapi pipeline tetap jalan.

### 3. Jalankan (setiap kali)
Jalankan `MULAI.bat`. UI terbuka dengan **4 view** (v2.9.0 — rebuild PySide6; landing default = **Anomali**):

| View | Fungsi |
|------|--------|
| 🎯 Anomali (**default**) | Tabel anomali ter-ranking (skor ↓, tanpa cap baris, pewarnaan severity, kolom TOTAL + % to BOM) + detail **pop-up** saat baris diklik (12 sinyal S1–S12, peer, uang, **peta nilai per hari 1–31**) + drill-down 1-klik (cabang/item/alasan) + ambang "Skor ≥" + KPI mengikuti filter |
| 📅 **Hari Mencurigakan** (v2.9.0) | "Potensi salah angka terjadi di **tanggal berapa** (1–31)?" — tabel anomali + bukti hari: HARI TERSANGKA · NILAI HARI · TIPIKAL CABANG LAIN · RASIO (×) · SHARE · ALASAN HARI; combo hanya-ada-bukti / semua; KPI rasio terbesar; pop-up detail + peta hari; hover judul kolom = arti istilah |
| 🔀 Banding Periode (v2.10.0) | **Bulan berjalan vs daftar file bulan lalu** (1 file = 1 bulan, format REKAP MENTAH — kuantiti tanpa BOM): nama bulan otomatis dari nama file (bisa dikoreksi), daftar **diingat antar sesi**, dimuat di background (+progress+cancel); banding per bulan atau vs **Tipikal** (median beberapa bulan): ringkasan (Total Waste, **Waste per Hari** — menormalkan beda 30/31 hari), per-JENIS, cabang/item bergerak terbesar, item baru/hilang; **v2.10.2: ⤢ Perbesar Tabel + ⛶ Layar Penuh + klik 2× = pop-up drill Total → resto → item → per hari** |
| ▶ Pipeline | Workbook + key akhir + Run/⏹Batal + progress + log + ringkasan + editor threshold |

Sidebar kiri (bisa disembunyikan — ☰ Filter / Ctrl+Shift+F, v2.8.0): pencarian (debounce 300 ms), cabang, status, keterangan, rentang hari, profil filter tersimpan. Saat disembunyikan, tabel memakai lebar penuh jendela. Toolbar atas: **☰ Filter** + **💾 Export Excel** (global — tidak duplikat per tab) + **❓ Bantuan**.

> **Catatan deviasi (v2.7.0):** nama tab di-elide `…` bila jendela sangat sempit — konvensi disengaja (elide kanan + tombol panah scroll tab, bukan terpotong mentah mid-kata); jaminan anti-terpotong tetap berlaku untuk semua konten view.

### 4. Banding vs bulan-bulan lalu (opsional — v2.10.0)

Simpan workbook rekap bulan lalu sesuai kebiasaan Anda (template **REKAP MENTAH**: kolom SOURCE DATA / JENIS / KETERANGAN / NAMA BARANG / NAMA RESTO / SATUAN / hari 1–31 — **tanpa angka BOM**; nama file sebaiknya memuat nama bulan, mis. `REKAP MENTAH_01-31 AGUSTUS 2026_TEGAR.xlsx`). Lalu di tab **🔀 Banding Periode**:

1. Klik **＋ Tambah File…** — bisa pilih beberapa file sekaligus (1 file = 1 bulan; 2–3 bulan ideal).
2. Nama bulan muncul otomatis dari nama file; **klik 2× baris** bila mau mengoreksi. Daftar **diingat antar sesi** — aplikasi dibuka lagi = bulan lalu termuat otomatis di background.
3. Jalankan pipeline bulan berjalan seperti biasa → hasil banding muncul: **Ringkasan** (Total Waste, **Waste per Hari** — adil untuk beda panjang bulan), **Per Jenis**, **Cabang/Item Mover** (naik-turun terbesar), **Item Baru/Hilang**.
4. Combo **"Banding dengan"**: pilih satu bulan tertentu, atau **📊 Tipikal** (median gabungan ≥ 2 bulan) untuk deteksi perubahan.

Tab **📅 Hari Mencurigakan** otomatis menambah kolom **NILAI BULAN LALU** / **RASIO VS BULAN LALU** (tanggal yang sama bulan sebelumnya) saat pembanding tersedia. Tombol **🔄 Muat Ulang** membaca ulang file yang berubah (cache mtime — file sama tidak dibaca ulang).

## Output Excel (10 Sheet) — via tombol "💾 Export Excel" di toolbar

Pipeline berjalan **in-memory** (cepat, idempotent). Setelah selesai, klik **💾 Export Excel** di toolbar untuk menyimpan laporan:

| Sheet | Isi |
|-------|-----|
| Detail | Semua baris — kolom mengikuti M code Final order (~70 kolom) |
| Anomali Prioritas | Hanya baris dengan `ANOMALY STATUS` = Prioritas Tinggi + Potensi Anomali |
| Per Cabang | Ringkasan per NAMA RESTO (jumlah baris, total waste, count anomali per status) |
| Top Items | Top 20 item by TOTAL waste (rank, total, max, cabang terpengaruh, count prioritas) |
| Pareto Alasan | Group by KETERANGAN — sum TOTAL, persentase, cumulative % |
| Log Run | Timestamp, parameter, summary stats, log lines pipeline |

> Export berjalan di background thread (UI tetap responsif) dengan penanganan `PermissionError` ramah: kalau file sedang dibuka di Excel, muncul pesan jelas "tutup dulu lalu ulangi". Perf: ~27 detik untuk 25.901 baris × 93 kolom (dulunya ~110 detik).

## Drill-Down Interaktif — tab Anomali + sidebar filter (pusat analisa)

Tab **Anomali** (default) adalah pusat analisa: KPI strip mengikuti filter,
tabel anomali ter-ranked skor (klik header = sort; klik baris = detail
pop-up), dan ambang **Skor ≥** (0–19) untuk menyembunyikan anomali
ber-skor rendah.

### KPI Strip (6 kartu — tab Anomali)
| Card | Warna | Isi |
|------|-------|-----|
| TOTAL BARIS | slate | Jumlah baris terfilter |
| PRIORITAS TINGGI | red | Count anomali prioritas tinggi |
| POTENSI ANOMALI | orange | Count potensi anomali |
| PERLU REVIEW | amber | Count perlu review |
| TOTAL WASTE | teal | Sum TOTAL waste (qty) + breakdown per satuan |
| CABANG | purple | Jumlah cabang unik |

Label konteks "[KPI terfilter: X dari N baris]" jujur + catatan satuan
(agregat lintas satuan, indikatif — v2.7.0: breakdown menampilkan total
waste sesungguhnya per satuan, bukan jumlah baris).

### Cara drill-down (6 cara — state filter tunggal dipakai semua view)
1. **Search box** (sidebar) — free-text search di semua kolom (debounce 300 ms)
2. **Dropdown Cabang** (sidebar) — pilihan dari data PENUH, tidak menyusut saat drill (DD-M3)
3. **Dropdown Status anomali / Keterangan** (sidebar)
4. **Rentang hari (HARI MAX)** (sidebar) — 1-31; baris nol tidak lolos (DD-M1)
5. **Double-click baris tabel** (Anomali) — drill-down ke cabang+item baris itu
6. **Pop-up detail** (klik baris di Anomali) — tombol 🏬 Fokus cabang ini / 📦 Fokus item ini / 🏷 Fokus alasan ini (drill-down 1-klik)

Filter profile Save/Load: simpan state filter ke `filters.json`, load lagi
kapan saja. Filter aktif muncul sebagai ringkasan chip di sidebar. Klik
**✕ Hapus Semua Filter** untuk clear semua.

### Tabel data (virtualized — tanpa cap baris)
- Sortable columns (klik header — numeric-aware, NaN di akhir; kolom % to BOM sort numerik dengan 'Cek' di akhir)
- Status coloring (red/orange/amber/green sesuai ANOMALY STATUS, per baris)
- TANPA cap baris: 25.901 baris di-render virtualized (dulu pagination max 500)
- Klik baris → pop-up detail; double-click row → drill-down cabang+item
- Kolom auto-fit proporsional + lantai lebar header + word-wrap; tabel >3.000 baris otomatis wrap-mati + elide kanan `…` (tooltip sel tetap teks penuh — v2.7.0)
- Kolom **% to BOM** tampil sebagai persen (`1,34%`); `Cek` = item tanpa data penjualan
- Di jendela sempit (laptop 1024): JENIS & KETERANGAN disembunyikan responsif (muncul lagi saat melebar) supaya kolom inti + % to BOM tetap muat tanpa scrollbar horizontal — alasan tetap terlihat di pop-up detail

### Workflow Analisa Contoh
```
1. Tab Pipeline → pilih workbook → Mulai Pipeline → buka tab Anomali
2. Lihat KPI strip + tabel anomali ter-ranked (skor ↓) + kolom % to BOM
3. Klik baris → pop-up detail: 12 chip sinyal, angka peer, uang, konteks
4. Tombol "🏬 Fokus cabang ini" di pop-up → tabel ter-filter cabang itu
5. Search "Cancel Nota" → tambah filter keterangan
6. 💾 Export Excel (toolbar) → laporan 10 sheet dari hasil pipeline
```

## View & Modul yang DIHAPUS (v2.8.0 + v2.8.1)

Atas permintaan user, UI disederhanakan bertahap — 8 view → 5 view
(v2.8.0) → **3 view** (v2.8.1):

- **v2.8.0** — tab **Uang** (money view, Pareto item), **Peer** (banding
  2 cabang A/B, kuadran anomali, rate league, benchmark SUSUT), **Kualitas
  Data** (tampilan 7 pemeriksaan DQ).
- **v2.8.1** — tab **Jelajah** (chart interaktif + tabel 5 sheet + 9 chart
  statistik) dan **Waktu** (pola waste per hari / kelas hari mod-7),
  beserta modul `charts.py`, `dashboard.py`, `chart_helpers.py`, widget
  chart di UI, dan `_build_derived_sheets` (sheet turunan kini hanya
  dibangun jalur export).

Yang TIDAK hilang:
- Metrik pembanding peer: sinyal **S8/S9** (outlier peer), pop-up detail
  Anomali (PEER COUNT, PEER MEDIAN TOTAL/MAX, rasio ke median), prioritas
  magnitude di scoring.
- **Cek data_quality tetap jalan** di pipeline setiap run & ikut ke export
  Excel (sheet Data Quality) — hanya tampilan tab-nya yang dihapus.
- **Sheet analisa export tetap lengkap** (Waste per Hari, Alasan×Hari,
  Money View, Data Quality) — modul temporal/priority tetap hidup.
- Analisa pola hari masih bisa dilakukan lewat rentang hari (HARI MAX)
  + kolom HARI MAX / MAX SHARE / LAST DAY SHARE di pop-up detail, dan
  sheet "Waste per Hari" di laporan export.

Sidebar filter (drill-down 6 cara) kini juga bisa **disembunyikan** lewat
tombol **☰ Filter** di toolbar atau **Ctrl+Shift+F** — tabel memakai
lebar penuh jendela.

## 12 Sinyal Anomali (S1-S12)

Nama sinyal v2.9.0 = **Bahasa awam** (fragmen `ANOMALY REASONS` + chip UI;
perubahan dari "Spike vs AVG" dkk. — permintaan user). Trigger & skor tidak
berubah. Hover chip di pop-up detail / judul kolom tabel = penjelasan lengkap.

| # | Nama (v2.9.0, awam) | Nama lama (teknis) | Trigger | Skor |
|---|------|------|---------|------|
| S1 | Lonjakan vs rata-rata harian | Spike vs AVG | `Count≥2 & MAX/AVG≥3` | 1 |
| S2 | Lonjakan vs hari aktif | MAX vs AVG Aktif | `Count≥3 & MAX/AVG_AKTIF≥2.5` (≥4 → skor 2) | 1 atau 2 |
| S3 | Lonjakan vs nilai tengah | MAX vs Median Aktif | `Count≥3 & MAX/MEDIAN_AKTIF≥3` | 2 |
| S4 | Terpusat di satu hari | MAX Share | `MAX/TOTAL≥0.70` (≥0.50 → skor 1) | 1 atau 2 |
| S5 | Jauh di atas hari kedua | MAX vs Second Max | `Count≥2 & MAX/SECOND_MAX≥3` | 1 |
| S6 | Puncak harian vs BOM | MAX / BOM | `MAX/TOTAL_BOM≥0.50` (≥0.25 → skor 1) | 1 atau 2 |
| S7 | Total bulanan vs BOM | TOTAL / BOM | `TOTAL/TOTAL_BOM≥1.00` (≥0.50 → skor 1) | 1 atau 2 |
| S8 | Puncak vs cabang lain | Peer MAX | `PeerCount≥3 & MAX/PeerMedMax≥3` (≥2 → skor 1) | 1 atau 2 |
| S9 | Total vs cabang lain | Peer TOTAL | `PeerCount≥3 & TOTAL/PeerMedTot≥3` | 1 |
| S10 | Waste hanya satu hari | Single-day event | `Count=1 & (MaxBOM≥0.10 atau MaxPeer≥2)` | 1 |
| S11 | Menumpuk di hari terakhir | Last Day Share | `LastDay/TOTAL≥0.70` | 1 |
| S12 | Pola 10× (mungkin salah ketik) | Scale Signal | heuristic rasio (8-12 / 80-120 / 800-1200 / 8000-12000) | 2 |

**Max skor = 18.** Status final:
- `≥ 8` → **Prioritas Tinggi**
- `≥ 5` → **Potensi Anomali**
- `≥ 3` → **Perlu Review**
- `else` → **Normal**

## Testing

**781 test** — golden regression end-to-end (fixture `DATA_WASTE.xlsx` 25.901 baris), unit test 12 sinyal S1–S12, join BOM & normalisasi kunci, presisi float, kontrak summary dict, validasi skema, cancel hook antar-stage, exporter dual-mode, logging framework, path frozen-mode, semantik filter (v2.5.1), 14 test struktural paket ui/ v2.6.0 (modul ada, mixin lama tak kembali, kontrak shared, kontrak view refresh/on_shown, worker QThread, manifest metode, MainWindow offscreen, infra chart dihapus), **49 test regresi fix audit v2.7.0** (gelombang 1–4: kontrak banding periode + closeEvent worker + memo filter; record penuh panel detail + 12 chip sinyal + fmt numpy + tabel besar; validasi threshold + default 20/20 key; manifest dua-arah + lantai header tabel + `fmt_id(None)` + versi), **dan 27 test regresi v2.8.0+v2.8.1** (3 view + file view/modul chart dihapus + tabel memanjang penuh + pop-up detail + kolom % to BOM + sidebar hide/unhide + help jujur; test view/chart lama dihapus jujur bersama subjeknya: −13 kontrak chart, −12 gelombang-3 view, −2 derived-sheets, −2 Pareto), **plus 2 test kontrak v2.8.2** (baris verifikasi SETUP.bat wajib sinkron dengan requirements.txt — anti bug "import matplotlib" basi), **dan 5 test v2.8.3** (busy feedback: cursor sibuk aktif selama render & dipulihkan; jalur sinyal filter terbungkus; pesan status ⏳/✓ terkirim; helper aman bersarang; kontrak sumber titik-tunggal), **plus 40 test v2.9.0** (Stage 15 day_focus unit + golden hari tersangka data asli + tab Hari Mencurigakan offscreen + istilah awam & tooltip kontrak + cache perf), **plus 60 test v2.10.0** (label bulan dari nama file; saringan JENIS + golden MIE 194 vs 43.115; agregat & banding kuantiti — arah %, mover, baru/hilang; Tipikal median; bukti hari vs bulan lalu + threshold config; persistensi daftar file atomic + backup korup + frozen-path; HistoryWorker cancel + file-gagal-tidak-menggagalkan; PeriodeView offscreen multi-file + combo + edit label + hapus + cache mtime; HariView kolom bulan-lalu + memo objek; istilah & format kolom baru; golden data asli 2 workbook), **plus 4 test v2.10.1** (path hasil loader = persis string input — regresi Windows dialog Qt '/' vs pathlib '\\', direproduksi di Linux via path '/./'; worker mengunci path entri; kolom Status berubah '✓' + combo terisi; notif jujur saat semua file gagal), **plus 60 test v2.10.2** (compare_level: level resto/item/per-JENIS + per-day 30/31 + urutan selisih; drill_day_detail: hari 1–31 + puncak + string spasi; agregat baru agg_jenis/agg_detail + typical median; classify_change: 6 kategori + batas + config + anti-noise min-abs; change_vs_history: kunci persis resto×item×jenis×keterangan + casefold + tanpa-mutasi + fallback kunci kasar + tipikal; format `+35,5%`/`BARU`; baseline bersama combo↔Anomali dgn signal identitas; UI: toggle ⤢, layar penuh ⛶, rantai drill resto→item→hari semua tab, breadcrumb, filter Perubahan, tanpa-pembanding = tabel identik), **plus 7 test v2.10.3** (regex bulan underscore: diterima + huruf tetap ditolak + pola lama utuh; pop-up basi: clear & render-ulang menutup, toggle ⤢ tidak), **plus 16 test v2.11.0** (SlicerBar: klik chip → pending → set_filters_multi satu broadcast; multi/uncheck → list/kanonik-None; sinkron dua arah combo-sidebar ↔ chip + placeholder 'beberapa dipilih' + no-op; reset & dataset baru → chip bersih & repopulasi JENIS/KETERANGAN/STATUS; FlowLayout membungkus; set_filters_multi: emit sekali + kunci asing diabaikan + memo invalid; _apply_filters list status/keterangan ≡ single + normalisasi keterangan). **dan 42 test v2.12.0** (fingerprint: deterministik + dtype-stabil + kembar identik menyatu/nilai-beda terbeda + hari-nol tak mengubah identitas; select dedup kembar; suspicious_days: merah tersangka → fallback HARI MAX per-baris + amber ≥2× rata-rata aktif + merah menang + guard rata-rata ≤ 0; persistensi roundtrip atomic + korup → backup .bad; AppContext: toggle no-op tanpa broadcast + add_many satu broadcast & dedup batch + clear + followup_df dataset-penuh + prune data-baru + memo per data_version; model: flags/CheckState/DisplayRole kosong/setData enum & int + sort ✓ + penanda (fp, kolom) stabil lewat sort + notify_column_changed; AnomaliView klik mouse nyata + tombol massal + sinkron in-place tanpa reset + memo objek display; FollowUpView format rekap + lepas centang + pesan arahan; export: header rekap + serah-terima + fill merah/amber + freeze/autofilter + dtype numerik np.int64; MainWindow badge + isolasi followup.json; pop-up basi ditutup saat baris keluar daftar) Jalankan setiap kali mengubah kode — angka golden berubah tanpa alasan = regresi. **Dan 32 test v2.12.1** (perf tombol: _apply_filters fast-path tanpa salinan + objek-sama + konten benar + kolom-tak-ada + baca-saja; text_at ≡ data() display + kolom centang kosong + data() TETAP hidup setelah mutasi df langsung (regresi desain) + notify menyegarkan snapshot + setData sinkron + sort membangun ulang; LRU display bolak-balik A→B→A objek sama + nilai ✓ disegarkan + data_ready membersihkan + reindex fps ≡ md5 lokal + fallback; set_dataset memetik followup_fps worker + tanpa-fps bangun malas + index-tak-cocok ditolak; suspicious_days ekuivalensi oracle loop lama (acak + tanpa tersangka + tanpa avg + sebagian kolom hari + hari-tak-ada-di-kolom + input list); tabel lebar wrap mati + elide + refit no-op + anomali wrap nyala + raksasa utuh; status bar stylesheet hanya saat warna berganti). **Dan 27 test v2.12.3** (Opsi A: peta ✓ banding hanya baris anomali + peta penuh utk lepas + fallback tanpa kolom status + baris tanpa anomali ditolak + lepas membersihkan noise warisan; Follow Up BULAN LALU: kolom+alias+nilai join benar + tanpa baseline = identik + history_ready dirty; HariView JENIS keluar narrow_hide + ⤢ toggle + ⛶ reparent/pulihkan/idempoten/guard; FilterHeader: setup + kolom kanonik + menu nilai/apply/None + state awal dari state_fn + Pilih Semua + tombol sort + cari + debounce + tabel tanpa mapping perilaku biasa + integrasi AnomaliView (ctx + render ulang + slicer sinkron + klik funnel tak memicu sort) + Follow Up filter lokal (daftar/ekspor tak tersentuh + lepas + refresh mempertahankan); peta hari format baru tanpa 'N:nilai'). **Dan 28 test v2.12.4** (sidebar dihapus: tanpa aksi ☰/shortcut/atribut + central QTabWidget lebar penuh + 5 tab utuh + tanpa widget filter; SlicerBar/FlowLayout dihapus dari widgets + view tanpa _slicer; hint 💡 dihapus dari SEMUA view (sweep findChildren) + _HINT_BASE/_hint hilang; funnel all_cols: flag + skip + hit-test kolom non-mapping + menu kolom numerik + kolom ✓ di-skip; AnomaliView: semua kolom tampak ber-funnel + filter TOTAL lokal (ctx tak tersentuh) + lepas pulih + memo mask A→B→A objek sama + ☑ Centang yang tampil mengikuti mask + tombol ✕ Hapus Filter (global+lokal+skor) + dataset baru reset lokal; HariView semua kolom + funnel lokal kolom non-mapping + kolom mapping tetap global; Follow Up: kolom hari 1-31 ber-funnel + filter lokal (daftar/ekspor tak tersentuh); PeriodeView: semua halaman ber-funnel + bahan halaman tersimpan + mask halaman items + state funnel + lepas pulih; dialog layar penuh tanpa hint tapi Esc di judul + tombol Kembali tetap). **Dan 31 test v2.12.2** (WLabel hfw aktif + tinggi jujur mengikuti lebar + < sizeHint persegi; slicer kompak label-inline + tinggi ≤115px; minus merah: float/np-int negatif merah, 0/plus/teks/bool/NaN tidak, prioritas penanda hari; remove_followup_many satu broadcast + no-op + dedup batch; compare_quantity +JENIS split nilai + branch/baru/hilang per jenis + fallback tanpa agg_jenis = struktur lama + satu sisi; header nama bulan di headerData + frame mentah tetap 'Pembanding' + label Tipikal median; ✓ banding: centang item/cabang massal + sinkron in-place antar tabel + baris tanpa pasangan di-revert + gone/summary tanpa ✓; auto-ciut hanya jalur muat-otomatis (manual tidak); AnomaliView ⤢ toggle KPI/kontrol + ⛶ reparent-pulihkan + idempoten + guard kosong; fmt_run_label tanpa jargon). **Dan 12 test v2.12.5** (_header_font = family chain + 13px + DemiBold dari konstanta theme (dipakai QSS & lantai); lantai header diukur font QSS; piksel strip [w−24, w] bersih dari teks + ikon funnel terlukis; tutup menu mencatat waktu; klik-ganda artefak pasca-tutup ditelan; klik ganda sah setelah guard / tabel tanpa menu tetap hidup; klik tunggal pilih-baris tetap hidup dalam jendela guard; zona hit funnel baru [w−24, w−2] pusat ikon right−12).

## Packaging — EXE Standalone

Jalankan `BUILD_EXE.bat` di Windows (butuh Python + SETUP.bat sekali). Hasil: `dist/WasteAnomalyDetection.exe` — aplikasi jalan **tanpa Python** di PC lain, lengkap dengan ikon (`assets/app_icon.ico`). PyInstaller di-install otomatis; konfigurasi build ada di `waste_anomaly.spec`.

## Struktur Project

```
Waste/
├── MULAI.bat                       ← ENTRY POINT (buka UI 4 view)
├── SETUP.bat                       ← One-time install (buat .venv + pip install, hardened v2.7.0)
├── BUILD_EXE.bat                   ← Build .exe standalone (PyInstaller)
├── waste_anomaly.spec              ← Konfigurasi PyInstaller (icon, datas)
├── requirements.txt                ← Dependensi pinned (pandas 2.2.x; matplotlib DIHAPUS v2.8.1)
├── README.md                       ← File ini
├── LICENSE                         ← MIT
├── .gitignore
├── .gitattributes                  ← eol .bat = CRLF (ZIP-download Windows, V26-M16)
├── ui_app.py                       ← LAUNCHER tipis (entry point lama tetap jalan)
├── ui/                             ← PAKET UI (v2.6.0 — rebuild PySide6)
│   ├── __init__.py                ← Eksport lazy (main, MainWindow)
│   ├── shared.py                  ← Kontrak publik (APP_DIR, _apply_filters, fmt_id)
│   ├── theme.py                   ← Palet warna + QSS global
│   ├── state.py                   ← AppContext: state tunggal + signal Qt
│   ├── models.py                  ← PandasTableModel (tabel virtualized, sort, severity,
│   │                                 fmt_cell + fmt_pct utk kolom rasio % — v2.8.1)
│   ├── workers.py                 ← PipelineWorker / ExportWorker / HistoryWorker (QThread,
│   │                                 v2.10.0: muat file pembanding di background)
│   ├── widgets.py                 ← Blok anti-terpotong: WLabel, DataTable
│   │                                 (auto-fit + wrap), KpiStrip, StatusChip
│   ├── app.py                     ← MainWindow (toolbar + sidebar + 3 view) + main()
│   ├── view_anomali.py            ← View 1 Anomali (default): ranking + % to BOM + pop-up detail + peta hari
│   ├── view_followup.py            ← View 2 Follow Up (v2.12.0): shortlist centang ✓ + ekspor
│   │                                 + DetailDialog pop-up + drill (v2.8.1)
│   ├── view_hari.py               ← View 2 Hari Mencurigakan (v2.9.0): bukti hari 1-31
│   │                                 + bukti tanggal-sama bulan lalu (v2.10.0)
│   ├── view_periode.py            ← View 3 Banding Periode: multi-file bulan lalu +
│   │                                 Tipikal median (v2.10.0)
│   └── view_pipeline.py           ← View 3 Pipeline (+ ringkasan + threshold editor)
├── assets/                         ← Ikon aplikasi (ico + png)
├── make_sample.py                  ← Generate sample workbook untuk testing
├── sample_workbook.xlsx            ← Fixture test in-repo (v2.7.0 — hasil make_sample.py)
├── tests/                          ← Test suite pytest (781 test)
│   ├── conftest.py
│   ├── fixtures/ui_methods_manifest.txt  ← Manifest def top-level ui/ (kunci struktural DUA-ARAH, v2.7.0)
│   ├── test_pipeline_regression.py ← Golden regression 25.901 baris (14 test)
│   ├── test_signals.py             ← Unit test S1–S12 (54 test)
│   ├── test_schema_and_cancel.py   ← Validasi skema + cancel hook (13)
│   ├── test_exporter.py            ← Exporter dual-mode (normal/streaming) (13)
│   ├── test_bom_join.py            ← Join BOM numerik (7)
│   ├── test_key_normalization.py   ← Normalisasi kunci join (13)
│   ├── test_float_precision.py     ← Presisi 15 digit (idempotency) (10)
│   ├── test_logging.py             ← Logging framework (5)
│   ├── test_frozen_paths.py        ← Path frozen-mode exe (seed sidecar) (10)
│   ├── test_temporal.py            ← Analisa temporal (52)
│   ├── test_priority.py            ← Money view + benchmark peer (41)
│   ├── test_data_quality.py        ← 7 pemeriksaan kualitas data (58)
│   ├── test_period_compare.py      ← Compare periode bulan-ke-bulan (23)
│   ├── test_filter_semantics.py    ← Semantik filter + fmt_id (26)
│   ├── test_ui_structure.py        ← Struktur paket ui/ (manifest + offscreen) (14)
│   ├── test_v270_wave1.py          ← Regresi fix audit v2.7.0 gel. 1 (8; v2.10.0:
│   │                                 kontrak PeriodWorker pindah ke test_v2100.py)
│   ├── test_v270_wave2.py          ← Regresi fix audit v2.7.0 gel. 2 (23)
│   ├── test_v270_wave3.py          ← Regresi fix audit v2.7.0 gel. 3 (6)
│   ├── test_v270_wave4.py          ← Regresi fix audit v2.7.0 gel. 4 (10)
│   ├── test_v280.py                ← Regresi v2.8.0–v2.8.3: 3 view + pop-up detail
│   │                                 + kolom % to BOM + sidebar + busy feedback (32)
│   ├── test_v290.py                ← Regresi v2.9.0: Stage 15 hari tersangka + tab
│   │                                 Hari Mencurigakan + istilah awam + cache perf (37)
│   ├── test_v2100.py               ← Regresi v2.10.0+v2.10.1: pembanding multi-file +
│   │                                 tipikal + bukti bulan-lalu + fix path status (64)
│   ├── test_v2102.py               ← Regresi v2.10.2+v2.10.3: drill-down banding +
│   │                                 kolom perubahan + audit underscore/pop-up basi (74)
│   ├── test_v2110.py               ← Regresi v2.11.0: slicer multi-select (16)
│   ├── test_v2120.py               ← Regresi v2.12.0: tab Follow Up (42)
│   ├── test_v2121.py               ← Regresi v2.12.1: perf tombol (32)
│   ├── test_v2122.py               ← Regresi v2.12.2: UI/UX fix batch (31)
│   ├── test_v2123.py               ← Regresi v2.12.3: Opsi A + BULAN LALU + filter header (27)
│   ├── test_v2124.py               ← Regresi v2.12.4: sidebar/slicer dihapus + funnel semua kolom + hint dihapus (28)
│   └── test_v2125.py               ← Regresi v2.12.5: header anti-terpotong (font QSS + strip) + guard klik-ganda pasca menu funnel (12)
├── .github/workflows/ci.yml        ← CI: matrix Python × OS, lint + 781 test
├── waste_anomaly/
│   ├── __init__.py                 ← __version__ single-source (2.10.1)
│   ├── frozen.py                   ← Resolusi path PyInstaller exe vs dev (v2.4.1)
│   ├── config.json                 ← Thresholds + sheet name candidates (version 2.10.1)
│   ├── pipeline.py                 ← Orchestrator 14 stage + cancel_check (in-memory)
│   ├── schema.py                   ← Validasi skema input (anti degradasi senyap)
│   ├── logging_setup.py            ← Rotating file log + hook exception
│   ├── loader.py                   ← Excel loaders (auto-detect sheet + normalisasi 15 digit)
│   ├── stages.py                   ← 14 stage replika M code (idempotent v2.3.2)
│   ├── day_focus.py                ← Stage 15 (v2.9.0): bukti hari tersangka per anomali
│   ├── signals.py                  ← 12 sinyal anomali + composite score (max 19)
│   ├── temporal.py                 ← Analisa temporal (waste/hari, weekday, alasan×hari)
│   │                                 — dipakai export + KPI unit note
│   ├── priority.py                 ← Money view + benchmark peer — dipakai export
│   ├── data_quality.py             ← 7 pemeriksaan kualitas data — pipeline + export
│   ├── period_compare.py           ← Banding 2 periode + auto key_akhir
│   ├── period_history.py           ← Pembanding multi-file: label bulan dari nama
│   │                                 file + agregat kuantiti + Tipikal median +
│   │                                 bukti hari vs bulan lalu + persist (v2.10.0)
│   ├── filters.py                  ← Filter profile persistence
│   ├── followup.py                 ← Identitas baris + daftar follow-up + export (v2.12.0)
│   ├── exporter.py                 ← Multi-sheet xlsx writer + mode streaming
│   └── utils.py                    ← Helper (load_config, norm_text, dll)
├── data/                           ← (opsional) letakkan DATA_WASTE.xlsx di sini
│   └── README.md
├── logs/                           ← (auto-generated) rotating file log
├── output/                         ← Output Excel tersimpan di sini
│   └── .gitkeep
└── filters.json                    ← (auto-generated) saved filter profiles
```

## Stage Pipeline (14 Stage, replika M code)

| Stage | Fungsi |
|-------|--------|
| 1 | Source & cleanup: drop TOTAL/PIC/KATEGORI/STATUS/PENYEBAB, coerce hari 1-31 numeric, filter JENIS ∈ {SUSUT, TRIAL, WASTE} |
| 2 | Per-row daily stats: TOTAL, MAX, AVG, AVG AKTIF, MEDIAN AKTIF, SECOND MAX, HARI MAX, rasio, share, single-day, scale-signal |
| 3 | Reason summary: KETERANGAN GABUNGAN, KONTRIBUSI TERBESAR, SOURCE DATA GABUNGAN |
| 4 | Group totals: MAX TOTAL, AVG TOTAL by (KETERANGAN, NAMA BARANG, SOURCE DATA) |
| 5 | BOM join: TOTAL BOM, Rill % to BOM |
| 6 | Peer summary: PEER COUNT, PEER MEDIAN TOTAL, PEER MEDIAN MAX by (NAMA BARANG, JENIS, KETERANGAN, SOURCE DATA) |
| 7 | Top 3 summary: TopTotal list, TopBOM list per (JENIS, NAMA BARANG) |
| 8 | Merge semua summary (left joins) |
| 9 | DATABASE_SATUAN join: 11 kolom kategori helper |
| 10 | Helper / STATUS (Sesuai/Tidak Sesuai) / % to BOM |
| 11 | 12 sinyal anomali + ANOMALY SCORE + STATUS + REASONS + KATEGORI ANOMALI + RANGKING WASTE |
| 12 | Expand analysis (no-op — sudah di-expand di stage 11) |
| 13 | Cleanup temporary columns |
| 14 | Final column order (mengikuti M code) |

## Persyaratan

- **Python 3.10+** (cek: `python --version`)
- **Windows** untuk `.bat` files (Mac/Linux: jalankan `python ui_app.py` langsung)
- Dependencies: pandas, numpy, openpyxl (di-install oleh `SETUP.bat`)

## Cara Download & Update

1. Download ZIP repo: https://github.com/anandategarch/Waste/archive/refs/heads/main.zip
2. Ekstrak
3. Jalankan `SETUP.bat` (sekali saja)
4. Siapkan `DATA_WASTE.xlsx` Anda (query → olah di Excel → save dengan struktur 53 kolom standar)
5. Jalankan `MULAI.bat` → Browse `DATA_WASTE.xlsx` Anda → Mulai Pipeline

**Untuk run berikutnya (data baru):**
1. Replace `DATA_WASTE.xlsx` Anda dengan file baru (overwrite / copy paste)
2. Jalankan `MULAI.bat` → Browse file → Mulai Pipeline

> **Tip:** Pipeline idempotent. Bisa di-run di file output sendiri (`Waste_Anomaly_Report.xlsx`) atau file `DATA_WASTE.xlsx` yang sudah berisi output M code — semua derived columns akan di-drop & dihitung ulang oleh Stage 1.

## CLI Mode (tanpa UI)

Pipeline berjalan **in-memory** — tidak menulis file Excel. Menulis laporan
adalah panggilan TERPISAH lewat `exporter.export_to_excel` (jalur yang sama
dipakai tombol 💾 Export Excel di UI):

```python
from waste_anomaly.pipeline import run_pipeline
from waste_anomaly.exporter import export_to_excel
from waste_anomaly.utils import load_config

summary = run_pipeline(
    workbook_path="data/rekap.xlsx",
    key_akhir=31,
    progress_callback=lambda msg, pct: print(f"[{pct:.0f}%] {msg}"),
)
df = summary["df"]  # DataFrame hasil semua stage (kolom output lengkap)
print(summary["total_rows"], "baris •", summary["prioritas_count"], "prioritas")

result = export_to_excel(
    df, "output/Waste_Anomaly_Report.xlsx",
    config=load_config(),
    key_akhir=summary["key_akhir"],
    log_lines=summary["log"].splitlines(),
)
print(result["output_path"])
```

## Custom Thresholds

Edit `waste_anomaly/config.json` → section `thresholds`. Atau pakai **editor threshold di tab Pipeline** (card "Threshold & Konfigurasi" — Simpan config.json / Reset Default). v2.7.0: editor kembali memvalidasi nilai (non-numerik / ≤ 0 ditolak dengan pesan, tidak lagi tersimpan sebagai string).

```json
{
  "thresholds": {
    "TH_SPIKE": 3,
    "TH_MAX_AVG_AKTIF": 2.5,
    "TH_PEER_HIGH": 3,
    "STATUS_PRIORITAS": 8,
    "STATUS_POTENSI": 5,
    "STATUS_REVIEW": 3,
    "S2_SCORE2_MIN": 4,
    "S10_BOM_MIN": 0.10,
    "QUADRANT_THRESHOLD": 0.5,
    ...
  }
}
```

> Konfigurasi korup otomatis diperingatkan (warning di log + tab Ringkasan/Pipeline) dan pipeline lanjut dengan default — tidak lagi diam-diam mengganti threshold.

## Troubleshooting

| Error | Solusi |
|-------|--------|
| `Tidak menemukan sheet untuk 'rekap_mentah'` | Pastikan workbook punya sheet `DATA_WASTE` / `Sheet1` / `REKAP_MENTAH` / `DATA`. Atau edit `config.json` → `input_sheets.rekap_mentah` untuk tambah nama kandidat. |
| `BOM sheet tidak ditemukan` | BOM join dilewati. Sinyal S6/S7 tidak trigger. Tambahkan sheet `BOM` / `MASTER BOM` untuk mengaktifkan. |
| `DATABASE_SATUAN tidak ditemukan` | Kolom HELPER/STATUS dari input dipertahankan; kalau tidak ada sama sekali tidak bisa dihitung ulang. Tambahkan sheet `DATABASE_SATUAN` untuk mengaktifkan. |
| `File .xls` | Tidak didukung — save-as `.xlsx` dulu. |
| `File output sedang dibuka di Excel` | Tutup filenya di Excel, lalu klik Export ulang (pesan errornya sekarang jelas). |
| `ModuleNotFoundError: pandas / PySide6` | Jalankan `SETUP.bat` dulu. Atau manual di dalam `.venv`: `pip install -r requirements.txt`. (v2.8.1: matplotlib sudah tidak dipakai — hilang dari requirements.) |
| `pip install PySide6` gagal `OSError: [Errno 2] ... qrc_...cpp.obj` (Windows) | Batas path 260 karakter (MAX_PATH). Jalankan `SETUP.bat` v2.6.1+ (otomatis pakai `.venv`). Kalau masih gagal: pindahkan repo ke path pendek, atau aktifkan `LongPathsEnabled` (admin + restart) — lihat bagian Setup. |
| UI error di Linux headless | Set env: `export QT_QPA_PLATFORM=offscreen` sebelum `python ui_app.py` (UI sekarang Qt/PySide6, bukan Tkinter). |
| UI tidak terbuka | Pastikan Python 3.10+ terpasang (`python --version` atau `py -3 --version` — SETUP.bat/MULAI.bat v2.7.0 menerima keduanya). |

## Changelog v2.6.1 — Fix Installer Windows (venv otomatis)

**Pemicu nyata dari pengguna:** instalasi v2.6.0 di Windows gagal — `pip install -r requirements.txt` mati di `PySide6` dengan `OSError: [Errno 2] No such file or directory: ...\PySide6\qml\Qt\labs\assetdownloader\objects-Debug\...\.qt\rcc\qrc_..._init.cpp.obj`; hint pip sendiri menyebut *Windows Long Path support*.

**Akar masalah (bukan bug aplikasi):** Python Microsoft Store menaruh package di path ±137 karakter; wheel PySide6 6.11 memuat file dengan path internal ±143 karakter; total 280 > batas 260 karakter Windows (MAX_PATH) → OS menolak membuat file.

**Fix:**
- **`SETUP.bat`**: cek Python → buat **`.venv`** di folder repo (sekali; dipakai ulang kalau sudah ada) → upgrade pip → install `requirements.txt` **ke `.venv`** → verifikasi import termasuk `PySide6`. Branch error khusus `:pipfail` menjelaskan 2 solusi: pindah repo ke path pendek (mis. `C:\Waste`) atau aktifkan `LongPathsEnabled` (admin + restart).
- **`MULAI.bat`**: otomatis pakai `.venv\Scripts\python.exe` kalau ada (fallback: `python` global); banner disegarkan dari jadul v2.4.1/"10 tab" ke v2.6.x/8-view.
- **`BUILD_EXE.bat`**: PyInstaller di-install & dijalankan dari `.venv`; error jelas kalau SETUP.bat belum dijalankan.
- **README**: bagian Setup menjelaskan kenapa `.venv` (dengan matematika panjang path), tabel troubleshooting + row khusus error long-path + fix baris Linux headless yang masih menyebut Tkinter/TkAgg.
- **Hardening anti-terpotong UI** — audit ulang VLM berukuran kecil (zoom 3× + ground-truth numerik widget) menemukan pelanggaran yang lolos audit 13/13 v2.6.0: header kolom ter-elide TENGAH di jendela sempit ("NAMA RESTO"→"MA REST", "KETERANGAN"→"TERANGA") dan tabel tidak re-fit saat window di-resize (kolom terakhir terpotong di tepi + scrollbar sia-sia):
  - `ui/widgets.py` `DataTable._auto_columns`: **lantai lebar kolom = lebar teks header** (sel bisa wrap, header tidak — lantai header satu-satunya jaminan struktural); pass-2 menekan kolom konten-lebar ke arah lantai SEBELUM menyerah pada scrollbar; dukungan `narrow_hide` (kolom disembunyikan responsif saat sempit, muncul kembali saat melebar — disembunyikan ≠ terpotong); re-fit saat lebar viewport berubah >24px (ambang anti loop umpan balik scrollbar ~14px).
  - `ui/app.py`: sidebar menyusut PROPORSIONAL saat window kecil (stretch 3:12, min 260→230px) — dulu menahan ~300px & memiskinkan view (viewport tabel hanya 662px di window 1024).
  - `ui/view_anomali.py`: tabel anomali 10→7 kolom — MAX, HARI MAX, RANGKING WASTE dihapus (semuanya tampil di panel detail + Jelajah + export; RANGKING mengulang ranking tabel itu sendiri); JENIS masuk daftar `narrow_hide`.
  - Hasil terukur: **0 scrollbar horizontal di 1440×900 (7 kolom penuh) dan 1024×700 (6 kolom inti penuh)** — verifikasi E2E + VLM PASS kedua ukuran; 366 test tetap hijau.
- Core `waste_anomaly/` TIDAK tersentuh — golden regression utuh (25.901 baris / 399 anomali / 41 prioritas).

## Changelog v2.6.0 — "Rebuild Ulang": PySide6 Anomaly Workbench

**Perintah user:** *rebuild ulang UI tapi tetap di Python offline, jangan ada teks yang terpotong atau grafik yang terpotong, orientasi UI untuk temukan anomali; UI/tombol tak perlu atau duplikat hapus.*

### UI baru (total rebuild — 15 file Tkinter dihapus, 16 file PySide6)
- **Framework**: Tkinter → **PySide6 6.x (Qt6)** — layout system yang menegosiasikan ukuran widget (jaminan struktural anti-terpotong); app tetap 100% offline (`pip install PySide6` sekali).
- **Orientasi anomali**: view default = **Anomali** — tabel 797 baris anomali ter-ranking skor tanpa cap, pewarnaan severity per baris, panel detail (12 sinyal, peer, uang, KETERANGAN) + drill 1-klik cabang/item/alasan + ambang **Skor ≥** + KPI terfilter.
- **8 view**: Anomali · Jelajah (gabungan Dashboard+Hasil+Viz+Compare lama) · Waktu · Uang · Peer (gabungan Quadrant+Rate+Compare) · Kualitas Data · Banding Periode · Pipeline (gabungan Run+Ringkasan+Konfigurasi+Bantuan-dialog).
- **State arsitektur**: god-object 109 metode → `AppContext(QObject)` (signal data_ready/filters_changed/status/log_line) + views berbayang — tiap view punya `refresh()`/`on_shown()` (lazy render H2 dipertahankan).
- **Tabel**: `PandasTableModel` + `QTableView` — virtualized 25.901 baris (dulu cap 500), sort numeric-aware klik header, auto-fit kolom proporsional ke viewport, **wrap multi-baris dengan tinggi baris dihitung manual** (bug Qt: `resizeRowsToContents` mengabaikan wrap), ElideNone, tooltip sel & header.
- **Chart anti-terpotong**: `MplCanvas` dengan lantai 85% lebar desain + melebar penuh saat window besar; `ChartCard` = QScrollArea (jendela kecil → scrollbar, bukan potong); **grid responsif** 2↔1 kolom + chart berdesain lebar selalu 1 baris penuh; re-placement ditunda ke tick berikutnya (viewport final).
- **Tombol/tabbars**: export Excel global di toolbar (dulu duplikat konteks), popup log → panel log permanen, "⟳ Refresh Semua" dihapus (render deterministik dari signal), tab label tak pernah terpotong tanpa ellips.
- **Fitur lama SEMUA dipertahankan**: profil filter (filters.json), export 10 sheet, compare periode + waste/hari, threshold editor + atomic save, banding 2 cabang, cancel antar-stage, keyboard Ctrl+F, ikon app, frozen-path sidecar exe.

### Perbaikan core (2 bug chart lama, tanpa menyentuh pipeline)
- `chart_rate_league`: legend "5% threshold (blatant)" terpotong di tepi figure SEJAK APLIKASI LAMA (bahkan pada ukuran desain) → legend dipindah ke bawah chart (ncol=2, label ringkas).
- `chart_weekday_effect`: label tick kelas hari ("(7, 14, 21, 28)…") saling tumpang tindih → dipadatkan tanpa spasi.

### Verifikasi (standar "no mistakes")
- E2E offscreen + data riil 25.901 baris: pipeline 17 s, golden regression **utuh** (25.901 baris / 399 anomali / 41 prioritas), 8 view render tanpa error, drill 797→49 baris, rentang hari, export Excel 8,8 MB sukses.
- **Audit visual AI (VLM) 13 screenshot — 13 PASS** (8 view + 3 state interaksi + 2 ukuran jendela kecil) setelah 6 iterasi perbaikan (kolom tabel auto-fit, wrap manual, grid responsif, lantai canvas, stretch kolom, elide tab). Bukti piksel: sel 2-baris ter-render lengkap; judul chart muat pada lantai 85%.
- 363 test lama tetap hijau (core tak tersentuh) + 12 test struktural baru.

## Changelog v2.5.0 — "Kerjakan Semua (Analisa)": 4 Tab Analisa Baru + Drill-Down Semua Tab

Dipicu audit analisa: 12 sinyal solid sebagai **detektor pola**, tapi ada 6 blind spot terukur — event single-day terbesar (96.480 GR BASIC MIE hari-9) lolos berlabel "Normal", baris Prioritas Tinggi hanya 0,5% dari total waste, peer mati untuk event langka (median termasuk cabang nol), tanpa analisa temporal (padahal pola hari mod-7 +35% ada di data), 119 baris waste tanpa BOM invisibel, dan agregat mencampur satuan. v2.5.0 menambal semuanya dengan **4 modul analisa murni baru + 4 tab UI baru + perluasan drill-down**.

### P1 — Tab "📅 Temporal" (analisa dimensi waktu)
- `waste_anomaly/temporal.py`: `waste_per_day`, `weekday_pattern` (kelas hari % 7), `weekday_effect` (deteksi pasangan kelas peak siklik), `reason_by_day` (matrix alasan×hari), `reason_weekday_ratio` (efek peak per alasan), `unit_summary`.
- Chart: **waste per hari** (hari peak di-highlight merah + catatan "+N%"), **weekday effect** (mean per baris aktif per kelas + garis rata-rata), **heatmap alasan×hari** (top-9 alasan, kapan terjadi). Tabel rasio alasan.
- Angka nyata pada data sampel: kelas peak (5,6) → +35% (369,7 vs 273,6); SUSUT +42%, Cancel Nota +39% di hari peak; TRIAL datar 1,00×; Kualitas Internal justru 0,58×.

### P2 — Tab "💰 Money View" (prioritas magnitude)
- `waste_anomaly/priority.py`: `money_view` (top waste rows APA PUN statusnya + Share %/Kumulatif %), `focus_score` (60% magnitude percentile + 40% anomali, 0-100), `focus_class` (Fokus Utama ≥ 70 / Sekunder ≥ 50 / Rutin), `benchmark_items`, `reason_profile`, `reason_share`, `susut_benchmark`.
- Chart: **top money rows** (diwarnai FOCUS CLASS), **Pareto item** (satuan eksplisit di label). Tabel money (top 100) + benchmark.
- Mengisi gap audit: top row KULIT PANGSIT GGPDAA 299.855 kini tampil teratas (sebelumnya "Normal" dan tak terlihat di view prioritas).

### P4 — Benchmark peer AKTIF (di tab Money View)
- Peer median dihitung **hanya dari cabang yang punya waste** pada item tsb — memperbaiki blind-spot peer lama (median termasuk cabang nol → rasio 0 → S8/S9/S10 mati justru untuk event langka).
- Data sampel: **239 pasangan item×cabang** kini ter-flag "Di Atas Peer" (≥ 2× median peer aktif) — dulu invisibel.

### P6 — Tab "🧹 Data Quality" (pemeriksaan otomatis)
- `waste_anomaly/data_quality.py` — 7 pemeriksaan defensif: nilai negatif (error); SATUAN spasi-tersembunyi/NBSP; SOURCE DATA varian kapital (memecah peer group); KETERANGAN terfragmentasi (prefix); waste tanpa BOM; grup resto×item terpecah antar source (dilute sinyal); baris nol (info struktur).
- Angka data sampel: 2.039 baris satuan 'PACK'NBSP, 12.086 baris source varian 'dan/DAN', 119 baris waste tanpa BOM (190.836 qty), 318 grup terpecah, 97 baris 'Kualitas' terfragmentasi.

### P9 — Tab "🔀 Compare Periode" (bulan ke bulan)
- `waste_anomaly/period_compare.py`: `auto_key_akhir` (deteksi hari aktif terbesar file B), `compare_periods` — summary 7 metrik, per-JENIS, cabang mover, item mover (top-100 |delta|), item baru/hilang.
- Worker thread + progress log + guard anti-run-bersamaan; hasil di 6 halaman tabel.

### P3/P5/P7 — Ekstensi Compare, KPI jujur, satuan
- Tab Compare: **chart profil alasan share %** 2 cabang + **tabel profil alasan semua cabang + benchmark SUSUT** (rank & share per cabang).
- KPI Dashboard: breakdown **per satuan** (GR/PCS/PACK + catatan campuran) + label serupa di Money View; Pareto item menulis satuan di label.

### P8 — Drill-down di SEMUA tab
- **Visualisasi**: 4 chart galeri (Status/Cabang/Top Items/Pareto Alasan) kini bisa **diklik** → set filter + lompat ke Dashboard (handler `on_click` baru di charts.py, kontrak sama dengan dashboard).
- **Hasil**: double-click baris Detail/Anomali → filter cabang+item + lompat.
- **Quadrant**: double-click baris item → filter item (semua cabang).
- **Money View**: double-click baris → filter cabang+item.
- **Dashboard**: dropdown filter **KETERANGAN** baru (sync 2 arah dengan chip/klik chart).

### Export & infrastruktur
- Export Excel kini **10 sheet**: +Waste per Hari, +Alasan×Hari, +Money View, +Data Quality (param `extra_sheets` di exporter — backward-compatible, default tetap 6).
- Bug diperbaiki saat pengembangan: `_wire_patch_click` meng-unpack `patch.contains()` (tuple truthy — patch pertama selalu match); item queue `period_done` 3-tuple (kontrak dispatcher); `load_rekap_mentah` butuh arg config.
- `ui/app.py` kini 15 mixin (14 tab); test struktural diperbarui (MRO dinamis, bukan posisi hard-coded).
- **320 test** (naik dari 150): 51 temporal + 40 priority + 58 data_quality + 21 period_compare + struktur diperbarui. CI: ruff fatal clean. Verifikasi E2E runtime (Xvfb): 14 tab render, drill-down 5 jalur, compare-periode 24 detik, export 10 sheet.

## Changelog v2.4.1 — "Double Check": Fix Path Frozen-Mode PyInstaller

Ditemukan saat verifikasi ulang menyeluruh v2.4.0 (semua klaim diuji runtime, bukan cuma percaya commit message).

### Bug — file user hilang senyap di mode exe (KRITIS)
- **Akar masalah**: `CONFIG_PATH` (utils.py), `PROFILES_PATH` (filters.py), dan `APP_DIR` (ui/shared.py) resolve dari `Path(__file__)`. Di exe PyInstaller, `__file__` menunjuk ke dir ekstraksi temp `_MEIPASS` yang **DIHAPUS saat aplikasi ditutup** — threshold yang disimpan lewat tab Konfigurasi, profil filter, dan folder `data/` lenyap tanpa jejak. Ke balikan dari klaim BUILD_EXE.bat ("config.json disimpan berdampingan dengan exe").
- **Fix**: modul baru `waste_anomaly/frozen.py` — satu sumber resolusi: file **writable** (config sidecar, filters.json, data/, logs) → folder **EXE** (`Path(sys.executable).parent`); resource **read-only** (ikon, config bundled) → `_MEIPASS` (`bundle_dir()`).
- **First-run seed**: saat exe dijalankan pertama kali, config bundled otomatis disalin ke `config.json` di samping exe — sekarang klaim BUILD_EXE.bat benar-benar terimplementasi. Folder read-only → fallback baca bundled (pipeline tetap jalan).
- **Ikon**: dicari di `bundle_res_dir()` (frozen) lalu `app_dir()` (dev) — jalan di kedua mode.
- **Log**: mode exe menulis `logs/` di samping exe (dulu `cwd` — bisa System32 kalau shortcut punya "Start in" berbeda).
- **Tab Konfigurasi** kini menampilkan & menulis ke path dinamis (`_active_config_path()`).

### Cleanup
- **12 pesan log duplikat** "Suppressed: Suppressed …" (sisa penggantian mekanis v2.4.0) → "Suppressed: …".
- Import `simpledialog` tak terpakai di `tab_dashboard.py` dihapus (F401/F811).
- Docstring `logging_setup` — contoh pemakaian `install_tk_exception_hook` dibenarkan.

### Test
- **+10 test** (`test_frozen_paths.py`): dev-path tak berubah (golden aman), seed first-run, sidecar existing menang (edit user bertahan), fallback read-only, roundtrip save/load profil frozen, `app_dir()`/`bundle_res_dir()`. Total **150 test** semua LULUS.

### Verifikasi runtime (bukan cuma test)
- Golden run data asli: 25.901 baris / 399 anomali / 41 prioritas — **MATCH** (key_akhir=31).
- Cancel mid-run: pipeline berhenti persis di gate Stage 2 (`cancelled=True`, log terpotong di gate) — **PASS**.
- Skema lowercase: gagal keras + saran rename — **PASS**.
- Exporter 60k baris: peak memori **7 MB** (dulu OOM ~1,8 GB) — **PASS**.

## Changelog v2.4.0 — "Kerjakan Semua": Arsitektur Modular + Infrastruktur Profesional Penuh

### Arsitektur — god-object dipecah (audit UI #1)
- **`ui_app.py` 3.256 baris / 102 metode → paket `ui/` 14 file**: 11 mixin (base + 10 tab) + shared + widgets + komposisi. Metode dipindah **VERBATIM via ekstraksi AST** (bukan tulis ulang) — terverifikasi: set 102 metode identik, 101/101 source identik byte-per-byte, 8 dekorator `@staticmethod`/`@classmethod` dipertahankan, MRO = 11 mixin + `tk.Tk`. Menambah tab ke-11 kini menyentuh **1 file baru + 1 baris komposisi** (dulu 5+ situs tersebar).
- **Registry font** menggantikan pola `global` lama (yang hanya bekerja saat semua kode di satu file): `shared.rebind_fonts()` mem-propagasi nilai font ke semua modul mixin saat startup.
- **`ui_app.py` tetap jadi entry point** — MULAI.bat & kebiasaan user tidak berubah.
- **11 test struktural permanen** (`test_ui_structure.py`): manifest 102 metode, MRO, anti-duplikat antarmixin, dekorator, registry font, APP_DIR repo-root.

### Cancel run yang jujur (audit UI #2)
- **Hook `cancel_check` antar-stage di pipeline** — tombol "⏹ Batalkan Run" kini benar-benar menghentikan CPU di gate stage berikutnya (dulu: flag hanya dicek SETELAH pipeline selesai — hasil dihitung sampai tuntas lalu dibuang). Teruji: cancel setelah Stage 1 → log berhenti di Stage 2, Stage 11+ tidak pernah dijalankan.

### Validasi skema input (audit data #5 — degradasi senyap)
- **`waste_anomaly/schema.py`**: header lowercase/missing kini **gagal keras dengan pesan actionable** (dulu: `success=True` dengan analisa setengah mati — semua baris "Normal" padahal ada spike). Deteksi: kolom wajib hilang + saran near-miss case-insensitive, header duplikat, kolom hari kosong, nilai JENIS asing (warning).

### Exporter streaming (audit data #2 — OOM 100k baris)
- **Dual-mode otomatis**: ≤35.000 baris → mode normal (formatting penuh); di atasnya → **openpyxl `write_only`** (memori konstan; terverifikasi 60k baris sukses — dulu OOM-kill ~1,8 GB). Threshold bisa di-override via `config["output"]["streaming_threshold"]`. Handler `MemoryError` dengan pesan ramah.

### Logging framework (audit UI #4)
- **Rotating file log** `logs/waste_anomaly.log` (1 MB × 3 backup) + `report_callback_exception` hook Tk — exception di callback kini tercatat, tidak hilang di stderr.
- **16 exception senyap (`except: pass`) diganti `_LOGGER.debug(...)`** — jejak audit penuh tanpa spam UI.

### Test & CI
- **140 test** (dari 44): +54 unit test S1–S12 (trigger/non-trigger/boundary persis di threshold/NaN/config-override), +13 skema & cancel, +13 exporter (paritas data antar-mode + streaming 60k), +5 logging, +11 struktural UI.
- **CI GitHub Actions**: matrix Python 3.10/3.12 × Ubuntu/Windows — lint fatal (ruff E9,F63,F7,F82) + seluruh test + smoke import.

### Packaging
- **`BUILD_EXE.bat` + `waste_anomaly.spec`** (PyInstaller): .exe standalone tanpa Python di PC target, `console=False`, ikon multi-resolusi.
- **Ikon aplikasi** (teal/coral, AI-generated) dipasang via `iconphoto` + `.ico` untuk exe.
- Versi single-source 2.4.0 di semua situs (`__init__`, `APP_VERSION`, config.json, MULAI.bat, README).

## Changelog v2.3.2 — Audit Profesional Lanjutan

### Critical / High
- **Idempotency sejati (F7)**: file Excel bisa mengandung *FP dust* (mis. `21.299999999999997` yang visually = `21.3`). Sebelumnya: run-1 vs run-ulang memberi **skor anomali berbeda** untuk data yang sama (402 → 403 — 5 baris di boundary threshold S3/S5 flip; terverifikasi test). Kini semua nilai float dinormalisasi ke **15 digit signifikan** (semantik penyimpanan Excel) saat load — konsisten dengan apa yang user & Power Query lihat. Golden: 399 anomali (41 prioritas, 358 potensi) — 4 dust-false-positive kini Normal, 1 dust-false-negative konsisten terdeteksi.
- **Join BOM numerik (F1)**: `stages.py` memakai normalisasi `_key_str` (loader) — outlet numerik `1049.0` kini **match** dengan `"1049"` di sheet BOM. Sebelumnya: join gagal diam-diam → TOTAL BOM semua NaN → sinyal S6/S7 tidak pernah trigger.
- **Test suite (44 test)**: `tests/` — golden regression end-to-end pada fixture `DATA_WASTE.xlsx` (25.901 baris), unit test normalisasi kunci, unit test join BOM, unit test presisi float, kontrak summary dict, validasi domain status, dan **test idempotency** (re-run pada output sendiri). Run: `python -m pytest tests/ -v` (~60 s).
- **requirements.txt (F5)**: dependensi di-pin dengan alasan (matplotlib ≥ 3.9 untuk `tick_labels`, pandas 2.2.x teruji, calamine opsional). SETUP.bat kini install dari file ini.

### Medium
- **LICENSE (MIT)** ditambahkan (README sudah mengklaim sejak awal).
- **QUADRANT_THRESHOLD (F4)** kini benar-benar dibaca dari config user oleh chart quadrant — sebelumnya hardcode 0.5, chart & tabel bisa tidak sinkron.
- **Reset Default config (F3)** kini mencakup 20/20 key (sebelumnya 6 key baru tidak pernah di-reset).
- **Save config atomic (F2)**: tmp + `os.replace` (pola `filters.py`) + validasi nilai > 0.
- **Single-source version (L2)**: `__init__.py`, `APP_VERSION`, MULAI.bat, README — semua 2.3.2.
- **MULAI.bat** banner diperbarui (10 tab, bukan 8).

## Changelog v2.3.1 — Deep Audit & Fix

### Critical (crash / korupsi data)
- **UI freeze permanen**: exception apa pun di queue-drain loop mematikan polling → progress macet + tombol Run stuck disabled. Loop kini reschedule-first + tiap item di-guard.
- **Crash log popup**: tombol X menghancurkan window tapi referensi tetap hidup → `TclError` berantai. Kini X = hide; popup auto-recreate; `append()` di-guard.
- **Scroll mouse rusak total**: 5 binding `bind_all` saling menimpa → wheel menggerakkan canvas yang tersembunyi; tab Konfigurasi tak bisa di-wheel; tabel double-scroll. Kini satu dispatcher global (Windows ±120 / macOS ±small / Linux Button-4/5).
- **Crash empty-data**: 0 baris valid setelah Stage 2 → `ValueError: Length mismatch`. Kini guard ramah + pesan jelas.
- **Kolom hilang diam-diam**: merge DATABASE_SATUAN menimpa kolom bentrok (`SATUAN`, `NAMA BARANG` jadi `_x/_y`). Kini merge hanya kolom yang dibutuhkan + detektor bentrok.
- **Bar chart menumpuk**: label ter-truncate duplikat → matplotlib menumpuk bar di posisi sama (data tersembunyi). Kini plot posisional + disambiguasi label.

### High (UX & performa)
- **Memory leak**: figure matplotlib tidak pernah di-dispose pada tiap re-render → RAM membengkak. Kini teardown penuh (disconnect cids → destroy widget → `fig.clf()`).
- **Render storm**: ~18 figure digambar sinkron setelah pipeline selesai → UI membeku. Kini lazy per-tab (render saat tab dibuka) + refresh hanya tab aktif.
- **Search lag**: tiap keystroke re-render 3 chart + 500 baris + `apply` row-wise. Kini debounce 300 ms + mask vectorized per-kolom.
- **Kalkulasi M-fidelity**: `KONTRIBUSI TERBESAR` kini agregasi per-KETERANGAN (23% baris dulu salah); `KETERANGAN GABUNGAN` urutan per kontribusi; nama kolom kanonik (spasi, bukan underscore).
- **Idempotency HELPER/STATUS**: re-run di output sendiri dulu menghancurkan 21.355 nilai HELPER/STATUS. Kini dipertahankan seperti TOTAL BOM.
- **Dead Output-Excel UI** dihapus → diganti tombol **💾 Export Laporan Excel** (background thread, `PermissionError` friendly, 3.5× lebih cepat).
- **Quadrant chart** kini pakai Key Akhir aktual (bukan hardcode /31) — titik tidak lagi mendarat di quadrant yang salah.
- **Profil filter**: save kini konfirmasi overwrite; restore tidak lagi double-render; file `filters.json` atomic-save + auto-backup saat korup.
- **Warna JENIS stabil** antar-run & antar-tab (dulu hash-based — bisa bentrok).
- **Spinbox TclError**: input non-numerik tidak lagi crash handler.

### Medium/Low
- Window centering + clamp untuk layar 1366×768; font fallback cross-platform; sort kolom numeric-aware + indikator ▲/▼; label "Menampilkan N dari M baris"; chip label Indonesia; konfirmasi keluar saat pipeline jalan; tombol **⏹ Batalkan Run**; shortcut Ctrl+R/Ctrl+F; status `Timestamp`/`Key Akhir`/warning-config di Ringkasan; progress bar monotonic 0→100; make_sample rng fix; bersih-bersih dead code & duplikasi (helper `_format_cell`, `_apply_filters`, `_export_figures_png`).

## Reference

- M code sumber: Power Query `Waste` query (private repo)
- Pattern UI: https://github.com/anandategarch/Inventory-Adjusment

## License

MIT — bebas pakai, modify, distribute.
