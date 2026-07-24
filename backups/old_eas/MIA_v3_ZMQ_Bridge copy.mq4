#include <Zmq/Zmq.mqh>

Context *ctx;
Socket *pub;
string z_address = "tcp://*:5555";

int OnInit() {
   ctx = new Context("MIA_v3_Context");
   pub = new Socket(*ctx, ZMQ_PUB);
   
   if(!pub.bind(z_address)) {
      Print("Gagal bind socket ZMQ");
      return(INIT_FAILED);
   }
   Print("ZMQ Bridge EA siap di port 5555");
   return(INIT_SUCCEEDED);
}

bool history_sent = false;

void OnTick() {
   // Kirim 100 candle history di tick pertama
   if(!history_sent) {
      for(int i = 100; i >= 1; i--) {
         string hist = StringFormat("{\"symbol\": \"%s\", \"bid\": %f, \"ask\": %f, \"open\": %f, \"high\": %f, \"low\": %f, \"close\": %f, \"h1_close\": %f, \"h4_close\": %f, \"time\": %d}",
            Symbol(), iClose(Symbol(), PERIOD_M1, i), iClose(Symbol(), PERIOD_M1, i), iOpen(Symbol(), PERIOD_M1, i), iHigh(Symbol(), PERIOD_M1, i), iLow(Symbol(), PERIOD_M1, i), iClose(Symbol(), PERIOD_M1, i), iClose(Symbol(), PERIOD_H1, 1), iClose(Symbol(), PERIOD_H4, 1), iTime(Symbol(), PERIOD_M1, i-1));
         pub.send(hist);
      }
      history_sent = true;
   }

   // Mengambil data OHLC dari candle yang sudah tertutup (indeks 1)
   // untuk stabilitas data.
   double open  = iOpen(Symbol(), PERIOD_M1, 1); 
   double high  = iHigh(Symbol(), PERIOD_M1, 1);
   double low   = iLow(Symbol(), PERIOD_M1, 1);
   double close = iClose(Symbol(), PERIOD_M1, 1);
   
   // Mengambil timestamp candle saat ini (indeks 0) sebagai ID unik candle
   // TimeCurrent() juga bisa digunakan, namun iTime lebih akurat untuk sinkronisasi candle
   long candle_time = iTime(Symbol(), PERIOD_M1, 0);
   
   // Kirim data ke Python melalui ZeroMQ
   string json_data = StringFormat(
      "{\"symbol\": \"%s\", \"bid\": %f, \"ask\": %f, \"open\": %f, \"high\": %f, \"low\": %f, \"close\": %f, \"h1_close\": %f, \"h4_close\": %f, \"time\": %d}",
      Symbol(), Bid, Ask, open, high, low, close, iClose(Symbol(), PERIOD_H1, 1), iClose(Symbol(), PERIOD_H4, 1), candle_time
   );
   
   pub.send(json_data);
}

void OnDeinit(const int reason) {
   if(pub != NULL) delete pub;
   if(ctx != NULL) delete ctx;
}