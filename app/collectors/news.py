from __future__ import annotations
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import hashlib
import re
from pathlib import Path
import feedparser
import requests
from dateutil import parser as dateparser
from sqlmodel import Session, select
from app.models import RawItem, SourceType
from app.settings import get_settings
from app.collectors.text import clean_text, compact_snippet


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def google_news_rss_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"


def news_queries(state_name: str) -> list[str]:
    return [
        f"{state_name} excise liquor latest when:7d",
        f"{state_name} liquor policy licence fee latest when:7d",
        f"{state_name} excise duty beer liquor tax latest when:7d",
        f"{state_name} excise minister commissioner liquor latest when:7d",
        f"{state_name} excise liquor licence fee notification",
        f"{state_name} excise notification liquor",
        f"{state_name} State Excise Department notification",
        f"{state_name} liquor licence auction excise",
        f"{state_name} low alcohol liquor policy beer duty excise",
        f'"{state_name}" excise liquor policy notification licence fee dry day permit commissioner transfer posting principal secretary managing director',
    ]


NEWS_KEYWORDS = {
    "alcohol",
    "bar",
    "bars",
    "beer",
    "brewery",
    "dry day",
    "excise",
    "licence",
    "license",
    "liquor",
    "permit",
    "pub",
    "toddy",
    "wine",
}


def is_excise_news_text(text: str) -> bool:
    haystack = f" {text.lower()} "
    return any(re.search(rf"\b{re.escape(keyword)}\b", haystack) for keyword in NEWS_KEYWORDS)


def collect_google_news(
    session: Session,
    state_code: str,
    state_name: str,
    max_items: int = 30,
    recent_days: int | None = None,
) -> list[RawItem]:
    settings = get_settings()
    Path(settings.doc_dir).mkdir(parents=True, exist_ok=True)
    created: list[RawItem] = []
    seen_links: set[str] = set()
    since = datetime.utcnow() - timedelta(days=recent_days) if recent_days else None
    for query in news_queries(state_name):
        try:
            response = requests.get(
                google_news_rss_url(query),
                headers={"User-Agent": "ExciseWatchBot/1.0"},
                timeout=12,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except requests.RequestException:
            continue
        for entry in feed.entries:
            if len(created) >= max_items:
                break
            title = clean_text(entry.get("title", ""))[:250]
            link = entry.get("link", "")
            if not title or not link or link in seen_links:
                continue
            seen_links.add(link)
            summary = clean_text(entry.get("summary", ""))
            if not is_excise_news_text(title):
                continue
            published = None
            if entry.get("published"):
                try:
                    published = dateparser.parse(entry.published).replace(tzinfo=None)
                except Exception:
                    published = None
            if since and published and published < since:
                continue
            digest = sha256(title + link + summary)
            if session.exec(select(RawItem).where(RawItem.content_hash == digest)).first():
                continue
            path = Path(settings.doc_dir) / f"news-{state_code.lower()}-{digest[:16]}.txt"
            path.write_text(f"{title}\n{link}\n{summary}", encoding="utf-8")
            item = RawItem(
                state_code=state_code,
                state_name=state_name,
                source_name="Google News RSS",
                source_type=SourceType.news,
                title=title,
                url=link,
                published_at=published,
                fetched_at=datetime.utcnow(),
                content_hash=digest,
                snippet=compact_snippet(summary),
                full_text_path=str(path),
            )
            session.add(item)
            created.append(item)
        if len(created) >= max_items:
            break
    session.commit()
    return created
