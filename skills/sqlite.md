---
name: sqlite
description: Работа с SQLite через sqlite_schema / sqlite_query — разведка схемы, SELECT с JOIN и агрегатами, проверка результата
triggers: SQLite, SQL, sqlite_query, sqlite_schema, база, остатки, заказы, таблица, JOIN
combines_with: 1c-query, python, markdown
---

# SQLite — работа через инструменты агента

## Порядок

1. `sqlite_schema()` — таблицы, колонки, число строк. Без этого шага
   запросы не писать.
2. Простой запрос на 5 строк (`LIMIT 5`) по каждой нужной таблице,
   чтобы увидеть форматы значений (даты как текст ISO, статусы).
3. Целевой запрос. Агрегаты с `GROUP BY`, соединения через `JOIN ... ON`.
4. Проверка: контрольная сумма или число строк вторым запросом; сверка
   одного значения вручную.

## Учебная база .data/demo.sqlite

```
nomenclature(sku PK, name, category, unit, price, is_active)
warehouses(id PK, code, name, city)
stock(sku, warehouse_id, qty, reserved, updated_at)        -- PK (sku, warehouse_id)
customers(id PK, name, inn, city)
orders(id PK, number, order_date, customer_id, warehouse_id, status)
order_items(order_id, line_no, sku, qty, price)            -- PK (order_id, line_no)
```

Доступный остаток: `qty - reserved`. Артикулы `sku` совпадают с
каталогом сайта (site_search / site_product).

Примеры:

```sql
-- остаток по артикулу по складам
SELECT w.code, s.qty, s.reserved, s.qty - s.reserved AS available, s.updated_at
FROM stock s JOIN warehouses w ON w.id = s.warehouse_id
WHERE s.sku = 'TA-2001';

-- продажи по категориям за август
SELECT n.category, SUM(i.qty) AS qty, ROUND(SUM(i.qty * i.price), 2) AS amount
FROM order_items i
JOIN orders o ON o.id = i.order_id
JOIN nomenclature n ON n.sku = i.sku
WHERE o.order_date BETWEEN '2026-08-01' AND '2026-08-31' AND o.status <> 'отменён'
GROUP BY n.category ORDER BY amount DESC;
```

## Правила

- Только чтение. Инструмент отклоняет `INSERT/UPDATE/DELETE/DROP` без
  `AI4TAI_DB_WRITE=1`; предлагать запись только по просьбе пользователя.
- Даты в базе — текст `YYYY-MM-DD`; сравнивать строками, функции
  `date()`, `strftime()`.
- Деление целых: `1.0 * a / b` или `CAST`.
- `NULL` в агрегатах: `COALESCE`.
- Результат больше 50 строк урезается; для сводок использовать
  `GROUP BY` и `LIMIT`.
- В ответе пользователю приводить запрос и вывод, а не пересказ.
