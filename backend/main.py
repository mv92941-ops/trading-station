"""
交易工作站後端 — FastAPI
本機啟動：uvicorn main:app --host localhost --port 8000 --reload
雲端啟動：由 Railway 自動注入 PORT 環境變數
"""

import asyncio
import json
import os
import platform
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from news import fetch_news
from yuanta import YuantaAPI
from youtube import YouTubeAuth
from history import get_history

# ── 設定（本機用 config.json，雲端用環境變數）────────────────────────
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

if CONFIG_FILE.exists():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
else:
    config = {
        "youtube": {
            "client_id":     os.environ.get("YOUTUBE_CLIENT_ID", ""),
            "client_secret": os.environ.get("YOUTUBE_CLIENT_SECRET", ""),
            "playlist_id":   os.environ.get("YOUTUBE_PLAYLIST_ID", ""),
        },
        "yuanta":  {"account": "", "password": "", "ca_password": "", "futures_account": ""},
        "symbols": {"futures": "MXFPM1", "tsmc": "2330", "etf1": "00631L", "etf2": "00675L"},
        "server":  {"host": "0.0.0.0", "port": 8000},
    }

PORT = int(os.environ.get("PORT", config["server"].get("port", 8000)))
IS_WINDOWS = platform.system() == "Windows"

app = FastAPI(title="交易工作站")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

yuanta = YuantaAPI(config)
youtube = YouTubeAuth(config)


# ── WebSocket 管理 ────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


manager = ConnectionManager()


@app.on_event("startup")
async def startup():
    if IS_WINDOWS:
        yuanta.on_data(manager.broadcast)
        await yuanta.connect()
    else:
        print("[QAPI] 雲端環境 (非 Windows)，跳過元大 API", flush=True)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── YouTube OAuth ─────────────────────────────────────────────────
@app.get("/youtube/auth")
async def youtube_auth():
    return RedirectResponse(youtube.get_auth_url())


@app.get("/youtube/callback")
async def youtube_callback(code: str):
    youtube.exchange_code(code)
    return HTMLResponse(
        "<html><body style='background:#111;color:#0f0;font-family:sans-serif'>"
        "<h2 style='margin-top:80px;text-align:center'>YouTube 授權成功，請關閉此視窗</h2>"
        "<script>setTimeout(()=>window.close(),2000)</script></body></html>"
    )


@app.get("/youtube/status")
async def youtube_status():
    return JSONResponse({"authorized": youtube.is_authorized()})


@app.get("/youtube/playlist")
async def youtube_playlist():
    if not youtube.is_authorized():
        return JSONResponse({"error": "未授權"}, status_code=401)
    return JSONResponse(youtube.get_playlist_items())


# ── 即時/收盤報價 ─────────────────────────────────────────────────
@app.get("/prices")
async def prices_endpoint():
    import yfinance as yf
    import httpx
    from datetime import datetime, timezone, timedelta
    result = {}
    tw_now = datetime.now(timezone(timedelta(hours=8)))
    market_open  = tw_now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    market_close = tw_now.replace(hour=13, minute=30, second=0, microsecond=0)
    is_weekday   = tw_now.weekday() < 5
    intraday     = is_weekday and market_open <= tw_now <= market_close

    async with httpx.AsyncClient(timeout=10) as client:

        # ── 加權指數 (TAIEX) — yfinance ────────────────────────────
        try:
            ticker = yf.Ticker("^TWII")
            if intraday:
                df = ticker.history(period="1d", interval="1m")
                if df.empty:
                    df = ticker.history(period="5d", interval="1d")
            else:
                df = ticker.history(period="5d", interval="1d")
            if not df.empty:
                price = round(float(df["Close"].dropna().iloc[-1]), 2)
                result["TAIEX"] = price
                print(f"[Prices] TAIEX = {price}")
        except Exception as e:
            print(f"[Prices] TAIEX 抓取失敗: {e}")

        # ── 台積電 (2330) — TWSE 官方 API ──────────────────────────
        try:
            r = await client.get(
                "https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                params={"ex_ch": "tse_2330.tw", "json": "1", "delay": "0"},
                headers={"User-Agent": "Mozilla/5.0"}
            )
            data = r.json()
            item = data.get("msgArray", [{}])[0]
            # z = 成交價，y = 昨收（盤後或休市時 z 可能為 "-"）
            val = item.get("z", "-")
            if val in ("-", "", None):
                val = item.get("y", "-")
            if val not in ("-", "", None):
                result["2330"] = float(val)
                print(f"[Prices] 2330 = {result['2330']}")
        except Exception as e:
            print(f"[Prices] 2330 抓取失敗: {e}")

        # ── 微型台指 (WMXF) — TAIFEX OpenAPI，Contract = TMF ──────
        try:
            r = await client.get(
                "https://openapi.taifex.com.tw/v1/DailyMarketReportFut",
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            data = r.json()
            # TMF = 微型台指（每點10元），一般交易時段，取成交量最大近月
            tmf = [d for d in data
                   if d.get("Contract") == "TMF"
                   and d.get("TradingSession") == "一般"]
            if not tmf:
                tmf = [d for d in data if d.get("Contract") == "TMF"]
            if tmf:
                def vol(d):
                    v = str(d.get("Volume") or "0").replace(",", "")
                    try: return int(v)
                    except: return 0
                best = max(tmf, key=vol)
                val = str(best.get("Last") or "").replace(",", "").strip()
                if val and val not in ("-", ""):
                    price = float(val)
                    if price > 0:
                        result["WMXF"] = price
                        print(f"[Prices] WMXF(TMF) = {price}  date={best.get('Date')}")
        except Exception as e:
            print(f"[Prices] WMXF 抓取失敗: {e}")

    return JSONResponse(result)


# ── 歷史資料 ──────────────────────────────────────────────────────
@app.get("/history")
async def history_endpoint(symbol: str, tf: str):
    data = await get_history(symbol, tf)
    return JSONResponse(data)

# ── 財經新聞 ──────────────────────────────────────────────────────
@app.get("/news")
async def news_endpoint():
    items = await fetch_news()
    return JSONResponse(items)

# ── 恐貪指數 ──────────────────────────────────────────────────────
@app.get("/fng")
async def fng_endpoint():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://api.alternative.me/fng/?limit=30")
            data = r.json().get("data", [])
        if not data:
            return JSONResponse({"error": "no data"})
        now   = data[0]
        yest  = data[1] if len(data) > 1 else None
        week  = data[7] if len(data) > 7 else None
        month = data[29] if len(data) > 29 else None
        return JSONResponse({
            "value":      int(now["value"]),
            "label":      now["value_classification"],
            "yesterday":  int(yest["value"]) if yest else None,
            "last_week":  int(week["value"]) if week else None,
            "last_month": int(month["value"]) if month else None,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)})


# ── 前端靜態檔案（最後掛載，避免覆蓋 API 路由）────────────────────
FRONTEND = Path(__file__).parent.parent / "frontend"

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def serve_index():
    from fastapi.responses import FileResponse
    resp = FileResponse(str(FRONTEND / "index.html"), media_type="text/html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
