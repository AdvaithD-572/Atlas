import os
import subprocess
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path
from threading import BoundedSemaphore

from pydantic import TypeAdapter, ValidationError

from atlas.errors import AtlasError

PARSER_VERSION = "utf8-literal-v1"
MEDIA_TYPES = {"text/plain", "text/markdown", "text/html", "application/pdf"}
MAX_EXTRACTED_CHARS = 1_048_576
PDF_TIMEOUT = 10
_pdf_slots = BoundedSemaphore(1)


def parser_version(media_type: str) -> str:
    if media_type == "application/pdf":
        return f"pypdf-{version('pypdf')}-pages-v1"
    if media_type == "text/html":
        return "html-inert-sections-v1"
    return PARSER_VERSION


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    start: int
    end: int
    text: str
    page_number: int | None = None
    heading: str | None = None


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    page_number: int | None = None
    heading: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    sections: tuple[Section, ...]
    parser_version: str

    def chunks(self, size: int, overlap: int) -> list[Chunk]:
        result: list[Chunk] = []
        for section in self.sections:
            for chunk in chunk_text(self.text[section.start : section.end], size, overlap):
                if len(result) >= 4096:
                    raise AtlasError("too_many_chunks", "Document exceeds the chunk limit.", 413)
                result.append(
                    Chunk(
                        len(result),
                        section.start + chunk.start,
                        section.start + chunk.end,
                        chunk.text,
                        section.page_number,
                        section.heading,
                    )
                )
        return result


def validate_upload(raw: bytes, media_type: str, max_bytes: int) -> None:
    if media_type not in MEDIA_TYPES:
        raise AtlasError("unsupported_type", "Use PDF, HTML, Markdown or plain text.", 415)
    if len(raw) > max_bytes:
        raise AtlasError("payload_too_large", "Document exceeds the upload limit.", 413)
    if not raw:
        raise AtlasError("empty_document", "Document must contain text.")
    if media_type == "application/pdf" and not raw.startswith(b"%PDF-"):
        raise AtlasError("invalid_pdf", "The file is not a supported PDF.")


def _validate_text(text: str) -> None:
    if not text.strip():
        raise AtlasError("empty_document", "No extractable text. Image-only PDFs need OCR first.")
    if len(text) > MAX_EXTRACTED_CHARS:
        raise AtlasError("extracted_text_too_large", "Extracted text exceeds the limit.", 413)
    if any(
        (ord(char) < 32 and char not in "\n\r\t") or 0xD800 <= ord(char) <= 0xDFFF for char in text
    ):
        raise AtlasError("invalid_text", "Binary control characters are not supported.")


class _HTMLText(HTMLParser):
    """Extract inert text. This is not a browser or a CSS visibility evaluator."""

    ignored = {"head", "script", "style", "template", "noscript", "iframe", "object", "svg", "math"}
    void = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    blocks = {
        "p",
        "div",
        "li",
        "ul",
        "ol",
        "pre",
        "blockquote",
        "tr",
        "td",
        "th",
        "section",
        "article",
        "br",
        "hr",
    }
    headings = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.parts: list[str] = []
        self.sections: list[tuple[str, str | None]] = []
        self.heading: str | None = None
        self.heading_start: int | None = None
        self.nodes = 0

    def _hidden(self) -> bool:
        return bool(self.stack and self.stack[-1][1])

    def _flush(self) -> None:
        text = "".join(self.parts).strip()
        if text:
            self.sections.append((text, self.heading))
        self.parts = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > 20000 or len(self.stack) >= 128:
            raise AtlasError(
                "html_complexity_limit", "HTML structure exceeds the parser limit.", 413
            )
        hidden = (
            self._hidden()
            or tag in self.ignored
            or any(
                name == "hidden" or (name == "aria-hidden" and value == "true")
                for name, value in attrs
            )
        )
        if not hidden:
            if tag in self.headings:
                self._flush()
                self.heading = None
                self.heading_start = len(self.parts)
            elif tag in self.blocks:
                self.parts.append("\n")
        if tag not in self.void:
            self.stack.append((tag, hidden))

    def handle_endtag(self, tag: str) -> None:
        hidden = self._hidden()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not hidden:
            if tag in self.headings and self.heading_start is not None:
                self.heading = "".join(self.parts[self.heading_start :]).strip()[:512] or None
                self.heading_start = None
                self.parts.append("\n")
            elif tag in self.blocks:
                self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self._hidden():
            self.parts.append(data)


