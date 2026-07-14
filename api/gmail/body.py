"""Extract a readable body from a Gmail message's MIME payload (format=full).

Fetched lazily, on-demand, only when a user actually opens a thread (see
routes/threads.py) - never during sync, which stays metadata-only for
cost/latency. Cached into messages_lite.body_html/body_text/body_fetched
afterward.

Gmail (like virtually all mail) has no special markup format - a message is
just MIME, usually a multipart/alternative with a text/html part (what Gmail's
own web client renders) and a text/plain fallback. We keep the sanitized HTML
so the frontend can render it faithfully (in a sandboxed iframe) instead of
flattening it to plain text."""

import base64

import nh3

_ALLOWED_TAGS = {
    "a", "b", "strong", "i", "em", "u", "s", "strike", "br", "p", "div", "span",
    "ul", "ol", "li", "blockquote", "pre", "code", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "img", "font", "center", "small", "sub", "sup",
}
_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height"},
    "font": {"color", "size", "face"},
    "td": {"colspan", "rowspan", "align", "valign"},
    "th": {"colspan", "rowspan", "align", "valign"},
    "table": {"border", "cellpadding", "cellspacing"},
    "*": {"style"},
}


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _sanitize_html(html: str) -> str:
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )


def extract_body(payload: dict) -> dict:
    """Walk a Gmail message payload's MIME tree, returning both a sanitized
    HTML rendering (preferred, matches what Gmail itself shows) and a plain
    text fallback. Either value may be None if that part wasn't present."""
    plain: str | None = None
    html: str | None = None

    def walk(part: dict) -> None:
        nonlocal plain, html
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if mime == "text/plain" and data and plain is None:
            plain = _decode(data)
        elif mime == "text/html" and data and html is None:
            html = _decode(data)
        for sub_part in part.get("parts") or []:
            walk(sub_part)

    walk(payload)
    return {
        "html": _sanitize_html(html) if html else None,
        "text": plain.strip() if plain else None,
    }
