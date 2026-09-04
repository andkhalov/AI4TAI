"""Учебная SQLite-база «номенклатура / склады / остатки / заказы».

Структура повторяет упрощённую учётную систему: справочник номенклатуры
(артикулы совпадают с локальной копией каталога сайта, data/catalog_mock.json),
склады, остатки по складам, заказы покупателей и их строки.

Данные генерируются детерминированно (фиксированный seed), поэтому у всех
слушателей одинаковая база и одинаковые ответы на запросы.

    python src/demo_db.py                 # → data/demo.sqlite
    python src/demo_db.py path/to.sqlite
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOG = REPO / "data" / "catalog_mock.json"
DEFAULT_DB = REPO / "data" / "demo.sqlite"

SCHEMA = """
CREATE TABLE nomenclature (
    sku       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL,
    unit      TEXT NOT NULL DEFAULT 'шт',
    price     REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE warehouses (
    id    INTEGER PRIMARY KEY,
    code  TEXT NOT NULL UNIQUE,
    name  TEXT NOT NULL,
    city  TEXT NOT NULL
);
CREATE TABLE stock (
    sku          TEXT NOT NULL REFERENCES nomenclature(sku),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    qty          REAL NOT NULL,
    reserved     REAL NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (sku, warehouse_id)
);
CREATE TABLE customers (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    inn   TEXT,
    city  TEXT
);
CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    number       TEXT NOT NULL UNIQUE,
    order_date   TEXT NOT NULL,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    status       TEXT NOT NULL
);
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders(id),
    line_no  INTEGER NOT NULL,
    sku      TEXT NOT NULL REFERENCES nomenclature(sku),
    qty      REAL NOT NULL,
    price    REAL NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
CREATE INDEX ix_stock_wh ON stock(warehouse_id);
CREATE INDEX ix_orders_date ON orders(order_date);
CREATE INDEX ix_items_sku ON order_items(sku);
"""

WAREHOUSES = [
    ("MSK-01", "Основной склад Москва", "Москва"),
    ("SPB-01", "Склад Санкт-Петербург", "Санкт-Петербург"),
    ("EKB-01", "Склад Екатеринбург", "Екатеринбург"),
    ("NSK-01", "Склад Новосибирск", "Новосибирск"),
]

CUSTOMERS = [
    ("ООО «СтройМонтажСервис»", "7701234567", "Москва"),
    ("АО «Уральский металлургический завод»", "6601234567", "Екатеринбург"),
    ("ООО «Северная логистика»", "7801234567", "Санкт-Петербург"),
    ("ООО «СибирьЭнергоРемонт»", "5401234567", "Новосибирск"),
    ("ГБУ «Автомобильные дороги»", "7702345678", "Москва"),
    ("ООО «ПромХимТранс»", "7803456789", "Санкт-Петербург"),
    ("ООО «АгроТехника Юг»", "6101234567", "Ростов-на-Дону"),
    ("ИП Петров А. В.", "770123456789", "Тула"),
]

STATUSES = ["новый", "подтверждён", "собран", "отгружен", "закрыт", "отменён"]


def build(db_path: Path | str = DEFAULT_DB, catalog_path: Path = CATALOG, seed: int = 20260908) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)["products"]
    rnd = random.Random(seed)

    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA)

    con.executemany(
        "INSERT INTO nomenclature(sku, name, category, unit, price, is_active) VALUES (?,?,?,?,?,?)",
        [(p["sku"], p["name"], p["category"], p.get("unit", "шт"), float(p["price"]),
          0 if p.get("discontinued") else 1) for p in catalog],
    )
    con.executemany("INSERT INTO warehouses(code, name, city) VALUES (?,?,?)", WAREHOUSES)
    con.executemany("INSERT INTO customers(name, inn, city) VALUES (?,?,?)", CUSTOMERS)

    base = date(2026, 9, 1)
    stock_rows = []
    for p in catalog:
        for wh_id in range(1, len(WAREHOUSES) + 1):
            if rnd.random() < 0.15:
                continue  # позиции нет на этом складе
            qty = rnd.choice([0, 0, 5, 12, 24, 48, 100, 250, 500])
            reserved = min(qty, rnd.choice([0, 0, 0, 2, 5, 10]))
            upd = (base - timedelta(days=rnd.randint(0, 20))).isoformat()
            stock_rows.append((p["sku"], wh_id, float(qty), float(reserved), upd))
    con.executemany(
        "INSERT INTO stock(sku, warehouse_id, qty, reserved, updated_at) VALUES (?,?,?,?,?)", stock_rows
    )

    skus = [p["sku"] for p in catalog]
    prices = {p["sku"]: float(p["price"]) for p in catalog}
    order_id = 0
    items = []
    orders = []
    for day in range(60):
        d = base - timedelta(days=59 - day)
        for _ in range(rnd.randint(0, 2)):
            order_id += 1
            cust = rnd.randint(1, len(CUSTOMERS))
            wh = rnd.randint(1, len(WAREHOUSES))
            status = rnd.choices(STATUSES, weights=[1, 2, 2, 4, 6, 1])[0]
            orders.append((order_id, f"ЗК-{order_id:05d}", d.isoformat(), cust, wh, status))
            for line, sku in enumerate(rnd.sample(skus, rnd.randint(1, 4)), 1):
                qty = rnd.choice([1, 2, 5, 10, 20, 50])
                price = round(prices[sku] * rnd.choice([1.0, 1.0, 0.95, 0.9]), 2)
                items.append((order_id, line, sku, float(qty), price))
    con.executemany(
        "INSERT INTO orders(id, number, order_date, customer_id, warehouse_id, status) VALUES (?,?,?,?,?,?)",
        orders,
    )
    con.executemany(
        "INSERT INTO order_items(order_id, line_no, sku, qty, price) VALUES (?,?,?,?,?)", items
    )
    con.commit()
    con.close()
    return db_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    p = build(target)
    con = sqlite3.connect(str(p))
    n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("nomenclature", "warehouses", "stock", "customers", "orders", "order_items")}
    con.close()
    print(f"База создана: {p}")
    for t, c in n.items():
        print(f"  {t}: {c}")
