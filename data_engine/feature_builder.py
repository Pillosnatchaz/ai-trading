import pandas as pd
from .indicator_math import IndicatorMath

class FeatureBuilder:
    def __init__(self):
        self.math = IndicatorMath()
        
    def build(self, df):
        """
        Membangun matriks fitur dari data OHLCV yang masuk.
        df harus memiliki kolom: 'bid', 'ask', 'h1_close', 'h4_close', 'open', 'close', 'high', 'low'
        """
        last_bid = df['bid'].iloc[-1]
        last_price = df['close'].iloc[-1]
        
        # 1. Fitur Indikator Dasar
        ema_50 = self.math.get_ema(df['bid'], 50).iloc[-1]
        
        # 2. Fitur SMC (Order Blocks)
        bullish_obs, bearish_obs = self.math.detect_order_blocks(df)
        print(f"[DEBUG] Bullish OBs detected: {bullish_obs}")
        print(f"[DEBUG] Bearish OBs detected: {bearish_obs}")
        nearest_bullish_ob = min([abs(last_price - ob) for ob in bullish_obs]) if bullish_obs else 9999
        nearest_bearish_ob = min([abs(last_price - ob) for ob in bearish_obs]) if bearish_obs else 9999
        
        # 3. Fitur SMC (FVG - Fair Value Gaps)
        fvgs = self.math.detect_fvg(df)
        # Jarak harga ke FVG terdekat
        fvg_prices = [f['price'] for f in fvgs]
        nearest_fvg = min([abs(last_price - p) for p in fvg_prices]) if fvgs else 9999
        
        # Gabungkan semua fitur
        features = {
            # Trend Features
            'dist_ema_50': (last_bid - ema_50) / last_bid,
            'rel_h1': (last_bid - df['h1_close'].iloc[-1]) / last_bid,
            'rel_h4': (last_bid - df['h4_close'].iloc[-1]) / last_bid,
            
            # SMC Features
            'dist_to_bull_ob': nearest_bullish_ob,
            'dist_to_bear_ob': nearest_bearish_ob,
            'dist_to_fvg': nearest_fvg,
            'is_near_ob': 1 if (nearest_bullish_ob < 10.0 or nearest_bearish_ob < 10.0) else 0,
            
            # Volatility
            'spread': df['ask'].iloc[-1] - df['bid'].iloc[-1]
        }
        
        return features