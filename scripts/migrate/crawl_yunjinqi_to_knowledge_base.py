#!/usr/bin/env python3
"""Crawl public yunjinqi.top articles and import them into a knowledge base.

The crawler is deliberately conservative: it stays on the configured host,
obeys ``robots.txt`` rules, makes one request at a time, and persists every
article to a JSONL manifest before the optional API import.  It is therefore
safe to resume a several-hundred-article import after a network interruption.

Examples:
    # Crawl up to 300 articles and save a reusable manifest only.
    python scripts/migrate/crawl_yunjinqi_to_knowledge_base.py --skip-import

    # Crawl and import into the local AI Chat knowledge base.
    AI_FOR_INVESTOR_TOKEN='...' python scripts/migrate/crawl_yunjinqi_to_knowledge_base.py

    # The source currently may use a locally untrusted certificate.  Only use
    # this explicit option after confirming the expected host and certificate.
    python scripts/migrate/crawl_yunjinqi_to_knowledge_base.py --insecure --skip-import
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree


USER_AGENT = "AIForInvestorKnowledgeBaseImporter/1.0 (+local operator)"
DEFAULT_BASE_URL = "https://yunjinqi.top/"
DEFAULT_KB_NAME = "云子量化文章库"
BLOCKED_PATH_PREFIXES = (
    "/author/",
    "/category/",
    "/feed",
    "/page/",
    "/search/",
    "/tag/",
    "/wp-admin",
    "/wp-json",
)
ASSET_SUFFIXES = (
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
    ".zip",
)
SKIPPED_TAGS = {"aside", "footer", "nav", "noscript", "script", "style", "svg"}


@dataclass(frozen=True)
class Article:
    """A source article persisted before it is imported into the API."""

    url: str
    title: str
    content: str
    crawled_at: str


class FetchError(RuntimeError):
    """Raised when an HTTP resource cannot be fetched."""


class PageParser(HTMLParser):
    """Extract canonical links, page title, and readable article text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.article_parts: list[str] = []
        self._ignored_depth = 0
        self._article_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        attributes = dict(attrs)
        if normalized in SKIPPED_TAGS:
            self._ignored_depth += 1
        if normalized == "article":
            self._article_depth += 1
        if normalized == "title":
            self._in_title = True
        if normalized == "a":
            href = attributes.get("href")
            if href:
                self.links.add(href)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "title":
            self._in_title = False
        if normalized == "article" and self._article_depth:
            self._article_depth -= 1
        if normalized in SKIPPED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        if self._ignored_depth:
            return
        self.body_parts.append(text)
        if self._article_depth:
            self.article_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        parts = self.article_parts or self.body_parts
        return _normalize_text("\n\n".join(parts))


class HttpClient:
    """Small stdlib client with a single explicit TLS policy."""

    def __init__(self, *, verify_tls: bool, timeout: float, source_delay_seconds: float) -> None:
        self.timeout = timeout
        self.source_delay_seconds = source_delay_seconds
        self._last_source_request_at = 0.0
        self.context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        elapsed = time.monotonic() - self._last_source_request_at
        if elapsed < self.source_delay_seconds:
            time.sleep(self.source_delay_seconds - elapsed)
        self._last_source_request_at = time.monotonic()
        request_headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.1"}
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout, context=self.context) as response:
                payload = response.read()
                content_type = response.headers.get_content_charset() or "utf-8"
        except HTTPError as exc:
            raise FetchError(f"HTTP {exc.code} for {url}") from exc
        except (URLError, TimeoutError, ssl.SSLError) as exc:
            raise FetchError(f"Could not fetch {url}: {exc}") from exc
        return payload.decode(content_type, errors="replace")

    def post_json(self, url: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
        return self._json_request(url, "POST", payload, token)

    def get_json(self, url: str, token: str) -> dict[str, Any]:
        return self._json_request(url, "GET", None, token)

    def get_public_json(self, url: str) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_source_request_at
        if elapsed < self.source_delay_seconds:
            time.sleep(self.source_delay_seconds - elapsed)
        self._last_source_request_at = time.monotonic()
        request = Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout, context=self.context) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise FetchError(f"HTTP {exc.code} for {url}") from exc
        except (URLError, TimeoutError, ssl.SSLError) as exc:
            raise FetchError(f"Could not fetch {url}: {exc}") from exc
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise FetchError(f"Public endpoint {url} did not return JSON") from exc
        if not isinstance(parsed, dict):
            raise FetchError(f"Public endpoint {url} returned an unexpected payload")
        return parsed

    def _json_request(
        self,
        url: str,
        method: str,
        payload: dict[str, Any] | None,
        token: str,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=body,
            method=method,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout, context=self.context) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FetchError(f"API {method} {url} failed with HTTP {exc.code}: {detail[:500]}") from exc
        except (URLError, TimeoutError, ssl.SSLError) as exc:
            raise FetchError(f"Could not call API {url}: {exc}") from exc
        try:
            parsed = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise FetchError(f"API {method} {url} did not return JSON") from exc
        if not isinstance(parsed, dict):
            raise FetchError(f"API {method} {url} returned an unexpected payload")
        return parsed


