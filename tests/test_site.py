"""site_search / site_product / site_categories / site_status в режимах mock, auto, live (HTTP замокан)."""
from __future__ import annotations

import json

import pytest
import requests


class _Resp:
    def __init__(self, payload=None, text: str = "", status: int = 200, ct: str = "application/json"):
        self._payload = payload
        self.status_code = status
        self.text = text or (json.dumps(payload, ensure_ascii=False) if payload is not None else "")
        self.headers = {"Content-Type": ct}

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


# ---------------- mock catalog ----------------

def test_catalog_loads_and_has_skus(m):
    cat = m._mock_catalog()
    assert len(cat) >= 30
    skus = [p["sku"] for p in cat]
    assert len(skus) == len(set(skus)), "артикулы должны быть уникальны"
    for p in cat:
        assert p["name"] and p["category"] and isinstance(p["price"], (int, float))


def test_site_search_mock_finds_gloves(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_search("перчатки нитриловые", 3)
    assert "TA-1001" in out
    assert "источник: mock" in out


def test_site_search_mock_by_sku(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_search("TA-2001", 1)
    assert "Каска" in out


def test_site_search_mock_by_property(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_search("FFP3", 2)
    assert "TA-4002" in out


def test_site_search_mock_nothing(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_search("квантовый компьютер", 3)
    assert "Ничего не найдено" in out


def test_site_product_mock(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_product("ta-2001")
    assert "Артикул: TA-2001" in out
    assert "Защитные свойства" in out
    assert "technoavia.ru/catalog/TA-2001" in out


def test_site_product_mock_missing(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_product("NOPE-1")
    assert "не найден" in out


def test_site_categories_mock(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_categories()
    assert "Перчатки" in out
    assert "Спецобувь" in out


def test_site_status_mock(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_status()
    assert "Режим: mock" in out
    assert "позиций" in out


# ---------------- auto без токена → mock без сетевых вызовов ----------------

def test_auto_without_token_uses_mock_without_network(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "auto")
    monkeypatch.setattr(m, "TARU_API", "")
    calls = []

    def fake_get(*a, **kw):
        calls.append(a)
        raise AssertionError("сеть не должна использоваться")

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.site_search("каска", 1)
    assert "TA-2001" in out
    assert "токен" in out
    assert calls == []


# ---------------- auto с токеном: капча → fallback ----------------

def test_auto_with_token_captcha_falls_back(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "auto")
    monkeypatch.setattr(m, "TARU_API", "1|x")

    def fake_get(url, params=None, headers=None, timeout=None):
        assert headers["Authorization"] == "Bearer 1|x"
        return _Resp(text="<html><title>Вы не робот?</title>captcha</html>", ct="text/html")

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.site_search("каска", 1)
    assert "TA-2001" in out
    assert "капча" in out


def test_live_mode_error_is_reported(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "live")
    monkeypatch.setattr(m, "TARU_API", "1|x")

    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.site_search("каска", 1)
    assert out.startswith("ERROR")
    assert "недоступно" in out


def test_live_mode_parses_json(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "live")
    monkeypatch.setattr(m, "TARU_API", "1|x")

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url.endswith("/search")
        assert params["q"] == "каска"
        return _Resp({"data": [
            {"clear_sku": "X-1", "name": "Каска live", "category": {"name": "Головы"},
             "price": 999, "description": "из API"}
        ]})

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.site_search("каска", 1)
    assert "X-1" in out and "Каска live" in out
    assert "источник: live" in out


def test_live_product_http_error(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "live")
    monkeypatch.setattr(m, "TARU_API", "1|x")

    def fake_get(url, params=None, headers=None, timeout=None):
        return _Resp({"error": "nf"}, status=404)

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.site_product("X-404")
    assert out.startswith("ERROR")
    assert "404" in out


def test_site_search_limit_clamped(m, monkeypatch):
    monkeypatch.setattr(m, "SITE_MODE", "mock")
    out = m.site_search("перчатки", 100)
    # не больше MAX_RESULTS позиций
    assert out.count("  • ") <= m.MAX_RESULTS
