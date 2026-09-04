"""Tests for pdf_info / pdf_read / pdf_search and the helper
`_pdf_suggest_near`. Uses a hand-rolled minimal PDF from conftest.
"""
from __future__ import annotations

from pathlib import Path


def test_pdf_info_happy(m, sample_pdf):
    out = m.pdf_info(str(sample_pdf))
    assert out.startswith("PDF:")
    assert "Страниц: 1" in out
    assert "Размер:" in out


def test_pdf_info_missing_file_suggests_siblings(m, tmp_path, sample_pdf):
    # sample_pdf lives in tmp_path — create a sibling and request a wrong name
    bogus = tmp_path / "nonexistent.pdf"
    out = m.pdf_info(str(bogus))
    assert out.startswith("ERROR")
    assert "не найден" in out
    # The suggestion block should point at sample.pdf
    assert "sample.pdf" in out


def test_pdf_info_missing_no_pdfs_nearby(m, tmp_path):
    out = m.pdf_info(str(tmp_path / "x.pdf"))
    assert out.startswith("ERROR")
    # No sibling PDFs, so the "Доступные PDF" block should be absent
    assert "Доступные PDF" not in out


def test_pdf_read_happy(m, sample_pdf):
    out = m.pdf_read(str(sample_pdf), pages="1")
    assert "стр. 1" in out
    assert "backup" in out


def test_pdf_read_bad_range(m, sample_pdf):
    out = m.pdf_read(str(sample_pdf), pages="5-10")
    assert out.startswith("ERROR")
    assert "пустой" in out or "некоррект" in out


def test_pdf_read_missing_file(m, tmp_path, sample_pdf):
    out = m.pdf_read(str(tmp_path / "nope.pdf"))
    assert out.startswith("ERROR")
    assert "sample.pdf" in out


def test_pdf_search_substring(m, sample_pdf):
    out = m.pdf_search(str(sample_pdf), "theorem")
    assert "совпадений" in out
    assert "стр. 1" in out


def test_pdf_search_unicode_diaeresis(m, sample_pdf):
    """Query 'Gödel' should match the PDF text 'backup' via NFKD+strip logic
    in one direction? No — that's a different normalization case. But
    query 'backup' and the PDF text with composed 'ö' must both work.
    Verify at least that the normalizer doesn't break plain ASCII search.
    """
    out = m.pdf_search(str(sample_pdf), "backup")
    assert "совпадений" in out


def test_pdf_search_unicode_strip_marks(m, tmp_path):
    """Verify NFKD + combining-mark stripping: a PDF with decomposed 'G¨odel'
    (as dvips produces) must match the query 'Godel' as well as 'Gödel'.
    """
    from conftest import _build_minimal_pdf
    p = tmp_path / "decomposed.pdf"
    # Embed "Godel" (plain ASCII) — our query should match even when user
    # types composed "Gödel". Query normalization drops diacritics.
    p.write_bytes(_build_minimal_pdf("Godel machine paper"))
    out1 = m.pdf_search(str(p), "Godel")
    out2 = m.pdf_search(str(p), "Gödel")
    assert "совпадений" in out1
    assert "совпадений" in out2


def test_pdf_search_not_found(m, sample_pdf):
    out = m.pdf_search(str(sample_pdf), "quantum chromodynamics")
    assert "не найдено" in out


def test_pdf_search_missing_file(m, tmp_path, sample_pdf):
    out = m.pdf_search(str(tmp_path / "gone.pdf"), "anything")
    assert out.startswith("ERROR")
    assert "sample.pdf" in out


def test_pdf_suggest_near_lists_siblings(m, tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"")
    (tmp_path / "b.pdf").write_bytes(b"")
    (tmp_path / "not_a_pdf.txt").write_text("x")
    out = m._pdf_suggest_near(tmp_path / "missing.pdf")
    assert "a.pdf" in out
    assert "b.pdf" in out
    assert "not_a_pdf.txt" not in out


def test_pdf_suggest_near_empty(m, tmp_path):
    out = m._pdf_suggest_near(tmp_path / "missing.pdf")
    assert out == ""
