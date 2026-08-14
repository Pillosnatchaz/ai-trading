//+------------------------------------------------------------------+
//| MIA v4.0 ZMQ Bridge — CENT LIVE ACCOUNT                          |
//|                                                                  |
//| Copy of MIA_v3_ZMQ_Bridge_Dual.mq4 for the HFM Cent live account.|
//| Differences from the v3 bridge:                                  |
//|   1. Pip size is fixed at 0.1 price units instead of 10*Point,    |
//|      so a 3-digit gold feed cannot silently make every stop 10x   |
//|      too tight. 0.1 is the definition used throughout the Python  |
//|      side (triple_barrier.py:13).                                 |
//|   2. Ports are inputs and default to 5567/5568 to match           |
//|      orchestration/main_loop.py.                                  |
//|   3. MaxLot hard cap — this account trades real money, so a bad   |
//|      lot value from Python gets clamped here rather than filled.  |
//|   4. OnInit prints the feed's Digits and the resulting stop        |
//|      distance so the 2-digit/3-digit question is answered the     |
//|      moment the EA is attached.                                   |
//+------------------------------------------------------------------+
#include <Zmq/Zmq.mqh>

input string PubAddress  = "tcp://*:5567";        // EA publishes candles here (Python SUBs)
input string SubAddress  = "tcp://127.0.0.1:5568"; // EA listens for orders here (Python PUBs)
input double MaxLot      = 0.01;                   // hard cap on lot size, live-money guard
input int    SlippagePts = 3;

// ponytail: a pip is 0.1 price units by definition on the Python side.
// Deriving it from Point assumes a 2-digit gold feed; this does not.
#define PIP 0.1

Context *ctx;
Socket *pub;
Socket *sub;

int OnInit() {
   ctx = new Context("MIA_v4_Cent_Context");
   pub = new Socket(*ctx, ZMQ_PUB);
   sub = new Socket(*ctx, ZMQ_SUB);

   if(!pub.bind(PubAddress)) {
      Print("Gagal bind socket ZMQ pub di ", PubAddress);
      return(INIT_FAILED);
   }

   if(!sub.connect(SubAddress)) {
      Print("Warning: ZMQ sub belum connect ke Python (akan retry otomatis)");
   }
   sub.subscribe(""); // listen to all Python signals

   Print("ZMQ Bridge CENT EA siap. PUB=", PubAddress, " SUB=", SubAddress);

   // ponytail: answers the "is this feed 2 or 3 digit" question on attach.
   // A 40-pip stop must read 4.00. If it prints 0.40 the feed is 3-digit and
   // any EA still using 10*Point would be placing stops 10x too tight.
   PrintFormat("Feed check: Digits=%d Point=%.5f  ->  40 pip stop = %.2f price  (expect 4.00)",
               (int)Digits, Point, 40 * PIP);
   PrintFormat("Account: %s  currency=%s  balance=%.2f  MaxLot=%.2f",
               AccountInfoString(ACCOUNT_SERVER), AccountInfoString(ACCOUNT_CURRENCY),
               AccountInfoDouble(ACCOUNT_BALANCE), MaxLot);

   double minlot = MarketInfo(Symbol(), MODE_MINLOT);
   double lotstep = MarketInfo(Symbol(), MODE_LOTSTEP);
   double contract = MarketInfo(Symbol(), MODE_LOTSIZE);
   PrintFormat("Symbol %s: minlot=%.2f lotstep=%.2f contract=%.0f  stoplevel=%.0f pts",
               Symbol(), minlot, lotstep, contract, MarketInfo(Symbol(), MODE_STOPLEVEL));

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
   long vol     = iVolume(Symbol(), PERIOD_M1, 1);

   long candle_time = iTime(Symbol(), PERIOD_M1, 0);

   // Kirim data ke Python melalui ZeroMQ (termasuk M1 tick volume dan Account Equity)
   string json_data = StringFormat(
      "{\"symbol\": \"%s\", \"bid\": %f, \"ask\": %f, \"open\": %f, \"high\": %f, \"low\": %f, \"close\": %f, \"m5_close\": %f, \"m15_close\": %f, \"h1_close\": %f, \"h4_close\": %f, \"d1_open\": %f, \"volume\": %d, \"time\": %d, \"equity\": %f}",
      Symbol(), Bid, Ask, open, high, low, close, iClose(Symbol(), PERIOD_M5, 1), iClose(Symbol(), PERIOD_M15, 1), iClose(Symbol(), PERIOD_H1, 1), iClose(Symbol(), PERIOD_H4, 1), iOpen(Symbol(), PERIOD_D1, 0), vol, candle_time, AccountInfoDouble(ACCOUNT_EQUITY)
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

           // Parse dynamic lot size
           double trade_lot = 0.01;
           int lot_start = StringFind(rcv, "\"lot\": ");
           if(lot_start >= 0) {
               lot_start += 7;
               int lot_end = StringFind(rcv, ",", lot_start);
               trade_lot = StringToDouble(StringSubstr(rcv, lot_start, lot_end - lot_start));
           }
           if(trade_lot <= 0) trade_lot = 0.01;
           // ponytail: real money on this account — never fill more than MaxLot,
           // whatever Python asks for. Trust boundary, not an optimisation.
           if(trade_lot > MaxLot) {
               PrintFormat("Lot %.2f from Python exceeds MaxLot %.2f — clamped.", trade_lot, MaxLot);
               trade_lot = MaxLot;
           }

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
               double sl_price = Ask - (sl_pips * PIP);
               double tp_price = Ask + (tp_pips * PIP);
               ticket = OrderSend(Symbol(), OP_BUY, trade_lot, Ask, SlippagePts, sl_price, tp_price, "AI_Trade", trade_id, 0, Blue);
           } else {
               double sl_price = Bid + (sl_pips * PIP);
               double tp_price = Bid - (tp_pips * PIP);
               ticket = OrderSend(Symbol(), OP_SELL, trade_lot, Bid, SlippagePts, sl_price, tp_price, "AI_Trade", trade_id, 0, Red);
           }

           if(ticket < 0) {
               Print("OrderSend failed with error #", GetLastError());
           }
       }

        // ponytail: close all open trades on news embargo signal from Python
        if(StringFind(rcv, "\"action\": \"CLOSE_ALL\"") >= 0) {
            for(int j = OrdersTotal() - 1; j >= 0; j--) {
                if(OrderSelect(j, SELECT_BY_POS, MODE_TRADES) && OrderSymbol() == Symbol()) {
                    if(OrderType() == OP_BUY)
                        OrderClose(OrderTicket(), OrderLots(), Bid, SlippagePts, clrYellow);
                    else if(OrderType() == OP_SELL)
                        OrderClose(OrderTicket(), OrderLots(), Ask, SlippagePts, clrYellow);
                }
            }
            Print("CLOSE_ALL: All positions closed (news embargo).");
        }
    }

   // --- Send TRADE_CLOSED Back ---
   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--) {
       if(OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) {
           int t_id = OrderMagicNumber();
           if(t_id > 0 && OrderSymbol() == Symbol()) { // It's our AI trade
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
