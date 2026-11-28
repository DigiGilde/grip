"""Markdown setup for the standalone Personaboek."""

from __future__ import annotations

from collections.abc import Callable

from markdown_it import MarkdownIt
from markdown_it.token import Token


def new_markdown() -> MarkdownIt:
    """CommonMark with tables and without raw HTML."""
    return MarkdownIt("commonmark", {"html": False}).enable("table")


def shift_headings(tokens: list[Token], shift: int) -> None:
    if not shift:
        return
    for token in tokens:
        if token.type in ("heading_open", "heading_close"):
            token.tag = f"h{min(int(token.tag[1]) + shift, 6)}"


def rewrite_targets(
    tokens: list[Token],
    link: Callable[[str], str | None],
    image: Callable[[str], str | None],
) -> None:
    """Rewrite every link and image target in the inline content.

    ``None`` from ``link`` turns the link into a plain ``span``; ``None`` from
    ``image`` replaces the image by its alt text.
    """
    for inline in tokens:
        if inline.type != "inline" or not inline.children:
            continue
        out: list[Token] = []
        plain = False
        for child in inline.children:
            if child.type == "link_open":
                target = link(str(child.attrGet("href") or ""))
                if target is None:
                    plain = True
                    child.tag = "span"
                    child.attrs = {}
                else:
                    child.attrSet("href", target)
            elif child.type == "link_close" and plain:
                plain = False
                child.tag = "span"
            elif child.type == "image":
                target = image(str(child.attrGet("src") or ""))
                if target is None:
                    text = Token("text", "", 0)
                    text.content = child.content
                    child = text
                else:
                    child.attrSet("src", target)
            out.append(child)
        inline.children = out
