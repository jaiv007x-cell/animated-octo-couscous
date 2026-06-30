from __future__ import annotations
from bs4 import BeautifulSoup
import re


def clean_text(html_or_text: str) -> str:
    soup = BeautifulSoup(html_or_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def extract_links(base_url: str, html: str) -> list[dict[str, str]]:
    from urllib.parse import urljoin
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for a in soup.find_all("a"):
        href = a.get("href")
        label = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if not href or not label:
            continue
        rows.append({"title": label[:250], "url": urljoin(base_url, href)})
    return rows


def compact_snippet(text: str, max_chars: int = 600) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars] + ("..." if len(text) > max_chars else "")
