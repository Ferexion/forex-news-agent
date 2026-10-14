
import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
from html import unescape

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = "seen.json"

query = (
    "forex OR Federal Reserve OR ECB OR interest rates "
    "OR inflation OR NFP OR central bank"
)
feed_url = (
    "https://news.google.com/rss/search?q="
    + urllib.parse.quote(query)
    + "&hl=en-US&gl=US&ceid=US:en"
)

def get_feed():
    request = urllib.request.Request(
        feed_url,
        headers={"User-Agent": "ForexNewsMonitor/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return ET.fromstring(response.read())

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode()
    request = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read())
        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the message")

def classify(title):
    t = title.lower()
    if any(x in t for x in [
        "federal reserve", "fed rate", "fomc", "powell"
    ]):
        return "USD / FED"
    if any(x in t for x in [
        "ecb", "european central bank", "euro zone"
    ]):
        return "EUR / ECB"
    if any(x in t for x in [
        "bank of england", "boe", "british pound"
    ]):
        return "GBP / BOE"
    if any(x in t for x in [
        "inflation", "cpi", "pce", "nfp",
        "unemployment", "payrolls", "interest rate"
    ]):
        return "HIGH-INTEREST ECONOMIC NEWS"
    return "FOREX / ECONOMY"

def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def main():
    root = get_feed()
    items = root.findall("./channel/item")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    seen = load_seen()
    fresh = []

    for item in items:
        title = unescape(item.findtext("title", "Untitled"))
        link = item.findtext("link", "")
        guid = item.findtext("guid", "") or link or title
        pub = item.findtext("pubDate", "")

        try:
            published = parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue

        if published < cutoff or guid in seen:
            continue

        fresh.append((published, guid, title, link))

    fresh.sort(reverse=True, key=lambda x: x[0])

    # On first run, send only the three newest recent stories.
    if not os.path.exists(STATE_FILE):
        fresh = fresh[:3]

    for published, guid, title, link in fresh:
        message = (
            f"📰 FOREX NEWS ALERT\n\n"
            f"Topic: {classify(title)}\n"
            f"Headline: {title}\n"
            f"Published: {published:%Y-%m-%d %H:%M UTC}\n\n"
            f"Source: Google News\n"
            f"{link}\n\n"
            "⚠️ Headline classification only — "
            "not verified fundamental analysis or a trade signal."
        )
        send_telegram(message)
        seen.add(guid)

    # Remember recent stories to reduce duplicate alerts.
    all_ids = [item.findtext("guid", "") or item.findtext("link", "")
               or item.findtext("title", "")
               for item in items]
    seen.update(x for x in all_ids if x)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-500:], f)

    print(f"Sent {len(fresh)} news alert(s).")

if __name__ == "__main__":
    main()