class RobotsPolicy:
    """A compact robots.txt evaluator for our single crawler user agent."""

    def __init__(self, text: str) -> None:
        self.disallow: list[str] = []
        self.delay_seconds: float | None = None
        active_for_us = False
        has_directive = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if has_directive:
                    active_for_us = False
                    has_directive = False
                agent = value.lower()
                active_for_us = agent in {"*", USER_AGENT.lower()}
                continue
            if not active_for_us:
                continue
            has_directive = True
            if key == "disallow" and value:
                self.disallow.append(value)
            elif key == "crawl-delay":
                try:
                    self.delay_seconds = max(0.0, float(value))
                except ValueError:
                    pass

    def allows(self, url: str) -> bool:
        path = urlsplit(url).path or "/"
        return not any(path.startswith(prefix) for prefix in self.disallow)


def _normalize_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def canonicalize_url(url: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, url)
    parts = urlsplit(absolute)
    base_parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or parts.netloc.lower() != base_parts.netloc.lower():
        return None
    normalized_path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))


def is_article_url(url: str, base_url: str) -> bool:
    parts = urlsplit(url)
    base_parts = urlsplit(base_url)
    if parts.netloc.lower() != base_parts.netloc.lower():
        return False
    path = (parts.path or "/").lower()
    if path == "/" or path.startswith(BLOCKED_PATH_PREFIXES):
        return False
    return not path.endswith(ASSET_SUFFIXES)


def parse_sitemap_locations(xml_text: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    return [element.text.strip() for element in root.iter() if element.tag.endswith("loc") and element.text]


def discover_sitemap_urls(client: HttpClient, base_url: str, policy: RobotsPolicy) -> list[str]:
    """Return article URLs from common sitemap entry points without crawling pages."""
    sitemap_queue = deque(
        canonicalize_url(path, base_url)
        for path in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")
    )
    visited: set[str] = set()
    articles: list[str] = []
    while sitemap_queue:
        sitemap = sitemap_queue.popleft()
        if not sitemap or sitemap in visited or not policy.allows(sitemap):
            continue
        visited.add(sitemap)
        try:
            locations = parse_sitemap_locations(client.get_text(sitemap))
        except FetchError:
            continue
        for location in locations:
            normalized = canonicalize_url(location, base_url)
            if not normalized:
                continue
            if normalized.lower().endswith(".xml") or "sitemap" in normalized.lower():
                sitemap_queue.append(normalized)
            elif is_article_url(normalized, base_url):
                articles.append(normalized)
    return list(dict.fromkeys(articles))


def load_manifest(path: Path) -> dict[str, Article]:
    """Load prior successful crawl records, ignoring a partially written final line."""
    articles: dict[str, Article] = {}
    if not path.exists():
        return articles
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            article = Article(
                url=str(item["url"]),
                title=str(item["title"]),
                content=str(item["content"]),
                crawled_at=str(item["crawled_at"]),
            )
        except (KeyError, TypeError, json.JSONDecodeError):
            continue
        articles[article.url] = article
    return articles


def append_manifest(path: Path, article: Article) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(article), ensure_ascii=False) + "\n")


