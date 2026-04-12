# 元大行情API (QAPI) 橋接程式
# 必須用 Python 3.9 32-bit 執行：
#   Python39-32\python.exe qapi_bridge.py
# 透過 stdout 以 JSON Lines 格式輸出行情資料給主後端

import sys
import json
import pathlib

import wx
import wx.lib.activex as activex

# ── 讀取設定 ─────────────────────────────────────────────────
CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.json"
cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

ACCOUNT  = cfg["yuanta"]["account"]   # 股票帳號 981-0433816
PASSWORD = cfg["yuanta"]["password"]
SERVER   = "203.66.93.84"             # 直接用 IP，排除 DNS 問題
PORT     = "80"

SYMBOLS = [
    cfg["symbols"]["futures"],   # MXFPM1
    cfg["symbols"]["tsmc"],      # 2330
    cfg["symbols"]["etf1"],      # 00631L
    cfg["symbols"]["etf2"],      # 00675L
]


def emit(data: dict):
    print(json.dumps(data, ensure_ascii=False), flush=True)


# ── QAPI ActiveX 控制項（事件方法直接定義在此）───────────────
class QAPICtrl(activex.ActiveXCtrl):
    """
    繼承 ActiveXCtrl，事件方法直接定義在類別內。
    呼叫 API 方法透過 self.ctrl（即內部 COM IDispatch）。
    """

    def __init__(self, parent):
        super().__init__(
            parent,                              # parent frame
            "YuantaQuote.YuantaQuoteCtrl.1",    # ProgID（第二個參數）
            -1,                                  # wxid
            size=(1, 1),
        )

    def login(self):
        emit({"type": "log",
              "msg": f"SetMktLogon {ACCOUNT} → {SERVER}:{PORT}"})
        self.ctrl.SetMktLogon(ACCOUNT, PASSWORD, SERVER, PORT, 0, 0)
        # 30 秒後若無回應則警告
        import threading
        def _timeout():
            import time; time.sleep(30)
            emit({"type": "log", "msg": "[警告] 30秒無回應，可能帳號/密碼/IP/Port有誤或非交易時間"})
        threading.Thread(target=_timeout, daemon=True).start()

    # ── 事件 ─────────────────────────────────────────────────
    def OnMktStatusChange(self, Status, Msg, ReqType):
        emit({"type": "status", "status": Status, "msg": str(Msg)})
        if Status == 1:
            emit({"type": "log", "msg": "連線成功，訂閱行情..."})
            for sym in SYMBOLS:
                r = self.ctrl.AddMktReg(sym, "A", 0, 0)
                emit({"type": "log", "msg": f"訂閱 {sym} → {r}"})

    def OnRegError(self, symbol, updmode, ErrCode, ReqType):
        emit({"type": "error", "symbol": str(symbol),
              "code": ErrCode, "msg": "訂閱失敗"})

    def OnGetMktAll(self, symbol, RefPri, OpenPri, HighPri, LowPri,
                    UpPri, DnPri, MatchTime, MatchPri, MatchQty,
                    TolMatchQty, BestBuyQty, BestBuyPri,
                    BestSellQty, BestSellPri,
                    FDBPri, FDBQty, FDSPri, FDSQty, ReqType):
        emit({
            "type":   "mkt",
            "symbol": str(symbol).strip(),
            "time":   str(MatchTime).strip(),
            "price":  str(MatchPri).strip(),
            "open":   str(OpenPri).strip(),
            "high":   str(HighPri).strip(),
            "low":    str(LowPri).strip(),
            "qty":    str(MatchQty).strip(),
            "vol":    str(TolMatchQty).strip(),
            "ref":    str(RefPri).strip(),
            "buy":    str(BestBuyPri).strip(),
            "sell":   str(BestSellPri).strip(),
        })

    def OnGetTickData(self, strSymbol, strTickSn, strMatchTime,
                      strBuyPri, strSellPri, strMatchPri,
                      strMatchQty, strTolMatQty,
                      strMatchAmt, strTolMatAmt, ReqType):
        emit({
            "type":   "tick",
            "symbol": str(strSymbol).strip(),
            "time":   str(strMatchTime).strip(),
            "price":  str(strMatchPri).strip(),
            "qty":    str(strMatchQty).strip(),
            "buy":    str(strBuyPri).strip(),
            "sell":   str(strSellPri).strip(),
            "vol":    str(strTolMatQty).strip(),
        })

    def OnTickRegError(self, strSymbol, lMode, lErrCode, ReqType):
        emit({"type": "error", "symbol": str(strSymbol),
              "code": lErrCode, "msg": f"Tick訂閱失敗 mode={lMode}"})

    # 其餘事件暫不使用
    def OnGetMktQuote(self, *a): pass
    def OnGetMktData(self, *a): pass
    def OnGetDelayClose(self, *a): pass
    def OnGetBreakResume(self, *a): pass
    def OnGetTradeStatus(self, *a): pass
    def OnGetTimePack(self, *a): pass
    def OnGetDelayOpen(self, *a): pass
    def OnGetFutStatus(self, *a): pass
    def OnTickRangeDataError(self, *a): pass
    def OnGetTickRangeData(self, *a): pass


# ── 容器視窗（隱藏）─────────────────────────────────────────
class QAPIFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="QAPI", size=(1, 1),
                         style=wx.FRAME_NO_TASKBAR)
        self.Hide()
        self.qapi = QAPICtrl(self)
        # 連線後才登入（等 frame 完全初始化）
        wx.CallAfter(self.qapi.login)


def main():
    emit({"type": "log",
          "msg": f"QAPI橋接啟動 帳號={ACCOUNT} 伺服器={SERVER}:{PORT}"})

    app   = wx.App(False)
    frame = QAPIFrame()
    app.MainLoop()


if __name__ == "__main__":
    main()
