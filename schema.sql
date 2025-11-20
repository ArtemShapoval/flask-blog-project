-- Видаляємо таблиці, якщо вони вже є (CASCADE видаляє зв'язки)
DROP TABLE IF EXISTS posts CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS archives CASCADE;

-- 1. Основні пости
-- SERIAL - це автоінкремент у Postgres
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    dislikes INTEGER DEFAULT 0
);

-- 2. Журнал подій
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Архів
CREATE TABLE archives (
    id SERIAL PRIMARY KEY,
    original_id INTEGER,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);