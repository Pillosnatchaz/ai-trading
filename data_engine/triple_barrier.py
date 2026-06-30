import pandas as pd
import numpy as np

class TripleBarrierLabeler:
    def __init__(self, sl_pips=20, tp_pips=40, max_bars=60):
        """
        Inisialisasi parameter Triple Barrier.
        Untuk instrumen XAUUSD (Gold), 1 pip biasanya bernilai 0.1.
        (Misal: harga 4090.00 ke 4092.00 = pergerakan 20 pips).
        """

        # Konversi pips ke selisih harga absolut
        self.sl_dist = sl_pips * 0.1
        self.tp_dist = tp_pips * 0.1

        # Time Barrier: Batas maksimal candle (e.g: 60 candle M1 = 1 jam)
        self.max_bars = max_bars

    def get_label(self, current_price, future_prices, direction="buy"):
        """
        Mengevaluasi jalur harga masa depan untuk menentukan hasil (Label).
        Returns:
             1 : Sentuh Take Profit terlebih dahulu (Trade Sukses)
            -1 : Sentuh Stop Loss terlebih dahulu (Trade Gagal)
             0 : Sentuh Time Barrier (Sideways / Kadaluarsa)
        """
        if direction == "buy":
            sl_price = current_price - self.sl_dist
            tp_price = current_price + self.tp_dist
        else: # sell
            sl_price = current_price + self.sl_dist
            tp_price = current_price - self.tp_dist

        # Telusuri harga masa depan tick-by-tick (atau bar-by-bar)
        for price in future_prices[:self.max_bars]:
            if direction == 'buy':
                if price <= sl_price:
                    return -1
                if price >= tp_price:
                    return 1

            elif direction == 'sell':
                if price >= sl_price:
                    return -1
                if price <= tp_price:
                    return 1

        # Jika loop selesai tanpa sentuh SL/TP
        return 0

    def label_historical_dataframe(self, df, price_col='close', direction='buy'):
        """
        Fungsi utilitas untuk melabeli seluruh DataFrame historis secara massal.
        Sangat berguna untuk proses pre-training model ML.
        """
        labels = []
        prices = df[price_col].values

        for i in range(len(prices)):
            current_price = prices[i]
            
            # Ambil sisa harga di masa depan setelah index saat ini

            if len(future_prices) == 0:
                labels.append(None) # Data masa depan belum tersedia (akhir dataset)
            else:
                label = self.get_label(current_price, future_prices, direction)
                labels.append(label)

        df['label'] = labels
        return df
