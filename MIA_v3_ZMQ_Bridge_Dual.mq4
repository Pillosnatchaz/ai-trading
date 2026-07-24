#include <Zmq/Zmq.mqh>

Context *ctx;
Socket *pub;
Socket *sub;
string z_address = "tcp://*:5557"; // Changed port
string z_sub_addr = "tcp://127.0.0.1:5558"; // Changed port

int OnInit() {
   ctx = new Context("MIA_v3_Context");
   pub = new Socket(*ctx, ZMQ_PUB);
   sub = new Socket(*ctx, ZMQ_SUB);
   
   if(!pub.bind(z_address)) {
      Print("Gagal bind socket ZMQ pub di port 5557");
      return(INIT_FAILED);
   }
   
   if(!sub.connect(z_sub_addr)) {
      Print("Warning: ZMQ sub belum connect ke Python (akan retry otomatis)");
   }
   sub.subscribe(""); // listen to all Python signals
   
   Print("ZMQ Bridge DUAL EA siap di port 5557 dan 5558");
   return(INIT_SUCCEEDED);
}

bool history_sent = false;

void OnTick() {
   // Kirim 100 candle history di tick pertama
   if(!history_sent) {
      for(int i = 100; i >= 1; i--) {
         string hist = StringFormat("{\"symbol\": \"%s\", \"bid\": %f, \"ask\": %f, \"open\": %f, \"high\": %f, \"low\": %f, \"close\": %f, \"m5_close\": %f, \"m15_close\": %f, \"h1_close\": %f, \"h4_close\": %f, \"d1_open\": %f, \"time\": %d}",
            Symbol(), iClose(Symbol(), PERIOD_M1, i), iClose(Symbol(), PERIOD_M1, i), iOpen(Symbol(), PERIOD_M1, i), iHigh(Symbol(), PERIOD_M1, i), iLow(Symbol(), PERIOD_M1, i), iClose(Symbol(), PERIOD_M1, i), iClose(Symbol(), PERIOD_M5, 1), iClose(Symbol(), PERIOD_M15, 1), iClose(Symbol(), PERIOD_H1, 1), iClose(Symbol(), PERIOD_H4, 1), iOpen(Symbol(), PERIOD_D1, 0), iTime(Symbol(), PERIOD_M1, i-1));
         pub.send(hist);
      }
      history_sent = true;
   }

   // Mengambil data OHLC dari candle yang sudah tertutup
   double open  = iOpen(Symbol(), PERIOD_M1, 1); 
   double high  = iHigh(Symbol(), PERIOD_M1, 1);
   double low   = iLow(Symbol(), PERIOD_M1, 1);
   double close = iClose(Symbol(), PERIOD_M1, 1);
   
   long candle_time = iTime(Symbol(), PERIOD_M1, 0);
   
   // Kirim data ke Python melalui ZeroMQ
   string json_data = StringFormat(
      "{\"symbol\": \"%s\", \"bid\": %f, \"ask\": %f, \"open\": %f, \"high\": %f, \"low\": %f, \"close\": %f, \"m5_close\": %f, \"m15_close\": %f, \"h1_close\": %f, \"h4_close\": %f, \"d1_open\": %f, \"time\": %d}",
      Symbol(), Bid, Ask, open, high, low, close, iClose(Symbol(), PERIOD_M5, 1), iClose(Symbol(), PERIOD_M15, 1), iClose(Symbol(), PERIOD_H1, 1), iClose(Symbol(), PERIOD_H4, 1), iOpen(Symbol(), PERIOD_D1, 0), candle_time
   );
   
   pub.send(json_data);
   
   // --- Receive Python Signals ---
   ZmqMsg msg;
   if(sub.recv(msg, 1)) { // 1 = ZMQ_DONTWAIT
       string rcv = msg.getData();
       if(StringFind(rcv, "\"action\": \"BUY\"") >= 0 || StringFind(rcv, "\"action\": \"SELL\"") >= 0) {
           // Parse trade_id
           int id_start = StringFind(rcv, "\"trade_id\": ") + 12;
           int id_end = StringFind(rcv, ",", id_start);
           int trade_id = (int)StringToInteger(StringSubstr(rcv, id_start, id_end - id_start));
           
           // ponytail: no cooldown — Python controls trade frequency via ML threshold + H1 filter
           // Parse sl_pips and tp_pips from Python signal
           int sl_start = StringFind(rcv, "\"sl_pips\": ") + 11;
           int sl_end = StringFind(rcv, ",", sl_start);
           int sl_pips = (int)StringToInteger(StringSubstr(rcv, sl_start, sl_end - sl_start));
           int tp_start = StringFind(rcv, "\"tp_pips\": ") + 11;
           int tp_end = StringFind(rcv, "}", tp_start);
           int tp_pips = (int)StringToInteger(StringSubstr(rcv, tp_start, tp_end - tp_start));
           if(sl_pips <= 0) sl_pips = 40; // ponytail: fallback
           if(tp_pips <= 0) tp_pips = 60;
           
           int ticket = -1;
           if(StringFind(rcv, "\"action\": \"BUY\"") >= 0) {
               double sl_price = Ask - (sl_pips * 10 * Point); 
               double tp_price = Ask + (tp_pips * 10 * Point);
               ticket = OrderSend(Symbol(), OP_BUY, 0.01, Ask, 3, sl_price, tp_price, "AI_Trade", trade_id, 0, Blue);
           } else {
               double sl_price = Bid + (sl_pips * 10 * Point); 
               double tp_price = Bid - (tp_pips * 10 * Point);
               ticket = OrderSend(Symbol(), OP_SELL, 0.01, Bid, 3, sl_price, tp_price, "AI_Trade", trade_id, 0, Red);
           }
           
           if(ticket < 0) {
               Print("OrderSend failed with error #", GetLastError());
           }
       }
   }
   
   // --- Send TRADE_CLOSED Back ---
   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--) {
       if(OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) {
           int t_id = OrderMagicNumber();
           if(t_id > 0) { // It's our AI trade
               string gv_name = "AI_Sent_" + IntegerToString(t_id);
               if(!GlobalVariableCheck(gv_name)) {
                   double exit_price = OrderClosePrice();
                   double profit = OrderProfit();
                   int duration_sec = (int)(OrderCloseTime() - OrderOpenTime());
                   string close_msg = StringFormat("{\"action\": \"TRADE_CLOSED\", \"trade_id\": %d, \"exit_price\": %f, \"profit\": %f, \"duration\": %d}", t_id, exit_price, profit, duration_sec);
                   pub.send(close_msg);
                   GlobalVariableSet(gv_name, 1);
               }
           }
       }
   }
}

void OnDeinit(const int reason) {
   if(sub != NULL) delete sub;
   if(pub != NULL) delete pub;
   if(ctx != NULL) delete ctx;
}
