import sqlite3, pandas as pd, json

conn = sqlite3.connect('ai_data.db')
df = pd.read_sql_query("SELECT * FROM live_trades WHERE timestamp >= date('now')", conn)
print(f'Total trades today: {len(df)}')

wins = df[df['profit'] > 0]
losses = df[df['profit'] < 0]
print(f'Wins: {len(wins)}, Losses: {len(losses)}')

buy_losses = losses[losses['direction'] == 'BUY']
print(f'BUY Losses: {len(buy_losses)}')

if len(buy_losses) > 0:
    print('\n=== Sample Features of the First BUY Loss ===')
    sample_feat = json.loads(buy_losses.iloc[0]['features_json']) if buy_losses.iloc[0]['features_json'] else {}
    for k, v in sample_feat.items():
        if isinstance(v, float):
            print(f'  {k}: {v:.5f}')
        else:
            print(f'  {k}: {v}')
