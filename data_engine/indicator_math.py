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

    # @staticmethod
    # def detect_order_blocks(df, window=5):
    #     # Pastikan kolom sudah ada
    #     if 'open' not in df.columns or 'close' not in df.columns:
    #         return [], []

    #     df = df.copy() # Hindari SettingWithCopyWarning
    #     df['body'] = abs(df['close'] - df['open'])
    #     avg_body = df['body'].rolling(window=20).mean()
        
    #     bullish_obs, bearish_obs = [], []

    #     for i in range(window, len(df) - 1):
    #         # Bullish OB
    #         if df['close'].iloc[i] < df['open'].iloc[i]: 
    #             if df['close'].iloc[i+1] > (df['open'].iloc[i+1] + avg_body.iloc[i+1]):
    #                 bullish_obs.append(df['low'].iloc[i])
    #         # Bearish OB
    #         if df['close'].iloc[i] > df['open'].iloc[i]:
    #             if df['close'].iloc[i+1] < (df['open'].iloc[i+1] - avg_body.iloc[i+1]):
    #                 bearish_obs.append(df['high'].iloc[i])
                    
    #     return bullish_obs[-5:], bearish_obs[-5:]

    @staticmethod
    def detect_order_blocks(df, window=5):
        # Tambahkan drop_duplicates agar data statis tidak dihitung berulang-ulang
        df = df.drop_duplicates(subset=['open', 'high', 'low', 'close'])
        
        if len(df) < 2: return [], []
        
        df = df.copy()
        df['body'] = abs(df['close'] - df['open'])
        avg_body = df['body'].rolling(window=20, min_periods=1).mean()
        
        bullish_obs, bearish_obs = [], []
        # Gunakan threshold lebih rendah (0.5x rata-rata body) agar lebih sensitif
        for i in range(window, len(df) - 1):
            if df['close'].iloc[i] < df['open'].iloc[i]: # Bullish OB
                if df['close'].iloc[i+1] > df['open'].iloc[i+1]:
                    if df['body'].iloc[i+1] > (avg_body.iloc[i+1] * 0.5): 
                        bullish_obs.append(df['low'].iloc[i])
            if df['close'].iloc[i] > df['open'].iloc[i]: # Bearish OB
                if df['close'].iloc[i+1] < df['open'].iloc[i+1]:
                    if df['body'].iloc[i+1] > (avg_body.iloc[i+1] * 0.5):
                        bearish_obs.append(df['high'].iloc[i])
        return bullish_obs[-5:], bearish_obs[-5:]
    
    @staticmethod
    def get_sma(series, period):
        return series.rolling(window=period).mean()

    @staticmethod
    def get_ema(series, period):
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def get_ote_levels(high, low):
        """Menghitung zona Fibonacci OTE (Optimal Trade Entry)"""
        diff = high - low
        return {
            '50': high - (diff * 0.50),
            '618': high - (diff * 0.618),
            '705': high - (diff * 0.705),
            '79': high - (diff * 0.79)
        }