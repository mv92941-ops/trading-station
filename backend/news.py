"""
即時財經新聞
"""

import feedparser
import httpx

RSS_SOURCES = [
    ("經濟日報", "https://money.udn.com/rssfeed/news/1001/5591?ch=money", True),
    ("MoneyDJ",  "https://www.moneydj.com/MOOC/rss/",                    False),  # SSL 憑證有誤，略過驗證
    ("鉅亨網",   "https://news.cnyes.com/rss/tw/stock",                   True),
]


async def fetch_news(limit: int = 30) -> list:
    results = []
    per_source = max(1, limit // len(RSS_SOURCES))
    for source, url, verify_ssl in RSS_SOURCES:
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True,
                                         verify=verify_ssl) as client:
                resp = await client.get(url)
            feed = feedparser.parse(resp.text)
            for entry in feed.entries[:per_source]:
                results.append({
                    "source":    source,
                    "title":     entry.get("title", ""),
                    "link":      entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"[News] {source} 抓取失敗: {e}")
    return results
