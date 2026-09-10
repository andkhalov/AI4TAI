"""rag_index: нарезка, hash-эмбеддер, построение индекса, поиск; MCP-инструменты rag_search / rag_status."""
from __future__ import annotations

from pathlib import Path

import rag_index as r


def test_chunk_text_respects_size_and_overlap():
    text = "\n".join(f"строка {i} " + "x" * 40 for i in range(60))
    chunks = r.chunk_text(text, chunk_chars=500, overlap_lines=2)
    assert len(chunks) > 3
    for c in chunks:
        assert len(c["text"]) <= 600
        assert c["start_line"] <= c["end_line"]
    # перекрытие: следующий фрагмент начинается раньше конца предыдущего
    assert chunks[1]["start_line"] <= chunks[0]["end_line"]


def test_chunk_text_empty():
    assert r.chunk_text("") == []
    assert r.chunk_text("\n\n") == []


def test_hash_embedder_deterministic_and_normalized():
    e = r.HashEmbedder()
    a = e.embed_query("каска защитная")
    b = e.embed_query("каска защитная")
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6


def test_hash_embedder_similarity_orders_sensibly():
    e = r.HashEmbedder()
    q = e.embed_query("срок носки каски")
    near = e.embed_query("каска защитная срок носки не более 3 лет")
    far = e.embed_query("резервное копирование журнала транзакций SQL Server")
    assert r._cosine(q, near) > r._cosine(q, far)


def test_build_index_and_search(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# Каски\nКаска защитная выдаётся на 3 года.\nДата выпуска на козырьке.", encoding="utf-8")
    (docs / "b.txt").write_text("Резервное копирование базы выполняется ночью.\nЖурнал транзакций каждые 30 минут.", encoding="utf-8")
    (docs / ".hidden.md").write_text("скрытый файл не индексируется", encoding="utf-8")
    (docs / "c.bin").write_bytes(b"\x00\x01")
    db = tmp_path / "idx.sqlite"
    st = r.build_index(docs, db, r.HashEmbedder())
    assert st["docs"] == 2 and st["chunks"] >= 2 and st["embedder"] == "hash"
    hits = r.search(db, "срок каски", top_k=1)
    assert hits and hits[0]["path"] == "a.md"
    hits = r.search(db, "журнал транзакций", top_k=1)
    assert hits[0]["path"] == "b.txt"
    stats = r.index_stats(db)
    assert stats["docs"] == 2 and stats["embedder"] == "hash"


def test_index_reads_pdf(tmp_path, sample_pdf):
    docs = tmp_path / "d"
    docs.mkdir()
    (docs / "s.pdf").write_bytes(sample_pdf.read_bytes())
    db = tmp_path / "i.sqlite"
    st = r.build_index(docs, db, r.HashEmbedder())
    assert st["docs"] == 1
    hits = r.search(db, "backup regulation", top_k=1)
    assert hits and "backup" in hits[0]["text"].lower()


def test_get_embedder_hash_without_keys(monkeypatch):
    monkeypatch.delenv("YANDEX_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_CLOUD_FOLDER", raising=False)
    monkeypatch.delenv("AI4TAI_EMBEDDER", raising=False)
    assert r.get_embedder().name == "hash"
    assert r.get_embedder("hash").name == "hash"


def test_get_embedder_yandex_requires_keys(monkeypatch):
    monkeypatch.delenv("YANDEX_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_CLOUD_FOLDER", raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        r.get_embedder("yandex")


def test_yandex_embedder_calls_api(monkeypatch):
    import requests

    class R:
        def raise_for_status(self): pass
        def json(self): return {"data": [{"embedding": [3.0, 4.0]}]}

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["model"] = json["model"]
        return R()

    monkeypatch.setattr(requests, "post", fake_post)
    e = r.YandexEmbedder("key", "b1folder")
    v = e.embed_query("тест")
    assert captured["url"].endswith("/v1/embeddings")
    assert captured["model"] == "emb://b1folder/text-search-query/latest"
    assert abs(v[0] - 0.6) < 1e-6 and abs(v[1] - 0.8) < 1e-6
    e.embed_docs(["a"])
    assert captured["model"] == "emb://b1folder/text-search-doc/latest"


# ---------------- MCP-инструменты ----------------

def test_rag_status_missing(m, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "RAG_DB", tmp_path / "none.sqlite")
    out = m.rag_status()
    assert "не найден" in out and "rag_index.py index" in out


def test_rag_search_missing(m, tmp_path, monkeypatch):
    monkeypatch.setattr(m, "RAG_DB", tmp_path / "none.sqlite")
    out = m.rag_search("каска")
    assert out.startswith("ERROR")


def test_rag_status_and_search_on_fixtures(m, rag_db):
    st = m.rag_status()
    assert "Документов: 3" in st and "hash" in st
    out = m.rag_search("рукопожатие есть, сервер недоступен", top_k=2)
    assert "vpn.md" in out
    assert "строки" in out


def test_rag_search_finds_helmet_doc(m, rag_db):
    out = m.rag_search("срок носки каски", top_k=3)
    assert "caskas.md" in out
