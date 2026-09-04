---
name: react
description: React + TypeScript для сайта-витрины — компоненты карточки товара, списки, запросы к API, проверка через сборку и тесты
triggers: React, TypeScript, TSX, компонент, витрина, frontend, npm, vite, fetch, карточка товара
combines_with: debug-loop, markdown
---

# React / TypeScript — компоненты витрины

## Цикл

1. Посмотреть структуру проекта: `package.json`, папка компонентов,
   как оформлены существующие компоненты (функциональные, хуки, стили).
2. Написать компонент в стиле проекта. Типы пропсов — `interface`.
3. Проверить типы и сборку: `npm run build` или `npx tsc --noEmit`.
   Тесты, если есть: `npm test -- --run`.
4. Исправить ошибки компилятора. Максимум 5 итераций.
5. Компонент без прогона `tsc` пользователю не отдаётся.

## Правила

- Функциональные компоненты, хуки. Состояние — `useState`, загрузка —
  `useEffect` с отменой через `AbortController` или библиотека запросов
  проекта, если она есть.
- Данные API типизировать: `interface Product { sku: string; name: string;
  price: number; ... }`. Поля брать из ответа API, не выдумывать.
- Состояния загрузки и ошибки отображать явно.
- Никаких ключей и токенов в коде компонента; адрес API — из
  конфигурации проекта.
- Стили — как в проекте (CSS-модули, styled-components, Tailwind).
  Новую библиотеку стилей не добавлять.

## Шаблон карточки товара

```tsx
interface Product {
  sku: string;
  name: string;
  category: string;
  price: number;
  unit: string;
  description?: string;
}

interface ProductCardProps {
  product: Product;
  onAdd?: (sku: string) => void;
}

export function ProductCard({ product, onAdd }: ProductCardProps) {
  return (
    <article className="product-card">
      <h3>{product.name}</h3>
      <p className="product-card__sku">Артикул: {product.sku}</p>
      <p className="product-card__price">
        {product.price.toLocaleString("ru-RU")} ₽ / {product.unit}
      </p>
      {product.description && <p>{product.description}</p>}
      {onAdd && (
        <button type="button" onClick={() => onAdd(product.sku)}>
          В корзину
        </button>
      )}
    </article>
  );
}
```

## Проверка результата

- `tsc` без ошибок.
- Компонент отрисовывается с тестовыми данными (Storybook или тестовая
  страница).
- Пустой список, ошибка API и долгая загрузка — три состояния проверены.
