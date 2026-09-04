"""sqlite_schema / sqlite_query и генератор учебной базы."""
from __future__ import annotations

import sqlite3


def test_demo_db_builds_all_tables(demo_db):
    con = sqlite3.connect(str(demo_db))
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"nomenclature", "warehouses", "stock", "customers", "orders", "order_items"} <= tables


def test_demo_db_is_deterministic(tmp_path):
    import demo_db as builder
    a = builder.build(tmp_path / "a.sqlite")
    b = builder.build(tmp_path / "b.sqlite")
    q = "SELECT number, order_date, customer_id, status FROM orders ORDER BY id"
    ra = sqlite3.connect(str(a)).execute(q).fetchall()
    rb = sqlite3.connect(str(b)).execute(q).fetchall()
    assert ra == rb and len(ra) > 10


def test_demo_db_skus_match_catalog(demo_db, m):
    con = sqlite3.connect(str(demo_db))
    db_skus = {r[0] for r in con.execute("SELECT sku FROM nomenclature")}
    con.close()
    cat_skus = {p["sku"] for p in m._mock_catalog()}
    assert db_skus == cat_skus


def test_sqlite_schema_lists_tables(m, demo_db):
    out = m.sqlite_schema()
    assert "nomenclature" in out and "stock" in out
    assert "sku TEXT PK" in out
    assert "строк" in out


def test_sqlite_query_select(m, demo_db):
    out = m.sqlite_query("SELECT sku, name FROM nomenclature WHERE sku = 'TA-2001'")
    assert "TA-2001" in out
    assert "1 строк" in out


def test_sqlite_query_join_and_aggregate(m, demo_db):
    out = m.sqlite_query(
        "SELECT w.code, SUM(s.qty - s.reserved) AS available "
        "FROM stock s JOIN warehouses w ON w.id = s.warehouse_id GROUP BY w.code ORDER BY w.code"
    )
    assert "MSK-01" in out and "available" in out


def test_sqlite_query_truncates_rows(m, demo_db):
    out = m.sqlite_query("SELECT * FROM order_items", max_rows=5)
    assert "показаны первые 5" in out


def test_sqlite_query_rejects_write_by_default(m, demo_db, monkeypatch):
    monkeypatch.setattr(m, "DB_WRITE", False)
    out = m.sqlite_query("DELETE FROM stock")
    assert out.startswith("ERROR")
    assert "DELETE" in out
    con = sqlite3.connect(str(demo_db))
    assert con.execute("SELECT COUNT(*) FROM stock").fetchone()[0] > 0
    con.close()


def test_sqlite_query_write_when_allowed(m, demo_db, monkeypatch):
    monkeypatch.setattr(m, "DB_WRITE", True)
    out = m.sqlite_query("UPDATE stock SET reserved = 0")
    assert out.startswith("OK")


def test_sqlite_query_sql_error(m, demo_db):
    out = m.sqlite_query("SELECT nope FROM nowhere")
    assert out.startswith("ERROR")
    assert "no such table" in out


def test_sqlite_query_explicit_path(m, demo_db):
    out = m.sqlite_query("SELECT COUNT(*) AS n FROM warehouses", db_path=str(demo_db))
    assert "4" in out


def test_sqlite_missing_db(m, tmp_path):
    out = m.sqlite_query("SELECT 1", db_path=str(tmp_path / "none.sqlite"))
    assert out.startswith("ERROR") and "не найдена" in out


def test_default_db_autobuilds(m, tmp_path, monkeypatch):
    p = tmp_path / "auto.sqlite"
    monkeypatch.setattr(m, "DB_PATH", p)
    assert not p.exists()
    out = m.sqlite_schema()
    assert p.exists()
    assert "nomenclature" in out
