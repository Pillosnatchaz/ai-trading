#property strict
#property script_show_inputs

// ponytail: Minimum viable CSV dump script. 
// Attach to an M1 chart. Dumps to MT4 Data Folder -> MQL4/Files/history_dump.csv
input int BarsToDump = 200000; // ~6 months of M1 data

void OnStart() {
    string filename = "history_dump.csv";
    int h = FileOpen(filename, FILE_CSV|FILE_WRITE, ",");
    if(h == INVALID_HANDLE) return;
    
    FileWrite(h, "timestamp,open,high,low,close,volume");
    
    int limit = MathMin(BarsToDump, Bars-1);
    for(int i = limit; i >= 0; i--) {
        // Format: YYYY.MM.DD HH:MI
        FileWrite(h, TimeToString(Time[i]), Open[i], High[i], Low[i], Close[i], Volume[i]);
    }
    
    FileClose(h);
    Print("Done! Dumped ", limit, " bars. Look in MQL4/Files/", filename);
}
