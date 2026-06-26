import zmq
import json

def start_zmq_listener(port=5555):
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    print(f"[*] MIA v3.0 Bridge: Mendengarkan di port {port}...")
    
    while True:
        try:
            message = socket.recv_string()
            data = json.loads(message)
            
            # Menggunakan .get() agar tidak crash jika key hilang
            symbol = data.get('symbol', 'N/A')
            bid = data.get('bid', 0.0)
            ask = data.get('ask', 0.0)
            h1 = data.get('h1_close', 0.0)
            h4 = data.get('h4_close', 0.0)
            
            print(f"[*] TICK RECEIVED | {symbol} | Bid: {bid} | Ask: {ask} | H1: {h1} | H4: {h4}")
            
        except Exception as e:
            print(f"[!] Error pada bridge: {e}")
            print(f"[!] Raw message: {message}")
            break

if __name__ == "__main__":
    start_zmq_listener()