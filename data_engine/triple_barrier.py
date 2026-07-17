import pandas as pd
import numpy as np

class TripleBarrierLabeler:
    def __init__(self, sl_pips=40, tp_pips=60, max_bars=60):
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

    def get_label(self, current_price, future_prices, direction="buy", future_highs=None, future_lows=None):
        """
        Mengevaluasi jalur harga masa depan untuk menentukan hasil (Label).
        
        ponytail: Uses High/Low when available for pessimistic SL/TP checking.
        If both SL and TP are breached in the same candle, assumes SL hit first (worst case).
        
        Returns:
             1 : Sentuh Take Profit terlebih dahulu (Trade Sukses)
            -1 : Sentuh Stop Loss terlebih dahulu (Trade Gagal)
            -2 : Fast SOTW (Hit SL first, then TP within 15 bars)
            -3 : Slow SOTW (Hit SL first, then TP after 15 bars)
             0 : Sentuh Time Barrier (Sideways / Kadaluarsa)
        """
        if direction == "buy":
            sl_price = current_price - self.sl_dist
            tp_price = current_price + self.tp_dist
        else: # sell
            sl_price = current_price + self.sl_dist
            tp_price = current_price - self.tp_dist

        # ponytail: use OHLC when available, fallback to close-only
        use_ohlc = future_highs is not None and future_lows is not None

        for i in range(min(len(future_prices), self.max_bars)):
            price = future_prices[i]
            # ponytail: check intra-candle extremes if available
            high = future_highs[i] if use_ohlc else price
            low = future_lows[i] if use_ohlc else price

            if direction == 'buy':
                hit_sl = low <= sl_price
                hit_tp = high >= tp_price

                if hit_sl and hit_tp:
                    # ponytail: pessimistic — assume SL hit first when both breached in same candle
                    hit_sl = True
                    hit_tp = False

                if hit_sl:
                    # Check SOTW
                    for p_idx in range(i + 1, min(len(future_prices), self.max_bars)):
                        check_high = future_highs[p_idx] if use_ohlc else future_prices[p_idx]
                        if check_high >= tp_price:
                            if (p_idx - i) <= 15:
                                return -2 # Fast SOTW (Noise)
                            else:
                                return -3 # Slow SOTW (Drift)
                    return -1
                if hit_tp:
                    return 1

            elif direction == 'sell':
                hit_sl = high >= sl_price
                hit_tp = low <= tp_price

                if hit_sl and hit_tp:
                    # ponytail: pessimistic — assume SL hit first
                    hit_sl = True
                    hit_tp = False

                if hit_sl:
                    # Check SOTW
                    for p_idx in range(i + 1, min(len(future_prices), self.max_bars)):
                        check_low = future_lows[p_idx] if use_ohlc else future_prices[p_idx]
                        if check_low <= tp_price:
                            if (p_idx - i) <= 15:
                                return -2 # Fast SOTW (Noise)
                            else:
                                return -3 # Slow SOTW (Drift)
                    return -1
                if hit_tp:
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
