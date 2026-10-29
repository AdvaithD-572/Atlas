"""Synthetic document fixtures, not an evaluation dataset."""

import io
import subprocess
from unittest.mock import patch

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from atlas.errors import AtlasError
from atlas.ingestion import parse_document
from tests.test_lifecycle import headers


def pdf_bytes(*texts: str, encrypted: bool = False) -> bytes:
    """Build real, tiny PDF pages with synthetic ASCII text; no report artifact."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 20 200 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("synthetic-test-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_html_sections_are_inert_and_locatable():
    raw = (
        b"<h1>Setup</h1><p>Rotate &amp; protect tokens.</p><script>steal()</script>"
        b"<h2>Limits</h2><p>Quota 10.</p>"
    )
    parsed = parse_document(raw, "text/html", 262144)
    assert "steal" not in parsed.text
    assert "Rotate & protect tokens." in parsed.text
    chunks = parsed.chunks(80, 10)
    assert {c.heading for c in chunks} == {"Setup", "Limits"}
    for chunk in chunks:
        assert parsed.text[chunk.start : chunk.end] == chunk.text


@pytest.mark.parametrize(
    "raw", [b"<script>only code</script>", b"<head>metadata</head>", b"<div hidden>hidden</div>"]
)
def test_empty_html_is_rejected(raw):
    with pytest.raises(AtlasError):
        parse_document(raw, "text/html", 262144)


def test_pdf_pages_preserve_actual_page_numbers_and_spans():
    parsed = parse_document(
        pdf_bytes("Alpha token guide", "", "Beta limits"), "application/pdf", 262144
    )
    chunks = parsed.chunks(80, 10)
    assert [c.page_number for c in chunks] == [1, 3]
    assert [c.text for c in chunks] == ["Alpha token guide", "Beta limits"]
    for chunk in chunks:
        assert parsed.text[chunk.start : chunk.end] == chunk.text


@pytest.mark.parametrize(
    "body,code",
    [
        (b"%PDF-1.7 malformed", "invalid_pdf"),
        (pdf_bytes("secret", encrypted=True), "encrypted_pdf"),
        (pdf_bytes(""), "empty_document"),
        (pdf_bytes(*(["x"] * 201)), "invalid_pdf"),
    ],
    ids=["malformed", "encrypted", "no-text", "page-limit"],
)
def test_pdf_rejection(body, code):
    with pytest.raises(AtlasError) as error:
        parse_document(body, "application/pdf", 262144)
    assert error.value.code == code


def test_pdf_subprocess_timeout_is_safe_and_releases_capacity():
    with patch(
        "atlas.ingestion.subprocess.run", side_effect=subprocess.TimeoutExpired("parser", 10)
    ):
        with pytest.raises(AtlasError) as error:
            parse_document(b"%PDF-synthetic", "application/pdf", 262144)
        assert error.value.code == "parser_timeout"
    assert parse_document(pdf_bytes("Recovery"), "application/pdf", 262144).text == "Recovery"


def test_pdf_subprocess_does_not_inherit_credentials(monkeypatch):
    monkeypatch.setenv("ATLAS_PRIVATE_TEST_SECRET", "do-not-pass-to-parser")
    actual = subprocess.run
    with patch("atlas.ingestion.subprocess.run", wraps=actual) as run:
        parse_document(pdf_bytes("Safe"), "application/pdf", 262144)
    assert "ATLAS_PRIVATE_TEST_SECRET" not in run.call_args.kwargs["env"]
    assert "-I" in run.call_args.args[0]


def test_pdf_real_deadline_kills_child_and_recovers(monkeypatch):
    monkeypatch.setattr("atlas.ingestion.PDF_TIMEOUT", 0.001)
    with pytest.raises(AtlasError) as error:
        parse_document(pdf_bytes("Synthetic timeout"), "application/pdf", 262144)
    assert error.value.code == "parser_timeout"
    monkeypatch.setattr("atlas.ingestion.PDF_TIMEOUT", 10)
    assert parse_document(pdf_bytes("Recovered"), "application/pdf", 262144).text == "Recovered"


def test_pdf_busy_limit_rejects_without_spawning():
    from atlas.ingestion import _pdf_slots

    with _pdf_slots, patch("atlas.ingestion.subprocess.run") as spawn:
        with pytest.raises(AtlasError) as error:
            parse_document(b"%PDF-busy", "application/pdf", 262144)
        assert error.value.code == "parser_busy"
        spawn.assert_not_called()


def test_html_depth_and_binary_limits():
    for raw in [b"<div>" * 129 + b"text", b"<p>nul\x00</p>", b"<p>\xff</p>", b"<br>" * 20001]:
        with pytest.raises(AtlasError):
            parse_document(raw, "text/html", 262144)


@pytest.mark.parametrize(
    "media,raw,location",
    [
        (
            "text/html",
            b"<h1>Rotation</h1><p>Rotate tokens safely.</p><script>notindexed</script>",
            {"heading": "Rotation", "page_number": None},
        ),
        (
            "application/pdf",
            pdf_bytes("Rotate tokens safely."),
            {"heading": None, "page_number": 1},
        ),
    ],
    ids=["html", "pdf"],
)
def test_formats_api_lifecycle_and_isolation(client, media, raw, location):
    auth = {**headers(), "Content-Type": media}
    response = client.put("/v1/documents/format", content=raw, headers=auth)
    assert response.status_code == 201
    doc = response.json()
    assert doc["normalization"] == ("pdf-text-v1" if media == "application/pdf" else "html-text-v1")
    assert client.put("/v1/documents/format", content=raw, headers=auth).json() == doc
    chunks = client.get(f"/v1/documents/{doc['id']}/chunks", headers=headers()).json()["items"]
    passage = chunks[0]
    assert all(passage[key] == value for key, value in location.items())
    assert client.get(f"/v1/citations/{passage['id']}", headers=headers()).json() == passage
    assert client.get(f"/v1/citations/{passage['id']}", headers=headers("bob")).status_code == 404
    found = client.post(
        "/v1/search",
        json={"question": "tokens"},
        headers={"Authorization": headers()["Authorization"]},
    ).json()
    assert found["passages"][0] == passage
    replacement = client.put(
        "/v1/documents/format", content=b"Replacement text", headers=headers()
    ).json()
    assert replacement["id"] == doc["id"] and replacement["version"] == 2
    assert client.get(f"/v1/citations/{passage['id']}", headers=headers()).status_code == 404
    assert client.delete(f"/v1/documents/{doc['id']}", headers=headers()).status_code == 204
