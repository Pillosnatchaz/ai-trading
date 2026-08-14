import pandas as pd
import numpy as np
from .indicator_math import IndicatorMath

class FeatureBuilder:
    def __init__(self):
        self.math = IndicatorMath()
        
    def build(self, df, now_wib=None):
        """
        Membangun matriks fitur dari data OHLCV yang masuk.
        df harus memiliki kolom: 'bid', 'ask', 'h1_close', 'h4_close', 'open', 'close', 'high', 'low'
        """
        last_bid = df['bid'].iloc[-1]
        last_price = df['close'].iloc[-1]
        
        # 1. SMC Features (FVG)
        fvgs = self.math.detect_fvg(df)
        has_fvg = 1 if len(fvgs) > 0 else 0
        
        # 2. Technical Indicators (Oscillators & Volatility)
        rsi_series = self.math.get_rsi(df['close'])
        rsi = rsi_series.iloc[-1] if not rsi_series.empty and pd.notnull(rsi_series.iloc[-1]) else 50.0

        stoch_k_series, _ = self.math.get_stochastic(df['high'], df['low'], df['close'])
        stoch_k = stoch_k_series.iloc[-1] if not stoch_k_series.empty and pd.notnull(stoch_k_series.iloc[-1]) else 50.0

        _, _, bb_bw_series, bb_pctb_series = self.math.get_bollinger_bands(df['close'])
        bb_bw = bb_bw_series.iloc[-1] if not bb_bw_series.empty and pd.notnull(bb_bw_series.iloc[-1]) else 0.0
        bb_pctb = bb_pctb_series.iloc[-1] if not bb_pctb_series.empty and pd.notnull(bb_pctb_series.iloc[-1]) else 0.5

        atr_series = self.math.get_atr(df['high'], df['low'], df['close'])
        atr = atr_series.iloc[-1] if not atr_series.empty and pd.notnull(atr_series.iloc[-1]) else 1.5
        atr = max(atr, 0.5)
        
        # FVG distance normalized by ATR (NaN when absent, handled natively by LightGBM)
        if has_fvg and atr > 0:
            nearest_fvg_price = min([f['price'] for f in fvgs], key=lambda p: abs(last_price - p))
            fvg_dist_atr = (last_price - nearest_fvg_price) / atr
        else:
            fvg_dist_atr = np.nan

        ema_50_series = self.math.get_ema(df['bid'], 50)
        ema_50_current = ema_50_series.iloc[-1]
        ema_50_past = ema_50_series.iloc[-5] if len(ema_50_series) >= 5 else ema_50_current
        ema_50_slope = (ema_50_current - ema_50_past) / ema_50_past if ema_50_past != 0 else 0.0

        # Time / Session Transition Countdown (WIB boundaries: 14:00, 19:30, 22:00)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        if now_wib is None:
            now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
        current_minutes = now_wib.hour * 60 + now_wib.minute
        session_boundaries = [14 * 60, 19 * 60 + 30, 22 * 60]
        future_boundaries = [b - current_minutes for b in session_boundaries if b > current_minutes]
        mins_to_session_transition = min(future_boundaries) if len(future_boundaries) > 0 else 999.0

        # Distance features (ATR-normalized per PRD v4.0)
        mom_dist_m5 = (last_bid - df['m5_close'].iloc[-1]) / atr if pd.notnull(df['m5_close'].iloc[-1]) else 0
        mom_dist_m15 = (last_bid - df['m15_close'].iloc[-1]) / atr if pd.notnull(df['m15_close'].iloc[-1]) else 0
        mom_dist_h1 = (last_bid - df['h1_close'].iloc[-1]) / atr if pd.notnull(df['h1_close'].iloc[-1]) else 0

        # Microstructure features
        last_open = df['open'].iloc[-1]
        last_high = df['high'].iloc[-1]
        last_low = df['low'].iloc[-1]
        body_size = abs(last_price - last_open)
        upper_wick = last_high - max(last_price, last_open)
        lower_wick = min(last_price, last_open) - last_low
        wick_body_ratio = (upper_wick + lower_wick) / body_size if body_size > 0.01 else 1.0

        # Multi-candle Swing levels (20 lookback)
        swing_high, swing_low = self.math.get_swing_levels(df, lookback=20)

        # Volatility Regime
        if atr < 1.0:
            volatility_regime = "LOW"
        elif atr > 2.5:
            volatility_regime = "HIGH"
        else:
            volatility_regime = "NORMAL"

        # Tick Volume (native from MT4 if available)
        tick_volume = float(df['volume'].iloc[-1]) if 'volume' in df.columns and pd.notnull(df['volume'].iloc[-1]) else 1.0

        # Combine all features
        features = {
            # Trend & Momentum Distance
            'dist_ema_50': (last_bid - ema_50_current) / atr,  # ponytail: atr always >= 0.5 from floor above
            'ema_50_slope': ema_50_slope,
            'mom_dist_m5': mom_dist_m5,
            'mom_dist_m15': mom_dist_m15,
            'mom_dist_h1': mom_dist_h1,
            'rel_h1': mom_dist_h1,  # Backward compatibility alias for main_loop H1 filter
            
            # Structural (FVG & Swings)
            'has_fvg': has_fvg,
            'fvg_dist_atr': fvg_dist_atr,
            'swing_high': swing_high,
            'swing_low': swing_low,
            
            # Technicals (Oscillators/Volatility)
            'rsi': rsi,
            'stoch_k': stoch_k,
            'bb_pctb': bb_pctb,
            'bb_bw': bb_bw,
            'atr': atr,
            'volatility_regime': volatility_regime,
            
            # Microstructure & Time
            'spread': df['ask'].iloc[-1] - df['bid'].iloc[-1],
            'wick_body_ratio': wick_body_ratio,
            'tick_volume': tick_volume,
            'mins_to_session_transition': mins_to_session_transition
        }
        
        return features