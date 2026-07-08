# RecipeNest — Daily Cookbook & Food

> Gather around good food

Мини-приложение «личная кулинарная книга»: Expo (React Native, TypeScript) + FastAPI (SQLite). Без аккаунтов — данные привязаны к анонимному UUID устройства (заголовок `X-Device-Id`).

## Структура

```
backend/    FastAPI + SQLAlchemy + SQLite, загрузка фото в static/recipe_images/
frontend/   Expo SDK 54, React Navigation (3 таба + модалка + detail), Reanimated
```

## Запуск бэкенда

```powershell
cd backend
python -m venv .venv          # один раз
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

БД (`backend/recipenest.db`) и таблицы создаются автоматически при первом старте. `--host 0.0.0.0` нужен, чтобы телефон в той же Wi-Fi-сети видел API.

### Стартовый каталог рецептов

При первом обращении нового устройства к API его кулинарная книга автоматически наполняется каталогом из **30 готовых рецептов** (8 завтраков, 8 обедов, 9 ужинов, 5 десертов; 217 строк ингредиентов, 86 уникальных ингредиентов) с иллюстрациями из `static/recipe_images/seed/`. Каталог задан в `backend/seed_data.py`. Оценки, избранное и счётчики готовки при этом пустые — статистика отражает только реальные действия пользователя. Сидинг выполняется один раз на устройство (таблица `seeded_devices`): удалённые рецепты не возвращаются. Общие seed-картинки не удаляются при удалении рецепта.

> **Если рецепты не появились:** перезапустите бэкенд (`uvicorn main:app ...`) — сидинг есть только в новой версии кода, и убедитесь, что приложение не в offline-режиме (нет плашки «Offline»).

Дополнительно в приложении есть **окно каталога** (иконка книги на главном экране): список всех 30 готовых рецептов с кнопкой «Add» — удалённый рецепт можно вернуть в один тап. В форме добавления рецепта у каждой строки ингредиента есть кнопка-список — открывает **окно выбора ингредиента** (86 позиций с поиском и типовым количеством). Эндпоинты: `GET /api/catalog/recipes`, `POST /api/catalog/recipes/{index}/add`, `GET /api/catalog/ingredients`.

## Запуск фронтенда (dev)

1. Укажите адрес бэкенда в `frontend/.env`:
   - Android-эмулятор: `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`
   - Реальный телефон: `EXPO_PUBLIC_API_URL=http://<IP-вашего-ПК>:8000`
2. Запуск:

```powershell
cd frontend
npm install
npx expo start
```

## Сборка релизного AAB (локально, без EAS)

Требуется Android Studio (SDK) и JDK 17.

```powershell
cd frontend
npx expo prebuild --platform android   # генерирует папку android/
cd android
.\gradlew bundleRelease
```

Готовый файл: `frontend/android/app/build/outputs/bundle/release/app-release.aab`.

Перед публикацией подпишите bundle своим ключом (в `android/app/build.gradle` замените debug-подпись на release-keystore или используйте Play App Signing).

Важно: перед сборкой пропишите в `frontend/.env` **продакшен**-адрес API (публичный хост), иначе приложение будет смотреть на адрес эмулятора.

## Разрешения (Google Play Data Safety)

- Фото выбираются только по одному через системный Android Photo Picker — разрешения на чтение медиатеки **не требуются и заблокированы** в манифесте (`blockedPermissions`).
- `CAMERA` — единственное опасное разрешение; запрашивается в рантайме только когда пользователь сам выбирает «Take photo». Отказ обрабатывается без падения.
- Персональные данные не собираются: только локально сгенерированный анонимный UUID устройства для скоупинга собственных рецептов. Аналитики, рекламы и сторонних SDK нет.

## API (кратко)

Все эндпоинты требуют заголовок `X-Device-Id` (400 без него), база — `/api`:

| Метод | Путь | Что делает |
|---|---|---|
| GET | `/api/recipes?category=&q=` | список рецептов устройства |
| POST | `/api/recipes` | создать (multipart: `data` JSON + опц. `image`) |
| GET/PUT/DELETE | `/api/recipes/{id}` | детально / изменить / удалить (с файлом фото) |
| POST | `/api/recipes/{id}/rate` | `{"rating": 1..5}` |
| POST | `/api/recipes/{id}/cook` | +1 к счётчику готовки |
| POST | `/api/recipes/{id}/favorite` | `{"is_favorite": bool}` |
| GET | `/api/stats` | агрегаты для экрана «Your Kitchen» |
