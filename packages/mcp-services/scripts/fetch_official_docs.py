"""Download the official documents listed in knowledge/manifest.json and save them as Markdown.

The text is the official text, unedited: the script only strips page navigation and turns
HTML structure (headings, lists, tables, code) into Markdown so it can be chunked.

  python scripts/fetch_official_docs.py            # fetch every document
  python scripts/fetch_official_docs.py ESP_OTA    # fetch selected documents
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
MANIFEST = KNOWLEDGE_DIR / "manifest.json"

# Where the article body starts and ends on each site.
SITE_BOUNDS = {
    "espressif": ('<div itemprop="articleBody">', "<footer>"),
    "mosquitto": ('<div class="refentry"', "</article>"),
    "oasis": ("<body", "</body>"),
}
VOID = {"br", "img", "hr", "meta", "link", "input", "wbr", "col", "area", "base", "source"}
SKIPPED = {"script", "style", "nav", "noscript", "svg", "button", "form", "head"}
BLOCK = {"p", "div", "section", "dt", "dd", "blockquote", "caption", "figure", "dl", "ul", "ol"}


class MarkdownConverter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.inline: list[str] = []
        self.skip_depth = 0
        self.pre_depth = 0
        self.pre_text: list[str] = []
        self.list_depth = 0
        self.heading: int | None = None
        self.table: list[list[str]] | None = None
        self.cell: list[str] | None = None
        self.marker: str | None = None  # list bullet waiting for the item's first text

    # -- helpers -------------------------------------------------------------
    def flush(self, prefix: str = "") -> None:
        text = re.sub(r"\s+", " ", "".join(self.inline)).strip()
        self.inline = []
        if not text:
            return
        if self.marker is not None and not prefix:
            prefix, self.marker = self.marker, None
        self.blocks.append(prefix + text)

    def write(self, text: str) -> None:
        if self.cell is not None:
            self.cell.append(text)
        else:
            self.inline.append(text)

    # -- parser callbacks ----------------------------------------------------
    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if self.skip_depth:
            if tag not in VOID:
                self.skip_depth += 1
            return
        if tag in SKIPPED or "headerlink" in classes or attributes.get("aria-hidden") == "true":
            if tag not in VOID:
                self.skip_depth = 1
            return
        if self.pre_depth:
            if tag == "pre":
                self.pre_depth += 1
            elif tag == "br":
                self.pre_text.append("\n")
            return
        if tag == "pre":
            self.flush()
            self.pre_depth = 1
            self.pre_text = []
        elif re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading = int(tag[1])
        elif tag == "table":
            self.flush()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
        elif tag in ("ul", "ol"):
            self.flush()
            self.list_depth += 1
        elif tag == "li":
            self.flush()
            self.marker = "  " * max(self.list_depth - 1, 0) + "- "
        elif tag == "br":
            self.write(" ")
        elif tag == "code":
            self.write("`")
        elif tag in BLOCK:
            self.flush()

    def handle_endtag(self, tag):  # noqa: ANN001
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if self.pre_depth:
            if tag == "pre":
                self.pre_depth -= 1
                if self.pre_depth == 0:
                    code = "".join(self.pre_text).strip("\n")
                    if code.strip():
                        self.blocks.append(f"```\n{code}\n```")
            return
        if re.fullmatch(r"h[1-6]", tag) and self.heading:
            self.flush("#" * self.heading + " ")
            self.heading = None
        elif tag in ("td", "th") and self.cell is not None and self.table is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|")
            if self.table:
                self.table[-1].append(text)
            self.cell = None
        elif tag == "table" and self.table is not None:
            rows = [row for row in self.table if any(cell for cell in row)]
            self.table = None
            if rows:
                width = max(len(row) for row in rows)
                rows = [row + [""] * (width - len(row)) for row in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
                lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
                self.blocks.append("\n".join(lines))
        elif tag in ("ul", "ol"):
            self.flush()
            self.list_depth = max(self.list_depth - 1, 0)
        elif tag == "code":
            self.write("`")
        elif tag in BLOCK or tag == "li":
            self.flush()

    def handle_data(self, data):  # noqa: ANN001
        if self.skip_depth:
            return
        if self.pre_depth:
            self.pre_text.append(data)
        else:
            self.write(data)

    def markdown(self) -> str:
        self.flush()
        text = "\n\n".join(self.blocks)
        text = text.replace("``", "")  # empty inline code left by nested <code> tags
        text = re.sub(r"(?m)^\[(English|中文)\]$", "", text)  # language switcher
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (knowledge-fetch)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        charset = response.headers.get_content_charset()
    if not charset:
        match = re.search(rb'charset=["\']?([\w-]+)', raw[:4000])
        charset = match.group(1).decode() if match else "utf-8"
    return raw.decode(charset, errors="replace")


def body(html: str, site: str) -> str:
    start_marker, end_marker = SITE_BOUNDS[site]
    start = html.find(start_marker)
    if start < 0:
        raise SystemExit(f"article start {start_marker!r} not found")
    end = html.find(end_marker, start)
    return html[start:end if end > 0 else len(html)]


def keep_chapters(markdown: str, chapters: list[str]) -> str:
    """OASIS spec: keep only the requested top-level chapters (headings like '# 3 MQTT ...')."""
    parts = re.split(r"(?m)^(?=# \d+ )", markdown)
    kept = [part for part in parts if re.match(r"# (\d+) ", part) and
            re.match(r"# (\d+) ", part).group(1) in chapters]
    if not kept:
        raise SystemExit(f"chapters {chapters} not found")
    return "".join(kept)


def convert(entry: dict) -> str:
    html = fetch(entry["url"])
    converter = MarkdownConverter()
    converter.feed(body(html, entry["site"]))
    text = unescape(converter.markdown())
    if entry.get("chapters"):
        text = keep_chapters(text, entry["chapters"])
    header = f"来源：{entry['url']}\n\n"
    if entry.get("chapters"):
        header += f"节选：第 {'、'.join(entry['chapters'])} 章（原文未改动）\n\n"
    return header + text


def main(selected: list[str]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["documents"]:
        if selected and entry["document_id"] not in selected:
            continue
        text = convert(entry)
        path = KNOWLEDGE_DIR / f"{entry['document_id']}.md"
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{entry['document_id']:22s} {len(text):8d} chars  {entry['url']}")


if __name__ == "__main__":
    main(sys.argv[1:])
