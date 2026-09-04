"""Интеграционные тесты с реальной сетью. Запуск: AI4TAI_TEST_NETWORK=1 pytest tests/test_network.py"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.network


def _skip_if_upstream_error(out: str, name: str) -> None:
    if out.startswith("ERROR") and any(
        k in out for k in ("Timeout", "ConnectionError", "SSLError", "NameResolution")
    ):
        pytest.skip(f"{name}: внешний сервис недоступен: {out[:200]}")


def test_web_search_live(m, monkeypatch):
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    out = m.web_search("ГОСТ 12.4.252-2013 перчатки", num_results=3)
    _skip_if_upstream_error(out, "duckduckgo")
    assert not out.startswith("ERROR")
    assert "http" in out


def test_web_fetch_live(m, monkeypatch):
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    out = m.web_fetch("https://example.com", max_chars=1000)
    _skip_if_upstream_error(out, "web_fetch")
    assert "Example Domain" in out


def test_site_status_live(m, monkeypatch):
    """Фиксирует фактическое поведение API сайта: JSON или капча. Падать не должен."""
    monkeypatch.setattr(m, "SITE_MODE", "auto")
    monkeypatch.setattr(m, "TARU_API", os.environ.get("TARU_API", ""))
    out = m.site_status()
    assert "Режим: auto" in out


@pytest.mark.skipif(not (os.environ.get("YANDEX_CLOUD_API_KEY") and os.environ.get("YANDEX_CLOUD_FOLDER")),
                    reason="нужны YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER")
def test_yandex_embedder_live():
    import rag_index as r
    e = r.get_embedder("yandex")
    q = e.embed_query("защита рук от масла")
    v = e.embed_docs(["перчатки нитриловые с полным обливом", "резервное копирование базы"])
    assert len(q) > 100
    assert r._cosine(q, v[0]) > r._cosine(q, v[1])
