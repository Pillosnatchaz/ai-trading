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

## 🟢 FASE 1: Infrastruktur Dasar (Fokus Minggu 1)

Ini adalah fondasi. Jika Anda tidak memiliki aliran data yang bersih dan cepat, AI sebaik apapun akan gagal.

- Setup Environment: Buat venv baru dan install dependensi dasar (pip install pyzmq pandas numpy lightgbm requests).

- Bangun MT4 ZMQ Bridge: - Tulis skrip mt4_zmq_bridge.py di Python.

- Pasang Expert Advisor (EA) ZeroMQ di MT4 Anda.
- Tujuan Fase 1 Selesai: Terminal Python Anda bisa mencetak harga (Bid/Ask) secara real-time tanpa lag saat grafik MT4 bergerak.

## 🟡 FASE 2: Rekayasa Fitur Matematika (Fokus Minggu 2)

Ubah panduan teman Anda menjadi kode.

- Matematika Murni: Di indicator_math.py, tulis fungsi untuk menghitung garis SMA, EMA, MACD, dan zona Fibonacci (OTE). Anda bisa menggunakan library seperti ta (Technical Analysis) atau pandas-ta untuk mempermudah ini.
- Feature Builder: Tulis skrip yang mengubah harga live tadi menjadi matriks angka. Misalnya, hitung selisih harga saat ini dengan EMA 50.

## 🟠 FASE 3: Pembersihan & Pelabelan Data Historis

Siapkan data untuk melatih ML.

- Triple Barrier Labeling: Tulis skrip triple_barrier.py.
- Label Ulang Database Lama: Ambil data M1 historis, lalu jalankan skrip Triple Barrier ke 2.118 snapshot lama Anda. Labeli dengan benar (+1 jika kena TP, -1 jika kena SL).

## 🔴 FASE 4: Melatih Mesin Probabilitas (LightGBM)

- Training: Gunakan data yang sudah dilabeli ulang untuk melatih model LightGBM Anda.
- Inference: Di ml_lightgbm.py, buat class Predictor yang menerima data dari Fase 2 dan mengeluarkan skor probabilitas instan (misal: 0.85).

## 🟣 FASE 5: Agen Makro LLM (Asinkron)

- Buat LLM bekerja di latar belakang agar tidak mengganggu kecepatan trading.
- Skrip Agen: Tulis llm_macro_agent.py untuk menarik berita dari RSS (ForexFactory) dan meminta DeepSeek-R1 menyimpulkan bias pasar.
- Cron Job / Thread: Atur agar skrip ini otomatis berjalan setiap 15 menit dan menyimpan hasilnya di file teks sederhana (contoh: macro_state.json).

## 🔵 FASE 6: Penyatuan Sang Gatekeeper (Final)

Satukan semuanya di main_loop.py.

- Looping: Skrip berjalan menanti tick harga dari ZMQ (Fase 1).
- Cek ML: Saat harga masuk, hitung fitur (Fase 2) dan minta probabilitas dari LightGBM (Fase 4).
- Validasi: Jika probabilitas > 75%, baca macro_state.json (Fase 5). Apakah arah ML selaras dengan arah Makro LLM?
- Hitung Risiko: Jika selaras, panggil risk_calculator.py untuk menghitung SL dan TP berdasarkan Average True Range (ATR).
- Tembak: Kirim perintah eksekusi ke MT4 via ZMQ.