def crawl_public_article_api(
    client: HttpClient,
    *,
    base_url: str,
    policy: RobotsPolicy,
    max_articles: int,
    min_content_chars: int,
    max_content_chars: int,
    manifest_path: Path,
) -> list[Article] | None:
    """Use the site's public SPA article API when it is available.

    The API includes rendered article HTML, avoiding lossy browser emulation and
    giving the crawler a stable paginated route for several hundred articles.
    ``None`` means the public API is unavailable and lets the caller use the
    static sitemap/link fallback.
    """
    endpoint = canonicalize_url("/api/articles", base_url)
    if not endpoint or not policy.allows(endpoint):
        return None

    stored = load_manifest(manifest_path)
    page = 1
    page_size = min(100, max(10, max_articles))
    total_available: int | None = None
    while len(stored) < max_articles:
        query = urlencode({"page": page, "page_size": page_size})
        try:
            payload = client.get_public_json(f"{endpoint}?{query}")
        except FetchError as exc:
            if page == 1:
                print(f"public article API unavailable; using HTML fallback: {exc}", file=sys.stderr)
                return None
            break
        if payload.get("code") != 200 or not isinstance(payload.get("data"), list):
            if page == 1:
                print("public article API returned no usable article list; using HTML fallback", file=sys.stderr)
                return None
            break

        rows = payload["data"]
        raw_total = payload.get("total")
        if isinstance(raw_total, int):
            total_available = raw_total
        for row in rows:
            if not isinstance(row, dict):
                continue
            article_id = row.get("articleid")
            content_html = str(row.get("content") or "")
            if not article_id or not content_html:
                continue
            article_url = canonicalize_url(f"/article/{article_id}", base_url)
            if not article_url or article_url in stored:
                continue
            parser = PageParser()
            parser.feed(content_html)
            body = parser.text
            if len(body) < min_content_chars:
                continue
            title = str(row.get("headline") or parser.title or f"文章 {article_id}").strip()[:500]
            source_time = str(row.get("createtime") or "")
            content = (
                f"# {title}\n\n"
                f"来源：{article_url}\n"
                f"原文发布时间：{source_time or '未知'}\n"
                f"采集时间：{datetime.now(timezone.utc).isoformat()}\n\n"
                f"{body[:max_content_chars]}"
            )
            article = Article(
                url=article_url,
                title=title,
                content=content,
                crawled_at=datetime.now(timezone.utc).isoformat(),
            )
            stored[article.url] = article
            append_manifest(manifest_path, article)
            print(f"crawled {len(stored)}/{max_articles}: {title}")
            if len(stored) >= max_articles:
                break

        if not rows or len(rows) < page_size:
            break
        if total_available is not None and page * page_size >= total_available:
            break
        page += 1
    return list(stored.values())[:max_articles]


def crawl_articles(
    client: HttpClient,
    *,
    base_url: str,
    max_articles: int,
    min_content_chars: int,
    max_content_chars: int,
    delay_seconds: float,
    manifest_path: Path,
) -> list[Article]:
    """Crawl and persist public articles, returning the complete manifest set."""
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        policy = RobotsPolicy(client.get_text(robots_url, headers={"Accept": "text/plain"}))
    except FetchError as exc:
        raise FetchError(f"Cannot verify robots.txt at {robots_url}; refusing to crawl. {exc}") from exc

    effective_delay = max(delay_seconds, policy.delay_seconds or 0.0)
    client.source_delay_seconds = max(client.source_delay_seconds, effective_delay)

    api_articles = crawl_public_article_api(
        client,
        base_url=base_url,
        policy=policy,
        max_articles=max_articles,
        min_content_chars=min_content_chars,
        max_content_chars=max_content_chars,
        manifest_path=manifest_path,
    )
    if api_articles is not None:
        return api_articles

    stored = load_manifest(manifest_path)
    queue: deque[str] = deque()
    queued: set[str] = set()

    def enqueue(url: str) -> None:
        normalized = canonicalize_url(url, base_url)
        if not normalized or normalized in queued or normalized in stored:
            return
        if policy.allows(normalized) and is_article_url(normalized, base_url):
            queue.append(normalized)
            queued.add(normalized)

    for sitemap_url in discover_sitemap_urls(client, base_url, policy):
        enqueue(sitemap_url)

    # A sitemap is not guaranteed, so the homepage seeds normal link discovery.
    try:
        homepage = PageParser()
        homepage.feed(client.get_text(base_url))
        for link in homepage.links:
            enqueue(link)
    except FetchError as exc:
        if not queue:
            raise FetchError(f"Could not discover any article URLs. {exc}") from exc

    while queue and len(stored) < max_articles:
        url = queue.popleft()
        try:
            parser = PageParser()
            parser.feed(client.get_text(url))
        except FetchError as exc:
            print(f"skip {url}: {exc}", file=sys.stderr)
            continue

        for link in parser.links:
            enqueue(link)

        text = parser.text
        if len(text) >= min_content_chars:
            title = (parser.title or urlsplit(url).path.strip("/").replace("-", " ") or url)[:500]
            content = (
                f"# {title}\n\n"
                f"来源：{url}\n"
                f"采集时间：{datetime.now(timezone.utc).isoformat()}\n\n"
                f"{text[:max_content_chars]}"
            )
            article = Article(
                url=url,
                title=title,
                content=content,
                crawled_at=datetime.now(timezone.utc).isoformat(),
            )
            stored[url] = article
            append_manifest(manifest_path, article)
            print(f"crawled {len(stored)}/{max_articles}: {title}")

    return list(stored.values())[:max_articles]


def load_import_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(url): str(document_id) for url, document_id in payload.items()}


