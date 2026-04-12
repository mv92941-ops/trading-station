"""
元大行情 API 串接層
架構：主後端（Python 3.14 64-bit）啟動 QAPI 橋接子進程（Python 3.9 32-bit），
      透過 stdout JSON Lines 接收行情資料。
"""

import asyncio
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone, timedelta, time as dtime
from pathlib import Path
from typing import Callable, Dict, List

PYTHON32  = r"C:\Users\mv929\AppData\Local\Programs\Python\Python39-32\python.exe"
BRIDGE    = Path(__file__).parent / "qapi_bridge.py"
RECONNECT = 15   # 橋接異常退出後幾秒重啟

TW = timezone(timedelta(hours=8))

def _is_market_hours() -> bool:
    """台灣股市交易時間：週一~五 09:00~13:35"""
    now = datetime.now(TW)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 0) <= t <= dtime(13, 35)

def _seconds_to_next_open() -> float:
    """距離下一個開盤的秒數（最多回傳 24 小時）"""
    now = datetime.now(TW)
    candidate = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return min((candidate - now).total_seconds(), 86400)


# ── K 棒聚合器 ───────────────────────────────────────────────────
class CandleAggregator:
    def __init__(self, symbol: str, timeframe_minutes: int):
        self.symbol = symbol
        self.tf     = timeframe_minutes
        self.current: Dict = {}

    def update(self, price: float, volume: int, ts: float):
        dt           = datetime.fromtimestamp(ts)
        period_start = self._period_start(dt)

        if not self.current:
            self.current = self._new_candle(period_start, price, volume)
            return None

        if period_start > self.current["period"]:
            completed = {k: self.current[k]
                         for k in ("open", "high", "low", "close")}
            completed["time"] = int(self.current["period"].timestamp())
            self.current = self._new_candle(period_start, price, volume)
            return completed

        self.current["high"]  = max(self.current["high"], price)
        self.current["low"]   = min(self.current["low"],  price)
        self.current["close"] = price
        return None

    def current_candle(self):
        if not self.current:
            return None
        c = {k: self.current[k] for k in ("open", "high", "low", "close")}
        c["time"] = int(self.current["period"].timestamp())
        return c

    def _period_start(self, dt: datetime) -> datetime:
        total   = dt.hour * 60 + dt.minute
        aligned = (total // self.tf) * self.tf
        return dt.replace(hour=aligned // 60, minute=aligned % 60,
                          second=0, microsecond=0)

    def _new_candle(self, period_start, price, volume) -> Dict:
        return {"period": period_start, "open": price, "high": price,
                "low": price, "close": price, "volume": volume}


# ── 主類別 ───────────────────────────────────────────────────────
class YuantaAPI:
    def __init__(self, config: dict):
        self.config = config
        syms = config["symbols"]
        self.sym_futures = syms["futures"]   # MXFPM1
        self.sym_tsmc    = syms["tsmc"]      # 2330
        self.sym_etf1    = syms["etf1"]      # 00631L
        self.sym_etf2    = syms["etf2"]      # 00675L

        self._callbacks: List[Callable] = []
        self._loop = None
        self._real_data_received = False

        self._agg: Dict[str, Dict[str, CandleAggregator]] = {
            sym: {"15": CandleAggregator(sym, 15), "60": CandleAggregator(sym, 60)}
            for sym in [self.sym_futures, self.sym_tsmc,
                        self.sym_etf1,    self.sym_etf2]
        }

    # ── 啟動 ─────────────────────────────────────────────────────
    async def connect(self):
        self._loop  = asyncio.get_event_loop()
        self._ready = threading.Event()
        threading.Thread(target=self._run_forever, daemon=True).start()
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._ready.wait(15)
        )

    # ── 橋接子進程管理（自動重啟，非交易時間休眠）──────────────
    def _run_forever(self):
        import platform
        if platform.system() != "Windows":
            print("[QAPI] 非 Windows 環境，橋接執行緒結束", flush=True)
            return

        attempt = 0
        self._ready.set()   # 讓 FastAPI startup 繼續，不等橋接就緒
        while True:
            if not _is_market_hours():
                wait = _seconds_to_next_open()
                print(f"[QAPI] 非交易時間，{wait/3600:.1f} 小時後重試", flush=True)
                # 每小時重新檢查一次，避免電腦時間跳躍
                threading.Event().wait(min(wait, 3600))
                continue

            attempt += 1
            print(f"[QAPI] 橋接啟動 #{attempt}", flush=True)
            try:
                proc = subprocess.Popen(
                    [PYTHON32, str(BRIDGE)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        self._handle(data)
                    except json.JSONDecodeError:
                        print(f"[QAPI] raw: {line}", flush=True)
                proc.wait()
                print(f"[QAPI] 橋接退出 code={proc.returncode}", flush=True)
            except Exception as e:
                print(f"[QAPI] 橋接例外: {e}", flush=True)

            if _is_market_hours():
                print(f"[QAPI] {RECONNECT}秒後重啟...", flush=True)
                threading.Event().wait(RECONNECT)

    # ── 處理橋接傳來的訊息 ───────────────────────────────────────
    def _handle(self, data: dict):
        t = data.get("type")

        if t == "log":
            print(f"[QAPI] {data['msg']}", flush=True)
            return

        if t == "status":
            print(f"[QAPI] 狀態 {data['status']}: {data['msg']}", flush=True)
            return

        if t == "error":
            print(f"[QAPI] 錯誤 {data.get('symbol','')} code={data.get('code')} {data.get('msg','')}", flush=True)
            return

        if t in ("mkt", "tick"):
            sym   = data.get("symbol", "")
            price = self._parse_price(sym, data.get("price", "0"))
            if price is None:
                return

            # 時間轉 timestamp
            ts = self._parse_time(data.get("time", ""))

            if not self._real_data_received:
                self._real_data_received = True
                print(f"[QAPI] ✓ 首筆行情：{sym} @ {price}", flush=True)

            # MXF 開頭的合約映射到期貨圖表
            display = self.sym_futures if sym.startswith("MXF") else sym
            self._process_tick(display, price, 1, ts)

    def _parse_price(self, symbol: str, raw: str) -> float:
        """期貨：直接點數；股票：元（原本就是小數字串）"""
        try:
            v = float(raw.replace(",", ""))
            # QAPI 股票報價已是元，不需除以 100
            return v if v > 0 else None
        except (ValueError, AttributeError):
            return None

    def _parse_time(self, time_str: str) -> float:
        """將 HHMMSS 或 HH:MM:SS 格式轉 Unix timestamp"""
        now = datetime.now()
        try:
            t = time_str.replace(":", "").strip()
            if len(t) >= 6:
                h, m, s = int(t[0:2]), int(t[2:4]), int(t[4:6])
                return now.replace(hour=h, minute=m, second=s,
                                   microsecond=0).timestamp()
        except (ValueError, IndexError):
            pass
        return now.timestamp()

    # ── Tick 處理 ────────────────────────────────────────────────
    def _process_tick(self, symbol: str, price: float, volume: int, ts: float):
        self._emit({"type": "tick", "symbol": symbol, "price": price, "ts": ts})
        if symbol not in self._agg:
            return
        for tf, agg in self._agg[symbol].items():
            completed = agg.update(price, volume, ts)
            if completed:
                self._emit({"type": "candle_completed",
                            "symbol": symbol, "tf": tf, "candle": completed})
            current = agg.current_candle()
            if current:
                self._emit({"type": "candle_update",
                            "symbol": symbol, "tf": tf, "candle": current})

    def _emit(self, data: dict):
        if not self._loop:
            return
        for cb in self._callbacks:
            self._loop.call_soon_threadsafe(
                lambda c=cb, d=data: asyncio.ensure_future(c(d))
            )

    def on_data(self, callback: Callable):
        self._callbacks.append(callback)
