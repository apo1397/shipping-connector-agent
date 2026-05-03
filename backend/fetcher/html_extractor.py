"""Smart HTML → clean text extraction for API documentation sites.

Uses BeautifulSoup to isolate main content + html2text for clean markdown
conversion.  Falls back to a built-in stripper when optional deps are absent.
"""

from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)


def extract_clean_text(raw_html: str) -> str:
    """Full pipeline: raw HTML page → clean markdown text for LLM analysis."""
    content_html = _extract_main_content(raw_html)
    text = _to_markdown(content_html)
    logger.info(
        f"HTML extraction: {len(raw_html)} raw chars → {len(text)} clean chars"
    )
    return text


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_main_content(raw_html: str) -> str:
    """Strip nav/scripts/styles and return the main content HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")

        # Kill noise tags first
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "noscript", "svg", "iframe", "button", "form"]):
            tag.decompose()

        # Prefer semantic content containers
        content = (
            soup.find("article")
            or soup.find("main")
            or soup.find(id=re.compile(r"content|main|docs", re.I))
            or soup.find("body")
        )
        return str(content) if content else str(soup)

    except ImportError:
        logger.warning("BeautifulSoup not installed — using regex fallback")
        for tag in ("article", "main"):
            m = re.search(
                rf"<{tag}[^>]*>(.*?)</{tag}>", raw_html, re.DOTALL | re.IGNORECASE
            )
            if m:
                return m.group(0)
        return raw_html


def _to_markdown(html_fragment: str) -> str:
    """Convert HTML to clean markdown text."""
    try:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0
        h.ignore_tables = False
        return h.handle(html_fragment).strip()

    except ImportError:
        logger.warning("html2text not installed — using builtin stripper")
        return _builtin_strip(html_fragment)


def _builtin_strip(html: str) -> str:
    """Minimal HTML → text using only Python stdlib."""
    from html.parser import HTMLParser

    _SKIP = frozenset(["script", "style", "nav", "footer", "aside", "svg", "button"])

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.out: list[str] = []
            self._d = 0

        def handle_starttag(self, tag, attrs):
            if tag.lower() in _SKIP:
                self._d += 1

        def handle_endtag(self, tag):
            if tag.lower() in _SKIP and self._d:
                self._d -= 1

        def handle_data(self, data):
            if not self._d and data.strip():
                self.out.append(data.strip())

    p = _P()
    try:
        p.feed(html)
    except Exception:
        pass
    return "\n".join(p.out)
