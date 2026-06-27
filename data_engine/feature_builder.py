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
        
        # 1. SMC Features (Order Block & FVG)
        # ema_50 = self.math.get_ema(df['bid'], 50).iloc[-1]
        bullish_obs, bearish_obs = self.math.detect_order_blocks(df)
        fvgs = self.math.detect_fvg(df)
        
        nearest_bullish_ob = min([abs(last_price - ob) for ob in bullish_obs]) if bullish_obs else 9999
        nearest_bearish_ob = min([abs(last_price - ob) for ob in bearish_obs]) if bearish_obs else 9999
        
        nearest_fvg = min([abs(last_price - f['price']) for f in fvgs]) if fvgs else 9999
        
        # 2. Technical Indicators (Oscillators & Volatility)
        rsi_series = self.math.get_rsi(df['close'])
        rsi = rsi_series.iloc[-1] if not rsi_series.empty and pd.notnull(rsi_series.iloc[-1]) else 50.0

        stoch_k_series, _ = self.math.get_stochastic(df['high'], df['low'], df['close'])
        stoch_k = stoch_k_series.iloc[-1] if not stoch_k_series.empty and pd.notnull(stoch_k_series.iloc[-1]) else 50.0

        _, _, bb_bw_series, bb_pctb_series = self.math.get_bollinger_bands(df['close'])
        bb_bw = bb_bw_series.iloc[-1] if not bb_bw_series.empty and pd.notnull(bb_bw_series.iloc[-1]) else 0.0
        bb_pctb = bb_pctb_series.iloc[-1] if not bb_pctb_series.empty and pd.notnull(bb_pctb_series.iloc[-1]) else 0.5

        atr_series = self.math.get_atr(df['high'], df['low'], df['close'])
        atr = atr_series.iloc[-1] if not atr_series.empty and pd.notnull(atr_series.iloc[-1]) else 0.0

        # 3. OTE Logic
        # Menggunakan logika OTE untuk memeriksa apakah harga di area diskon/premium
        ote = self.math.get_ote_levels(df['high'].iloc[-1], df['low'].iloc[-1])  

        # Gabungkan semua fitur
        features = {
            # Trend & Base
            'dist_ema_50': (last_bid - self.math.get_ema(df['bid'], 50).iloc[-1]) / last_bid,
            'rel_h1': (last_bid - df['h1_close'].iloc[-1]) / last_bid,
            'rel_h4': (last_bid - df['h4_close'].iloc[-1]) / last_bid,
            
            # SMC
            'dist_to_bull_ob': nearest_bullish_ob,
            'dist_to_bear_ob': nearest_bearish_ob,
            'dist_to_fvg': nearest_fvg,
            'is_near_ob': 1 if (nearest_bullish_ob < 10.0 or nearest_bearish_ob < 10.0) else 0,
            
            # Technicals (Oscillators/Volatility)
            'rsi': rsi,
            'stoch_k': stoch_k,
            'bb_pctb': bb_pctb,
            'bb_bw': bb_bw,
            'atr': atr,
            
            # Spread
            'spread': df['ask'].iloc[-1] - df['bid'].iloc[-1]
        }
        
        return features