"""Build a weekly markdown digest of AI, agents and automation news from RSS/Atom feeds.

Standard library only, so the GitHub Action needs no ``pip install``.

    python digest.py                 # last 7 days, writes digests/<date>.md and refreshes README
    python digest.py --days 3 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
USER_AGENT = "ai-news-digest/1.0 (+https://github.com/AmeesAnsari/ai-news-digest)"
ATOM = "{http://www.w3.org/2005/Atom}"
README_START, README_END = "<!-- latest:start -->", "<!-- latest:end -->"

# Topic -> keywords (matched as whole words, case-insensitive, in title + summary).
TOPICS: Dict[str, Sequence[str]] = {
    "Agents": ["agent", "agents", "agentic", "mcp", "model context protocol", "tool use", "function calling", "multi-agent"],
    "Automation": ["automation", "automate", "workflow", "workflows", "rpa", "orchestration", "copilot"],
    "Models": ["llm", "llms", "model", "models", "gpt", "claude", "gemini", "llama", "reasoning", "fine-tuning", "open-weight"],
    "Safety & security": ["safety", "security", "jailbreak", "prompt injection", "alignment", "guardrail", "guardrails", "red team", "privacy"],
    "Infrastructure": ["inference", "gpu", "gpus", "kubernetes", "serving", "latency", "datacenter", "data center", "chips"],
    "Retrieval & data": ["rag", "retrieval", "embedding", "embeddings", "vector", "search", "knowledge graph"],
}


@dataclass
class Item:
    title: str
    link: str
    source: str
    published: datetime
    summary: str = ""
    topics: List[str] = field(default_factory=list)


# ---------------------------------------------------------------- parsing


def clean_text(raw: Optional[str], limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)  # RSS: "Tue, 11 Nov 2026 09:00:00 GMT"
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))  # Atom: "2026-11-11T09:00:00Z"
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_feed(xml_bytes: bytes, source: str) -> List[Item]:
    """Parse RSS 2.0 or Atom into items; entries without a usable date are skipped."""
    root = ET.fromstring(xml_bytes)
    items: List[Item] = []

    for node in root.iter("item"):  # RSS
        published = parse_date(node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date"))
        title, link = clean_text(node.findtext("title"), 200), (node.findtext("link") or "").strip()
        if published and title and link:
            items.append(Item(title, link, source, published, clean_text(node.findtext("description"))))

    for node in root.iter(f"{ATOM}entry"):  # Atom
        published = parse_date(node.findtext(f"{ATOM}published") or node.findtext(f"{ATOM}updated"))
        # Explicit None check: an Element with no children is falsy, so `a or b` would skip a valid link.
        link_el = node.find(f"{ATOM}link[@rel='alternate']")
        if link_el is None:
            link_el = node.find(f"{ATOM}link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        title = clean_text(node.findtext(f"{ATOM}title"), 200)
        summary = node.findtext(f"{ATOM}summary") or node.findtext(f"{ATOM}content")
        if published and title and link:
            items.append(Item(title, link, source, published, clean_text(summary)))

    return items


# ---------------------------------------------------------------- selection


def tag(item: Item) -> List[str]:
    haystack = f"{item.title} {item.summary}".lower()
    return [topic for topic, words in TOPICS.items() if any(re.search(rf"\b{re.escape(w)}\b", haystack) for w in words)]


def normalise_link(link: str) -> str:
    return re.sub(r"[?#].*$", "", link).rstrip("/").lower()


def select(items: Sequence[Item], since: datetime, per_source: int) -> List[Item]:
    """Keep recent, on-topic, de-duplicated items, at most ``per_source`` per feed, newest first."""
    seen, picked, counts = set(), [], {}
    for item in sorted(items, key=lambda i: i.published, reverse=True):
        if item.published < since:
            continue
        key = normalise_link(item.link)
        if key in seen:
            continue
        item.topics = tag(item)
        if not item.topics or counts.get(item.source, 0) >= per_source:
            continue
        seen.add(key)
        counts[item.source] = counts.get(item.source, 0) + 1
        picked.append(item)
    return picked


# ---------------------------------------------------------------- output


def render(items: Sequence[Item], start: datetime, end: datetime, sources_ok: int, sources_total: int) -> str:
    lines = [
        f"# AI & automation digest · {start:%d %b} – {end:%d %b %Y}",
        "",
        f"{len(items)} stories from {sources_ok} of {sources_total} feeds, grouped by topic. "
        "A story can appear under its first matching topic only.",
        "",
    ]
    if not items:
        lines.append("_No matching stories this week._")
    placed = set()
    for topic in TOPICS:
        group = [i for i in items if i.topics and i.topics[0] == topic and i.link not in placed]
        if not group:
            continue
        lines += [f"## {topic}", ""]
        for i in group:
            placed.add(i.link)
            lines.append(f"- **[{i.title}]({i.link})** · {i.source}, {i.published:%d %b}")
            if i.summary:
                lines.append(f"  {i.summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def update_readme(readme: Path, digest_name: str, items: Sequence[Item], end: datetime, top: int = 5) -> None:
    # Feature stories in topic order (Agents first), one per source, so a busy feed can't fill the block.
    order = list(TOPICS)
    featured, sources = [], set()
    for i in sorted(items, key=lambda i: (order.index(i.topics[0]) if i.topics else len(order), -i.published.timestamp())):
        if i.source not in sources:
            featured.append(i)
            sources.add(i.source)
    block = [README_START, f"**Latest: [{end:%d %b %Y}](digests/{digest_name})**", ""]
    block += [f"- [{i.title}]({i.link}) · {i.source}" for i in featured[:top]] or ["_No matching stories this week._"]
    block.append(README_END)
    text = readme.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.S)
    readme.write_text(pattern.sub(lambda _: "\n".join(block), text), encoding="utf-8")


# ---------------------------------------------------------------- fetching


def fetch(feed: Dict[str, str], timeout: int = 20) -> List[Item]:
    request = urllib.request.Request(feed["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_feed(response.read(), feed["name"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-source", type=int, default=4, help="max stories per feed")
    parser.add_argument("--feeds", type=Path, default=ROOT / "feeds.json")
    parser.add_argument("--dry-run", action="store_true", help="print the digest instead of writing files")
    args = parser.parse_args(argv)

    feeds = json.loads(args.feeds.read_text(encoding="utf-8"))
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    all_items: List[Item] = []
    ok = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for feed, result in zip(feeds, pool.map(lambda f: _safe_fetch(f), feeds)):
            if result is None:
                continue
            ok += 1
            all_items.extend(result)

    if ok == 0:
        print("error: every feed failed; not writing an empty digest", file=sys.stderr)
        return 1

    items = select(all_items, start, args.per_source)
    digest = render(items, start, end, ok, len(feeds))

    if args.dry_run:
        print(digest)
        return 0

    name = f"{end:%Y-%m-%d}.md"
    (ROOT / "digests").mkdir(exist_ok=True)
    (ROOT / "digests" / name).write_text(digest, encoding="utf-8")
    update_readme(ROOT / "README.md", name, items, end)
    print(f"wrote digests/{name}: {len(items)} stories from {ok}/{len(feeds)} feeds")
    return 0


def _safe_fetch(feed: Dict[str, str]) -> Optional[List[Item]]:
    try:
        return fetch(feed)
    except Exception as exc:  # one broken feed must not sink the digest
        print(f"warning: {feed['name']}: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    sys.exit(main())
