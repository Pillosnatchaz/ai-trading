import requests

def send_discord_alert(webhook_url, message):
    # 👱 Ponytail: Just a simple POST request. No discord.py dependency needed.
    try:
        requests.post(webhook_url, json={"content": message}, timeout=5)
    except Exception as e:
        pass # If discord is down, don't crash the trading bot

# Example usage:
# send_discord_alert("https://discord.com/api/webhooks/...", "🤖 MIA v3.0: Trade Executed! BUY XAUUSD")
