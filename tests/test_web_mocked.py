"""web_search / web_fetch с замоканным HTTP."""
from __future__ import annotations

import json

import requests


class _Resp:
    def __init__(self, payload=None, text: str = "", status: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


_DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.cntd.ru%2Fdocument%2F1200103283">ГОСТ 12.4.252-2013</a>
  <a class="result__snippet" href="#">Перчатки для защиты от механических воздействий.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.org/siz">Нормы выдачи СИЗ</a>
  <a class="result__snippet" href="#">Типовые нормы бесплатной выдачи...</a>
</div>
</body></html>
"""


def test_web_search_ddg_parses(m, monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        assert "duckduckgo" in url
        return _Resp(text=_DDG_HTML)
    monkeypatch.setattr(m.requests, "post", fake_post)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    out = m.web_search("ГОСТ 12.4.252", 5)
    assert "docs.cntd.ru" in out and "example.org" in out
    assert "duckduckgo.com/l/" not in out


def test_web_search_brave(m, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert "brave" in url
        return _Resp({"web": {"results": [{"url": "https://x", "title": "X", "description": "snip"}]}})
    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setenv("BRAVE_API_KEY", "dummy")
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    out = m.web_search("q", 3)
    assert "brave" in out and "https://x" in out


def test_web_search_disabled(m, monkeypatch):
    monkeypatch.setattr(m, "WEB_DISABLED", True)
    assert "отключён" in m.web_search("x")


def test_web_search_error(m, monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("nope")
    monkeypatch.setattr(m.requests, "post", fake_post)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    assert m.web_search("x").startswith("ERROR")


def test_web_fetch_html(m, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _Resp(text="<html><body><p>Hello <b>world</b></p></body></html>",
                     headers={"Content-Type": "text/html; charset=utf-8"})
    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    out = m.web_fetch("https://example.com")
    assert "Hello world" in out and "<b>" not in out


def test_web_fetch_truncation(m, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _Resp(text="abc" * 2000, headers={"Content-Type": "text/plain"})
    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    out = m.web_fetch("https://example.com", max_chars=500)
    assert "truncated" in out and len(out) < 1500


def test_web_fetch_error(m, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise requests.ConnectionError("nope")
    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setattr(m, "WEB_DISABLED", False)
    assert m.web_fetch("https://example.com").startswith("ERROR")
