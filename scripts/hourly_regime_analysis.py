import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def analyze_hourly_regimes(db_path, csv_path):
    # 1. Load Live Trades
    conn = sqlite3.connect(db_path)
    trades_df = pd.read_sql_query("SELECT timestamp, profit, outcome FROM live_trades WHERE timestamp >= datetime('now', '-30 days')", conn)
    conn.close()

    if trades_df.empty:
        # Fallback to absolute date if sqlite 'now' is wrong context
        conn = sqlite3.connect(db_path)
        trades_df = pd.read_sql_query("SELECT timestamp, profit, outcome FROM live_trades", conn)
        conn.close()

    trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
    
    # Filter last 30 days based on max timestamp in trades
    max_date = trades_df['timestamp'].max()
    if pd.isna(max_date):
        print("No trade data found.")
        return
    thirty_days_ago = max_date - timedelta(days=30)
    trades_df = trades_df[trades_df['timestamp'] >= thirty_days_ago].copy()

    # Create Hour column for merging
    trades_df['hour_start'] = trades_df['timestamp'].dt.floor('h')
    
    # Calculate hourly trade metrics
    # win = outcome is 'WIN' or profit > 0
    trades_df['is_win'] = (trades_df['profit'] > 0).astype(int)
    
    hourly_trades = trades_df.groupby('hour_start').agg(
        total_profit=('profit', 'sum'),
        total_trades=('profit', 'count'),
        win_rate=('is_win', 'mean'),
        avg_profit_per_trade=('profit', 'mean')
    ).reset_index()

    # 2. Load Market Data
    market_df = pd.read_csv(csv_path)
    market_df['timestamp'] = pd.to_datetime(market_df['timestamp'])
    market_df = market_df[market_df['timestamp'] >= thirty_days_ago].copy()
    
    # Set index to timestamp for resampling
    market_df.set_index('timestamp', inplace=True)
    
    # Calculate 1-min returns for volatility
    market_df['returns'] = market_df['close'].pct_change()
    
    # Resample to Hourly
    hourly_market = market_df.resample('h').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum'),
        volatility=('returns', 'std')  # Standard deviation of 1-min returns
    ).reset_index()
    
    hourly_market.rename(columns={'timestamp': 'hour_start'}, inplace=True)
    
    # Calculate more hourly features
    hourly_market['trend_pct'] = (hourly_market['close'] - hourly_market['open']) / hourly_market['open'] * 100
    hourly_market['high_low_range_pct'] = (hourly_market['high'] - hourly_market['low']) / hourly_market['low'] * 100
    
    # Average true range proxy
    hourly_market['body_size'] = abs(hourly_market['close'] - hourly_market['open'])
    hourly_market['upper_shadow'] = hourly_market['high'] - hourly_market[['open', 'close']].max(axis=1)
    hourly_market['lower_shadow'] = hourly_market[['open', 'close']].min(axis=1) - hourly_market['low']
    
    # 3. Merge Data
    merged_df = pd.merge(hourly_market, hourly_trades, on='hour_start', how='inner')
    
    if merged_df.empty:
        print("No overlapping data between trades and market data.")
        return
        
    # 4. Classify Regimes
    # Volatility Regimes
    vol_33 = merged_df['high_low_range_pct'].quantile(0.33)
    vol_66 = merged_df['high_low_range_pct'].quantile(0.66)
    
    def classify_volatility(v):
        if v < vol_33: return 'Low Volatility'
        elif v < vol_66: return 'Medium Volatility'
        else: return 'High Volatility'
        
    merged_df['volatility_regime'] = merged_df['high_low_range_pct'].apply(classify_volatility)
    
    # Trend Regimes
    trend_33 = merged_df['trend_pct'].quantile(0.33)
    trend_66 = merged_df['trend_pct'].quantile(0.66)
    
    def classify_trend(t):
        if t < -0.1: return 'Downtrend'
        elif t > 0.1: return 'Uptrend'
        else: return 'Ranging'
        
    merged_df['trend_regime'] = merged_df['trend_pct'].apply(classify_trend)
    
    # Combined Regime
    merged_df['market_regime'] = merged_df['volatility_regime'] + " & " + merged_df['trend_regime']
    
    # 5. Analyze Performance by Regime
    print("=== OVERALL PERFORMANCE BY MARKET REGIME ===")
    regime_perf = merged_df.groupby('market_regime').agg(
        hours=('hour_start', 'count'),
        total_trades=('total_trades', 'sum'),
        total_profit=('total_profit', 'sum'),
        avg_profit_per_hour=('total_profit', 'mean'),
        win_rate=('win_rate', 'mean')
    ).sort_values('total_profit', ascending=False)
    
    print(regime_perf.to_markdown())
    
    print("\n\n=== OVERALL PERFORMANCE BY VOLATILITY LEVEL ===")
    vol_perf = merged_df.groupby('volatility_regime').agg(
        hours=('hour_start', 'count'),
        total_trades=('total_trades', 'sum'),
        total_profit=('total_profit', 'sum'),
        avg_profit_per_hour=('total_profit', 'mean'),
        win_rate=('win_rate', 'mean')
    ).sort_values('total_profit', ascending=False)
    print(vol_perf.to_markdown())

    print("\n\n=== OVERALL PERFORMANCE BY TREND TYPE ===")
    trend_perf = merged_df.groupby('trend_regime').agg(
        hours=('hour_start', 'count'),
        total_trades=('total_trades', 'sum'),
        total_profit=('total_profit', 'sum'),
        avg_profit_per_hour=('total_profit', 'mean'),
        win_rate=('win_rate', 'mean')
    ).sort_values('total_profit', ascending=False)
    print(trend_perf.to_markdown())
    
    # 6. Deep Dive: Top 5 Best Hours vs Top 5 Worst Hours
    print("\n\n=== TOP 5 MOST PROFITABLE HOURS ===")
    best_hours = merged_df.sort_values('total_profit', ascending=False).head(5)
    print(best_hours[['hour_start', 'total_profit', 'market_regime', 'trend_pct', 'high_low_range_pct', 'win_rate']].to_markdown())

    print("\n\n=== TOP 5 LEAST PROFITABLE HOURS ===")
    worst_hours = merged_df.sort_values('total_profit', ascending=True).head(5)
    print(worst_hours[['hour_start', 'total_profit', 'market_regime', 'trend_pct', 'high_low_range_pct', 'win_rate']].to_markdown())

    # Write results to a file for artifact generation later
    with open('regime_analysis_results.txt', 'w') as f:
        f.write("=== OVERALL PERFORMANCE BY MARKET REGIME ===\n")
        f.write(regime_perf.to_markdown() + "\n\n")
        f.write("=== OVERALL PERFORMANCE BY VOLATILITY LEVEL ===\n")
        f.write(vol_perf.to_markdown() + "\n\n")
        f.write("=== OVERALL PERFORMANCE BY TREND TYPE ===\n")
        f.write(trend_perf.to_markdown() + "\n\n")
        f.write("=== TOP 5 MOST PROFITABLE HOURS ===\n")
        f.write(best_hours[['hour_start', 'total_profit', 'market_regime', 'trend_pct', 'high_low_range_pct', 'win_rate']].to_markdown() + "\n\n")
        f.write("=== TOP 5 LEAST PROFITABLE HOURS ===\n")
        f.write(worst_hours[['hour_start', 'total_profit', 'market_regime', 'trend_pct', 'high_low_range_pct', 'win_rate']].to_markdown() + "\n\n")

if __name__ == "__main__":
    db_path = "E:/Projects/ai-trading-iso/ai_data.db"
    csv_path = "E:/Projects/ai-trading-iso/history_dump.csv"
    analyze_hourly_regimes(db_path, csv_path)
