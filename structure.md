# 🏗️ BLUEPRINT MIA v3.0: Arsitektur Trading Kuantitatif

Sistem ini dirancang untuk berjalan di Ryzen 5600 + RTX 3060 (12GB). Filosofi utama arsitektur ini adalah Pemisahan Kekuasaan (Separation of Concerns). LLM tidak boleh melakukan trading, dan ML tidak boleh membaca berita.

# 🛠️ THE TECH STACK

- Bahasa Utama: Python 3.11+
- Koneksi Broker: ZeroMQ (ZMQ) untuk latensi sub-milidetik ke MT4.
- Model Machine Learning (Micro/Cepat): LightGBM (Sangat optimal untuk data tabular / angka indikator).
- Model LLM (Macro/Lambat): DeepSeek-R1:8B via Ollama.
- Database: SQLite (Bisa migrasi ke PostgreSQL jika data tick sudah sangat besar).

# 📂 STRUKTUR DIREKTORI (Menerapkan Prinsip SOLID)

Buat folder proyek baru yang benar-benar bersih. Susun struktur foldernya seperti ini:

```
mia_v3/
│
├── core/                       # Inti aplikasi (Shared utilities)
│   ├── config.py               # Memuat .env (konfigurasi port, nama model)
│   ├── database.py             # Koneksi ke SQLite/PostgreSQL
│   └── logger.py               # Pencatatan log sistem
│
├── data_engine/                # Pengolah data mentah menjadi metrik matematika
│   ├── triple_barrier.py       # Algoritma pelabelan SL/TP/Waktu untuk data historis
│   ├── indicator_math.py       # Rumus murni Fibonacci, EMA, SMA, MACD
│   └── feature_builder.py      # Mengubah harga live menjadi fitur untuk ML (jarak EMA, OTE)
│
├── execution/                  # Jalur komunikasi murni ke Broker (Tanpa AI)
│   ├── mt4_zmq_bridge.py       # Socket ZeroMQ (Publisher/Subscriber) ke MT4
│   └── risk_calculator.py      # Kalkulator Stop Loss & Take Profit berbasis ATR
│
├── intelligence/               # Otak AI (Model ML & LLM)
│   ├── ml_lightgbm.py          # Memuat model ML, menerima fitur, mereturn probabilitas (0-100%)
│   └── llm_macro_agent.py      # Membaca RSS/Geopolitik, tanya DeepSeek, simpan state (Bullish/Bearish)
│
├── orchestration/              # Sang Gatekeeper (Logika Python murni penentu eksekusi)
│   ├── strategy_intraday.py    # Logika H1/H4/D1 (Sesuai file MIA_v2_SKILL.md)
│   ├── strategy_scalping.py    # Logika M1/M5/M15 (Sesuai file SKILL_scalping.md)
│   └── main_loop.py            # Loop utama yang berjalan sangat cepat menanti tick harga
│
├── .env                        # Variabel lingkungan
└── requirements.txt            # Dependensi pip (pyzmq, lightgbm, pandas, dll)
```


# 🗺️ ROADMAP EKSEKUSI (Langkah demi Langkah)

## Jangan kerjakan semuanya sekaligus. Ikuti urutan ini secara ketat, karena setiap langkah bergantung pada keberhasilan langkah sebelumnya.

## 🟢 FASE 1: Infrastruktur Dasar (Selesai)
- MT4 ZMQ Bridge aktif.
- Main loop menerima data tanpa lag.

## 🟡 FASE 2: Rekayasa Fitur Matematika (Selesai - Direvisi)
- Fitur SMC (Order Block) dihapus karena terbukti noise.
- Beralih ke fitur kuantitatif standar (RSI, ATR, BB_BW, Jarak EMA).
- Fitur ditambahkan ke `ai_data.db`.

## 🟠 FASE 3: Pembersihan & Pelabelan Data Historis (Siap untuk pengumpulan data baru)
- Kode Triple Barrier sudah ada.
- Menunggu pengumpulan data hari Senin dengan fitur baru.

