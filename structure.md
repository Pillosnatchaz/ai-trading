# 🏗️ BLUEPRINT MIA v3.0: Arsitektur Trading Kuantitatif

Sistem ini dirancang untuk berjalan di Ryzen 5600 + RTX 3060 (12GB). Filosofi utama arsitektur ini adalah Pemisahan Kekuasaan (Separation of Concerns). LLM tidak boleh melakukan trading, dan ML tidak boleh membaca berita.

# 🛠️ THE TECH STACK

- Bahasa Utama: Python 3.11+
- Koneksi Broker: ZeroMQ (ZMQ) untuk latensi sub-milidetik ke MT4.
- Model Machine Learning (Micro/Cepat): LightGBM (Sangat optimal untuk data tabular / angka indikator).
- Model LLM (Macro/Lambat): DeepSeek-R1:8B via Ollama.
- Database: SQLite (Bisa migrasi ke PostgreSQL jika data tick sudah sangat besar).

# 📂 STRUKTUR DIREKTORI (Menerapkan Prinsip SOLID)

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

# 🗺️ ROADMAP EKSEKUSI (Status Saat Ini)

## 🟢 FASE 1-4: Infrastruktur & AI Core (Selesai)
- **ZMQ Bridge:** Komunikasi sub-milidetik dengan MT4 berjalan stabil tanpa lag.
- **Math Engine:** Fitur kuantitatif standar (RSI, ATR, BB_BW, Jarak EMA) diekstrak real-time. Swing features (H4, D1) dimatikan untuk scalping.
- **Triple Barrier Labeler:** Pelabelan otomatis untuk TP/SL/Timeout (Label 1 = Win, 0 = Loss/Timeout) berjalan sukses.
- **LightGBM ML:** Model berhasil dilatih, dievaluasi, dan memberikan probabilitas live pada `main_loop.py`.

## 🟡 FASE 5: Live Execution & Data Collection Phase (STATUS KITA SAAT INI)
- **Hardcoded Risk:** Sistem dieksekusi dengan SL 30 / TP 45 yang hardcoded di `main_loop.py` untuk fase pengumpulan data M1.
- **Pengumpulan Data:** Bot saat ini dibiarkan berjalan untuk mengumpulkan data M1 yang bersih dari bug (bug zona waktu UTC dan error-handling telah diperbaiki).
- **Target:** Mencapai profitabilitas pada akun demo dengan arsitektur ini sebelum menambah kompleksitas.

## 🟠 FASE 6: Future Enhancements (Dynamic Risk & Macro Gatekeeper)
Jika bot sudah konsisten mencetak profit dengan sistem *hardcoded* saat ini, kita akan mengaktifkan:
- **Dynamic SL/TP:** Menghidupkan kembali kalkulasi `ote` (Optimal Trade Entry) dan ATR untuk menyesuaikan ukuran Stop Loss secara dinamis.
- **LLM News Filter:** Memodifikasi `llm_macro_agent.py` agar mendeteksi berita berdampak tinggi (NFP, FOMC) dan memberikan sinyal "Circuit Breaker" untuk menghentikan `main_loop.py` selama 30 menit.

# 🤖 LLM AGENTS SEPERATION OF CONCERN

Sistem MIA v3.0 dibagi menjadi 4 agen utama agar tugas orkestrasi, analisa, dan eksekusi berjalan secara modular:

1. **Data Observer Agent (The Sensor)**
   - **Tugas:** Membaca input dari ZMQ, memastikan kualitas data OHLC, menghitung fitur teknikal, dan menyimpan *snapshots* ke database.
   - **Status:** 🟢 **Selesai** (`main_loop.py` & `feature_builder.py`).

2. **Analyst Agent (The Brain)**
   - **Tugas:** Menjalankan model ML (LightGBM) untuk memberikan prediksi probabilitas 0-100%. 
   - **Status:** 🟢 **Selesai** (`ml_lightgbm.py`).

3. **Execution Agent (The Executor)**
   - **Tugas:** Mengirim perintah *Buy/Sell* ke MetaTrader dengan sangat cepat via ZMQ.
   - **Status:** 🟢 **Selesai** (`main_loop.py` ZMQ Publisher).

4. **Risk Management Agent (The Guardian)**
   - **Tugas:** Merubah SL/TP statis menjadi dinamis berdasarkan ATR, serta memutus aliran eksekusi jika ada sentimen berita ekstrem (Macro LLM).
   - **Status:** 🟠 **Ditunda** (Saat ini menggunakan 30/45 hardcoded logic untuk kecepatan dan kesederhanaan pengumpulan data).