import pandas as pd
import numpy as np

class IndicatorMath:

    @staticmethod
    def detect_fvg(df):
        """
        Deteksi FVG berdasarkan aturan TBC:
        - Bullish FVG: Low candle ke-3 > High candle ke-1 (Ada gap di antara keduanya)
        - Bearish FVG: High candle ke-3 < Low candle ke-1 (Ada gap di antara keduanya)
        """
        # Pastikan data memiliki kolom yang cukup
        if len(df) < 3:
            return []

        fvgs = []
        # Kita mulai dari indeks ke-2 karena butuh 3 candle (i-2, i-1, i)
        for i in range(2, len(df)):
            # Bullish FVG: Celah harga antara High candle pertama dan Low candle ketiga
            if df['low'].iloc[i] > df['high'].iloc[i-2]:
                fvgs.append({
                    'type': 'bullish', 
                    'price': df['low'].iloc[i],
                    'index': df.index[i]
                })
            # Bearish FVG: Celah harga antara Low candle pertama dan High candle ketiga
            elif df['high'].iloc[i] < df['low'].iloc[i-2]:
                fvgs.append({
                    'type': 'bearish', 
                    'price': df['high'].iloc[i],
                    'index': df.index[i]
                })
        
        return fvgs[-5:] # Mengembalikan 5 FVG terbaru


    @staticmethod
    def get_sma(series, period):

        return series.rolling(window=period).mean()

    @staticmethod
    def get_ema(series, period):
        
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def get_rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss

        return 100 - (100 / (1 + rs))

    @staticmethod
    def get_stochastic(high, low, close, period=14, smooth_k=3, smooth_d=3):
        lowest_low = low.rolling(window=period).min()
        highest_high = high.rolling(window=period).max()
        k = 100 * ((close - lowest_low) / (highest_high - lowest_low))

        return k.rolling(window=smooth_k).mean(), k.rolling(window=smooth_d).mean()

    @staticmethod
    def get_bollinger_bands(series, period=20, std=2):
        ma = series.rolling(window=period).mean()
        md = series.rolling(window=period).std()
        upper = ma + (md * std)
        lower = ma - (md * std)
        bandwidth = (upper - lower) / ma
        percent_b = (series - lower) / (upper - lower)

        return upper, lower, bandwidth, percent_b

    @staticmethod
    def get_atr(high, low, close, period=14):
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(window=period).mean()

    

    @staticmethod
    def get_ote_levels(high, low, direction='bullish'):
        """
        Menghitung Fibonacci Golden Zone (OTE).
        Direction: 'bullish' (swing low ke swing high) atau 'bearish' (swing high ke swing low)
        """
        diff = high - low
        if direction == 'bullish':

            return {
                '618': low + (diff * 0.618),
                '705': low + (diff * 0.705),
                '79': low + (diff * 0.79)
            }
        else: # bearish
            
            return {
                '618': high - (diff * 0.618),
                '705': high - (diff * 0.705),
                '79': high - (diff * 0.79)
            }