def save_import_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def ensure_knowledge_base(client: HttpClient, api_base: str, token: str, kb_name: str) -> str:
    query = urlencode({"limit": 100, "search": kb_name})
    listing = client.get_json(f"{api_base}/knowledge-base/?{query}", token)
    for item in listing.get("items", []):
        if isinstance(item, dict) and item.get("name") == kb_name and item.get("id"):
            return str(item["id"])
    created = client.post_json(
        f"{api_base}/knowledge-base/",
        {
            "name": kb_name,
            "description": "从 yunjinqi.top 采集的公开量化文章；每篇保留原始链接以便问答引用。",
            "is_public": True,
            "settings": {
                "retrieval_profile": "quant_research",
                "search_mode": "hybrid",
                "default_top_k": 8,
                "quant_focus": "strategy_research",
            },
        },
        token,
    )
    knowledge_base_id = created.get("id")
    if not knowledge_base_id:
        raise FetchError("Knowledge base creation did not return an id")
    return str(knowledge_base_id)


def import_articles(
    client: HttpClient,
    *,
    api_base: str,
    token: str,
    kb_name: str,
    articles: list[Article],
    import_state_path: Path,
) -> tuple[str, int]:
    """Create API documents and index them immediately for grounded chat."""
    knowledge_base_id = ensure_knowledge_base(client, api_base.rstrip("/"), token, kb_name)
    imported = load_import_state(import_state_path)
    created_count = 0
    for article in articles:
        if article.url in imported:
            continue
        document = client.post_json(
            f"{api_base.rstrip('/')}/knowledge-base/{knowledge_base_id}/documents/",
            {"title": article.title, "content": article.content, "content_type": "markdown"},
            token,
        )
        document_id = document.get("id")
        if not document_id:
            raise FetchError(f"Document creation did not return an id for {article.url}")
        client.post_json(
            f"{api_base.rstrip('/')}/rag/index",
            {"knowledge_base_id": knowledge_base_id, "document_id": str(document_id)},
            token,
        )
        imported[article.url] = str(document_id)
        save_import_state(import_state_path, imported)
        created_count += 1
        print(f"imported {created_count}/{len(articles)}: {article.title}")
    return knowledge_base_id, created_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--max-articles", type=int, default=300)
    parser.add_argument("--delay", type=float, default=1.0, help="Minimum seconds between source requests")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--min-content-chars", type=int, default=400)
    parser.add_argument("--max-content-chars", type=int, default=24000)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/imports/yunjinqi_articles.jsonl"),
        help="Append-only crawl manifest, reusable with --import-only",
    )
    parser.add_argument("--import-only", action="store_true", help="Do not crawl; import existing manifest")
    parser.add_argument("--skip-import", action="store_true", help="Crawl only; do not call the local API")
    parser.add_argument("--api-base", default="http://localhost:8000/api/v1")
    parser.add_argument("--token", default=os.getenv("AI_FOR_INVESTOR_TOKEN", ""))
    parser.add_argument("--kb-name", default=DEFAULT_KB_NAME)
    parser.add_argument("--import-state", type=Path, default=None)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate validation for the source/API; use only after manual verification",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_articles < 1:
        raise SystemExit("--max-articles must be at least 1")
    if args.delay < 0 or args.timeout <= 0:
        raise SystemExit("--delay must be non-negative and --timeout must be positive")
    if args.import_only and args.skip_import:
        raise SystemExit("--import-only and --skip-import cannot be used together")
    if not args.skip_import and not args.token:
        raise SystemExit("Set AI_FOR_INVESTOR_TOKEN or pass --token before importing documents")
    if args.insecure:
        print("WARNING: TLS verification is disabled by --insecure.", file=sys.stderr)

    base_url = canonicalize_url(args.base_url, args.base_url)
    if not base_url:
        raise SystemExit("--base-url must be an absolute http(s) URL")
    client = HttpClient(
        verify_tls=not args.insecure,
        timeout=args.timeout,
        source_delay_seconds=args.delay,
    )
    try:
        articles = (
            list(load_manifest(args.manifest).values())[: args.max_articles]
            if args.import_only
            else crawl_articles(
                client,
                base_url=base_url,
                max_articles=args.max_articles,
                min_content_chars=args.min_content_chars,
                max_content_chars=args.max_content_chars,
                delay_seconds=args.delay,
                manifest_path=args.manifest,
            )
        )
        if not articles:
            raise FetchError("No article content was collected; nothing to import")
        print(f"ready: {len(articles)} article(s) in {args.manifest}")
        if args.skip_import:
            return 0
        import_state = args.import_state or args.manifest.with_suffix(".import-state.json")
        knowledge_base_id, created = import_articles(
            client,
            api_base=args.api_base,
            token=args.token,
            kb_name=args.kb_name,
            articles=articles,
            import_state_path=import_state,
        )
        print(f"knowledge base {knowledge_base_id}: imported {created} new article(s)")
        return 0
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
