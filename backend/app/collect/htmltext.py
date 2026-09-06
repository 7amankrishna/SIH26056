"""Minimal, dependency-free HTML text extraction.

Only what a fare page needs: pull the text of elements matched by a tiny
selector subset (``tag``, ``.class``, ``#id``, ``tag.class``). Implemented on
top of :mod:`html.parser` so the collection engine adds no new runtime
dependency (important: the Vercel build stays a pure-ASGI function).
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Iterable


class _Node:
    __slots__ = ("tag", "attrs", "children", "text_parts")

    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: list["_Node"] = []
        self.text_parts: list[str] = []

    @property
    def text(self) -> str:
        parts = list(self.text_parts)
        for c in self.children:
            parts.append(c.text)
        return " ".join(" ".join(parts).split())


class _TreeBuilder(HTMLParser):
    VOID = {"br", "hr", "img", "input", "meta", "link", "source", "area", "base", "col"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#document", {})
        self.stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_parts.append(data.strip())


def _matches(node: _Node, selector: str) -> bool:
    sel = selector.strip()
    tag: str | None = None
    cls: str | None = None
    node_id: str | None = None
    buf = ""
    mode = "tag"
    for ch in sel:
        if ch in ".#":
            if mode == "tag":
                tag = buf or None
            elif mode == "class":
                cls = buf or cls
            buf = ""
            mode = "class" if ch == "." else "id"
            continue
        buf += ch
    if mode == "tag":
        tag = buf or None
    elif mode == "class" and buf:
        cls = buf
    elif mode == "id" and buf:
        node_id = buf

    if tag and node.tag != tag:
        return False
    if node_id and node.attrs.get("id") != node_id:
        return False
    if cls and cls not in node.attrs.get("class", "").split():
        return False
    return bool(tag or cls or node_id)


def walk(nodes: Iterable[_Node]):
    stack = list(nodes)
    while stack:
        n = stack.pop(0)
        yield n
        stack = list(n.children) + stack


def select(html: str, selector: str) -> list[str]:
    """Return the trimmed text content of every element matching ``selector``."""
    parser = _TreeBuilder()
    try:
        parser.feed(html)
    except Exception:  # malformed markup: degrade, don't crash the sweep
        return []
    return [n.text for n in walk([parser.root]) if n.tag != "#document" and _matches(n, selector)]


def select_first(html: str, selector: str) -> str | None:
    found = select(html, selector)
    return found[0] if found else None