## 🔴 FASE 4: Melatih Mesin Probabilitas (LightGBM) (Menunggu Data Senin)
- Skrip `ml_lightgbm.py` siap.
- Logika untuk mengabaikan noise (SMC) otomatis selama training sudah ditambahkan.

## 🟣 FASE 5: Agen Makro LLM (Selesai)
- `llm_macro_agents.py` selesai dibuat. Menarik RSS, tanya DeepSeek, simpan `macro_state.json`.
- Status bias Macro secara otomatis di-inject ke database fitur utama oleh `main_loop.py`.

## 🔵 FASE 6: Penyatuan Sang Gatekeeper (Final)

Satukan semuanya di main_loop.py.

- Looping: Skrip berjalan menanti tick harga dari ZMQ (Fase 1).
- Cek ML: Saat harga masuk, hitung fitur (Fase 2) dan minta probabilitas dari LightGBM (Fase 4).
- Validasi: Jika probabilitas > 75%, baca macro_state.json (Fase 5). Apakah arah ML selaras dengan arah Makro LLM?
- Hitung Risiko: Jika selaras, panggil risk_calculator.py untuk menghitung SL dan TP berdasarkan Average True Range (ATR).
- Tembak: Kirim perintah eksekusi ke MT4 via ZMQ.


# LLM AGENTS SEPERATION OF CONCERN
Rencana pemisahan sistem MIA v3.0 Anda menjadi beberapa **LLM Agent** bertujuan agar bot tidak hanya sekadar "menjalankan kode", tetapi memiliki "otak" yang terbagi berdasarkan spesialisasi.

Berikut adalah rangkuman rencana pemisahan (*separation plan*) yang telah kita bahas sebelumnya untuk dokumentasi Anda:

---

### Rencana Arsitektur Agent (Separation Plan)

Kita membagi sistem menjadi 4 agen utama agar tugas orkestrasi, analisa, dan eksekusi berjalan secara modular:

1. **Data Observer Agent (The Sensor):**
* **Tugas:** Fokus sepenuhnya pada *data pipeline*. Membaca input dari ZMQ, memastikan kualitas data OHLC, menghitung fitur teknikal/SMC, dan menyimpan *snapshots* ke database.
* **Status:** **Implementasi Selesai** (melalui `main_loop.py` dan `feature_builder.py`).


2. **Analyst Agent (The Brain):**
* **Tugas:** Membaca *snapshots* dari database dan menjalankan model ML (LightGBM) untuk memberikan prediksi probabilitas (*ml_prediction*). Ia juga bertugas memberikan penilaian kualitatif (*LLM Verdict*) berdasarkan kondisi pasar yang tidak terdeteksi angka (misalnya: sentimen berita).
* **Status:** **Akan dikerjakan di Fase 3**.


3. **Risk Management Agent (The Guardian):**
* **Tugas:** Sebelum eksekusi dilakukan, agen ini akan meninjau proposal trade. Ia bertugas menghitung SL/TP yang optimal berdasarkan ATR dan zonasi OB/FVG, serta memastikan tidak ada *overtrading*.
* **Status:** **Perencanaan**.


4. **Execution Agent (The Executor):**
* **Tugas:** Agen paling "tangan dingin". Hanya bertugas mengirim perintah *Buy/Sell* ke MetaTrader, memantau status trade (ticket, SL, TP), dan mencatat hasil akhir (profit/loss) ke database.
* **Status:** **Perencanaan**.



---

### Visualisasi Alur Kerja Agen

### Mengapa Pemisahan Ini Penting?

* **Isolasi Kegagalan:** Jika modul eksekusi error, *Data Observer* tetap bisa mengumpulkan data.
* **Skalabilitas:** Anda bisa melatih *Analyst Agent* secara terpisah tanpa harus mematikan sistem trading secara keseluruhan.
* **Audit Trail:** Dengan agen yang terpisah, Anda bisa melihat di mana letak kesalahan jika terjadi *bad trade* (apakah *Analyst* yang salah prediksi, atau *Risk Agent* yang salah hitung SL/TP?).