def _pdf_pages(raw: bytes) -> list[str]:
    if not _pdf_slots.acquire(blocking=False):
        raise AtlasError("parser_busy", "PDF parser is busy. Retry shortly.", 429)
    try:
        # Do not pass application credentials, PATH overrides or uploaded filenames.
        environment = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-B", str(Path(__file__).with_name("pdf_parser.py"))],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=PDF_TIMEOUT,
                check=False,
                env=environment,
                creationflags=creationflags,
            )
        except subprocess.TimeoutExpired as exc:
            raise AtlasError("parser_timeout", "PDF parsing exceeded its time limit.", 422) from exc
        except OSError as exc:
            raise AtlasError("parser_unavailable", "PDF parser is unavailable.", 503) from exc
        if result.returncode != 0:
            raise AtlasError("invalid_pdf", "PDF is malformed or exceeds parser resource limits.")
        if result.stdout == b"encrypted":
            raise AtlasError(
                "encrypted_pdf", "Encrypted PDFs are not supported. Upload an unencrypted copy."
            )
        try:
            pages = TypeAdapter(list[str]).validate_json(result.stdout, strict=True)
        except ValidationError as exc:
            raise AtlasError("invalid_pdf", "PDF extraction failed.") from exc
        if len(pages) > 200 or sum(map(len, pages)) > MAX_EXTRACTED_CHARS:
            raise AtlasError("invalid_pdf", "PDF exceeds parser limits.")
        return pages
    finally:
        _pdf_slots.release()


def parse_document(raw: bytes, media_type: str, max_bytes: int) -> ParsedDocument:
    validate_upload(raw, media_type, max_bytes)
    version = parser_version(media_type)
    segments: list[tuple[str, int | None, str | None]]
    if media_type == "application/pdf":
        segments = [
            (text.strip(), number, None)
            for number, text in enumerate(_pdf_pages(raw), 1)
            if text.strip()
        ]
    else:
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise AtlasError("invalid_encoding", "Document must use UTF-8.") from exc
        _validate_text(text)
        if media_type != "text/html":
            return ParsedDocument(text, (Section(0, len(text)),), version)
        parser = _HTMLText()
        try:
            parser.feed(text)
            parser.close()
        except (ValueError, AssertionError) as exc:
            raise AtlasError("invalid_html", "HTML could not be parsed.") from exc
        parser._flush()
        segments = [(text, None, heading) for text, heading in parser.sections]
    parts: list[str] = []
    sections: list[Section] = []
    offset = 0
    for text, page, heading in segments:
        if parts:
            parts.append("\n\n")
            offset += 2
        sections.append(Section(offset, offset + len(text), page, heading))
        parts.append(text)
        offset += len(text)
    text = "".join(parts)
    _validate_text(text)
    return ParsedDocument(text, tuple(sections), version)


def parse_text(raw: bytes, media_type: str, max_bytes: int) -> str:
    return parse_document(raw, media_type, max_bytes).text


def chunk_text(text: str, size: int, overlap: int) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk configuration.")
    count = 1 + max(0, (len(text) - size + size - overlap - 1) // (size - overlap))
    if count > 4096:
        raise AtlasError("too_many_chunks", "Document exceeds the chunk limit.", 413)
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(Chunk(len(chunks), start, end, text[start:end]))
        if end == len(text):
            break
        start = end - overlap
    return chunks
