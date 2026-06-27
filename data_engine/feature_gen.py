import pandas as pd
import numpy as np
from collections import deque

class FeatureGenerator:
    def __init__(self, window_size=100):
        # Buffer untuk menyimpan tick terakhir guna menghitung moving average
        self.tick_buffer = deque(maxlen=window_size)
        
    def add_tick(self, bid, ask, h1_close, h4_close):
        # Tambahkan tick baru
        self.tick_buffer.append({'bid': bid, 'ask': ask, 'h1': h1_close, 'h4': h4_close})
        
    def generate_features(self):
        if len(self.tick_buffer) < 20:
            return None # Belum cukup data
        
        df = pd.DataFrame(self.tick_buffer)
        
        # 1. Engineering Technical Features (Contoh SMA)
        features = {
            'sma_7': df['bid'].rolling(window=7).mean().iloc[-1],
            'sma_21': df['bid'].rolling(window=21).mean().iloc[-1],
            'price_vs_h1': df['bid'].iloc[-1] - df['h1'].iloc[-1],
            'spread': df['ask'].iloc[-1] - df['bid'].iloc[-1]
        }
        
        return features

# Contoh cara panggil di main loop nanti:
# gen = FeatureGenerator()
# gen.add_tick(bid, ask, h1, h4)
# features = gen.generate_features()