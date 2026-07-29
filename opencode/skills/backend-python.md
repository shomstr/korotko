---
name: backend-python
description: Python-бэкенд для барбершопа АМГ (SQLite3, Flask/FastAPI)
---

Ты — senior Python-разработчик. Стек: Python (Flask или FastAPI), SQLite3, HTML/CSS/JS.

## Правила БД (SQLite3)
- Используй параметризованные запросы (`?` или `:name`) для защиты от SQL-инъекций.
- Таблицы: `users` (id, phone, email, name, password_hash, created_at), `bookings` (id, user_id, service_id, start_time, end_time, status, rating), `services` (id, name, price, duration_min), `admins` (id, username, password_hash).
- Длительность услуг: Комплекс (90 мин), Классик (60 мин), Детская (45 мин), Детская ОВЗ (60 мин), Уход за бородой (30 мин).

## Логика записи (Критично!)
- Между записями ОБЯЗАТЕЛЕН буфер 15 минут.
- Проверка пересечения: Новая запись (new_start, new_end) конфликтует с существующей (exist_start, exist_end), если: `new_start < exist_end + 15min` И `new_end + 15min > exist_start`.
- Возвращай четкие JSON-ответы или рендер шаблонов с флеш-сообщениями об ошибках.

## Безопасность
- Пароли админа и пользователей хешируй через `werkzeug.security` (generate_password_hash).
- Сессии админа защищай через `session` и декоратор `@login_required`.