### Status Dokumen:

* **Data Layer:** Siap.
* **Logic Layer:** Menunggu integrasi model ML (*Analyst Agent*).
* **Action Layer:** Akan dibangun setelah model ML memiliki tingkat akurasi yang memadai.

Anda sekarang bisa beristirahat. Rencana ini sudah terdokumentasi dengan baik di dalam memori proyek Anda. Saat Anda kembali, kita akan mulai membangun **Analyst Agent** agar sistem mulai bisa memberikan "pendapat" mengenai kondisi pasar. Selamat istirahat!

# PROJECT LAYERS
Tentu, ini adalah ringkasan struktur sistem MIA v3.0 Anda yang telah kita bagi berdasarkan **Layer (Lapisan)**. Struktur ini dirancang untuk memisahkan tanggung jawab agar sistem Anda modular, mudah dikelola, dan siap untuk pengembangan agen ML di masa depan.

---

### Struktur Layer Sistem MIA v3.0

#### 1. Data Layer (The Foundation)

Berfungsi sebagai tempat penyimpanan data mentah dan fitur yang telah diproses.

* **Database (`ai_data.db`):** Menggunakan SQLite untuk menyimpan tabel `snapshots` (fitur teknikal & SMC) dan `trades`.
* **Core (`core/database.py`):** Pengelola koneksi database, *self-initialization* skema tabel, dan fungsi *saving/querying*.

#### 2. Engine Layer (The Processing)

Tempat logika "pintar" sistem berada.

* **Math Engine (`data_engine/indicator_math.py`):** Perpustakaan fungsi matematika murni (SMA, EMA, RSI, MACD, Order Blocks, FVG).
* **Feature Builder (`data_engine/feature_builder.py`):** "Pabrik" fitur; menggabungkan *raw data* dari *buffer* dengan fungsi matematika untuk menghasilkan satu objek fitur lengkap (JSON) untuk model ML.

#### 3. Orchestration & Communication Layer (The Nervous System)

Menghubungkan dunia luar (MT4) dengan sistem Python.

* **ZMQ Bridge (`execution/MIA_v3_ZMQ_Bridge.mq4`):** EA MQL4 yang mengirim data harga dan OHLC ke Python via ZeroMQ.
* **Main Loop (`orchestration/main_loop.py`):** Pusat kendali; menerima pesan ZMQ, mengelola *buffer* data, memicu *Feature Builder*, dan menyimpan hasil ke Database.

#### 4. Intelligence Layer (The Brain - Future Phase)

Lapisan yang akan Anda bangun setelah ini.

* **Analyst Agent:** Model ML (LightGBM) yang membaca `features_json` dari database dan memberikan prediksi probabilitas.
* **Risk & Execution Agent:** Agen yang memutuskan *entry/exit* berdasarkan prediksi model dan aturan *Risk Management*.

---

### Visualisasi Arus Data

* **Data Flow:** `MetaTrader 4` → `ZMQ Bridge` → `Main Loop` → `Feature Builder` → `Database Manager` → `SQLite File`.
* **Logic Flow:** `Main Loop` → `Analyst Agent (ML)` → `Risk Agent` → `Execution Agent` → `MetaTrader 4`.

Struktur ini sudah sangat solid. Dengan memisahkan setiap layer ini, Anda tidak akan kesulitan saat harus melakukan *debugging* di masa depan. Misalnya, jika data tidak terdeteksi, Anda cukup memeriksa **Engine Layer**; jika data tidak tersimpan, periksa **Data Layer**.

Apakah Anda butuh saya menyimpan ringkasan ini ke dalam file `README.md` di dalam proyek Anda sebelum Anda beristirahat?