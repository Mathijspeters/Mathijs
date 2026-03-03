"""
Daily Trend Tracker
===================
Fetches trending stocks and crypto currencies from:
  - CoinGecko  (no API key required)
  - Yahoo Finance trending tickers
  - NewsAPI    (requires NEWS_API_KEY secret)

Then sends a formatted Markdown report to a Telegram chat/group
via the Telegram Bot API (requires TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID secrets).

Required GitHub Actions secrets
--------------------------------
TELEGRAM_BOT_TOKEN  – token obtained from @BotFather
TELEGRAM_CHAT_ID    – numeric chat/group/channel ID
NEWS_API_KEY        – key from https://newsapi.org/ (free tier is fine)
"""

from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")
NEWS_API_KEY: str = os.environ.get("NEWS_API_KEY", "")

COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
YAHOO_TRENDING_URL = "https://query1.finance.yahoo.com/v1/finance/trending/US"
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"

REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_trending_crypto() -> list[dict[str, Any]]:
    """Return a list of trending coins from CoinGecko (top 7)."""
    try:
        response = requests.get(COINGECKO_TRENDING_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        coins = data.get("coins", [])
        return [
            {
                "name": c["item"]["name"],
                "symbol": c["item"]["symbol"].upper(),
                "market_cap_rank": c["item"].get("market_cap_rank", "N/A"),
            }
            for c in coins[:7]
        ]
    except Exception as exc:
        print(f"[WARNING] Could not fetch crypto trends: {exc}", file=sys.stderr)
        return []


def fetch_trending_stocks() -> list[str]:
    """Return a list of trending stock tickers from Yahoo Finance (top 10)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(
            YAHOO_TRENDING_URL,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        quotes = (
            data.get("finance", {})
            .get("result", [{}])[0]
            .get("quotes", [])
        )
        return [q["symbol"] for q in quotes[:10] if "symbol" in q]
    except Exception as exc:
        print(f"[WARNING] Could not fetch stock trends: {exc}", file=sys.stderr)
        return []


def fetch_financial_news(max_articles: int = 5) -> list[dict[str, str]]:
    """Return top financial news headlines from NewsAPI."""
    if not NEWS_API_KEY:
        print("[INFO] NEWS_API_KEY not set; skipping news headlines.", file=sys.stderr)
        return []
    try:
        params = {
            "apiKey": NEWS_API_KEY,
            "category": "business",
            "language": "en",
            "pageSize": max_articles,
        }
        response = requests.get(NEWS_API_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        articles = response.json().get("articles", [])
        return [
            {
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", ""),
            }
            for a in articles[:max_articles]
        ]
    except Exception as exc:
        print(f"[WARNING] Could not fetch news: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

# The report is intentionally written in Dutch, matching the language of the
# project requirements.

# MarkdownV2 requires these characters to be escaped with a backslash.
_MDV2_SPECIAL = r"\_*[]()~`>#+-=|{}.!"


def _escape_mdv2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    for ch in _MDV2_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text


def build_report(
    crypto: list[dict[str, Any]],
    stocks: list[str],
    news: list[dict[str, str]],
) -> str:
    """Build a Telegram-flavoured Markdown report."""
    today = date.today().strftime("%d %B %Y")
    lines: list[str] = [
        f"📊 *Dagelijkse Trend Tracker* — {today}",
        "",
    ]

    # --- Crypto ---
    lines.append("🪙 *Trending Crypto*")
    if crypto:
        for coin in crypto:
            rank = coin["market_cap_rank"]
            rank_str = f"\\#{rank}" if isinstance(rank, int) else str(rank)
            lines.append(
                f"  • {coin['name']} \\({coin['symbol']}\\)"
                f" — marktkapitalisatie rang {rank_str}"
            )
    else:
        lines.append("  _Geen data beschikbaar_")
    lines.append("")

    # --- Stocks ---
    lines.append("📈 *Trending Aandelen \\(VS\\)*")
    if stocks:
        lines.append("  " + " · ".join(stocks))
    else:
        lines.append("  _Geen data beschikbaar_")
    lines.append("")

    # --- News ---
    if news:
        lines.append("📰 *Financieel Nieuws*")
        for article in news:
            title = _escape_mdv2(article["title"])
            source = article["source"]
            url = article["url"]
            lines.append(f"  • [{title}]({url}) _— {source}_")
        lines.append("")

    lines.append("_Gegenereerd door de Daily Trend Tracker workflow_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram delivery
# ---------------------------------------------------------------------------


def send_telegram_message(text: str) -> None:
    """Send *text* to the configured Telegram chat using MarkdownV2."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "[ERROR] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    if not response.ok:
        print(
            f"[ERROR] Telegram API error {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    print("[INFO] Report successfully sent to Telegram.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("[INFO] Fetching trending crypto…")
    crypto = fetch_trending_crypto()

    print("[INFO] Fetching trending stocks…")
    stocks = fetch_trending_stocks()

    print("[INFO] Fetching financial news…")
    news = fetch_financial_news()

    report = build_report(crypto, stocks, news)
    print("[INFO] Report preview:\n")
    print(report)
    print()

    send_telegram_message(report)


if __name__ == "__main__":
    main()
