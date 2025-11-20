import psycopg2
from psycopg2.extras import RealDictCursor
import random
import os
from flask import Flask, request, g, render_template, redirect, url_for

app = Flask(__name__)

# --- НАЛАШТУВАННЯ ПІДКЛЮЧЕННЯ ---
DB_HOST = "localhost"
DB_NAME = "flask_blog"  # Переконася, що створив цю БД в pgAdmin!
DB_USER = "postgres"  # Твій логін в pgAdmin (зазвичай postgres)
DB_PASS = "artem"  # <--- ВПИШИ СЮДИ СВІЙ ПАРОЛЬ ВІД PGADMIN


def get_db():
    """Підключення до PostgreSQL"""
    if 'db' not in g:
        try:
            g.db = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS
            )
        except Exception as e:
            print(f"\n📛 ПОМИЛКА ПІДКЛЮЧЕННЯ: {e}")
            print(f"Перевірте, чи створили ви базу '{DB_NAME}' і чи правильний пароль.\n")
            return None
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# Допоміжна функція для SELECT запитів
def query_db(query, args=(), one=False):
    conn = get_db()
    if conn is None: return []

    # RealDictCursor повертає результат як словник {'title': '...', 'id': 1}
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(query, args)

    # Якщо це запит на вибірку даних
    if cur.description:
        rv = cur.fetchall()
    else:
        rv = []

    cur.close()
    return (rv[0] if rv else None) if one else rv


# Функція ініціалізації таблиць
def init_db():
    conn = get_db()
    if conn is None: return
    cur = conn.cursor()

    # 1. Виконуємо схему (створення таблиць)
    with app.open_resource('schema.sql', mode='r') as f:
        cur.execute(f.read())

    # 2. Додаємо об'єкти БД (функції та тригери)
    # Цей код створює об'єкти, про які ми говорили
    sql_objects = """
    -- 1. Додаємо колонку 'updated_at' (якщо немає)
    ALTER TABLE posts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

    -- 2. Створення ФУНКЦІЇ для тригера
    CREATE OR REPLACE FUNCTION update_changetimestamp_column()
    RETURNS TRIGGER AS $$
    BEGIN
       NEW.updated_at = now(); 
       RETURN NEW;
    END;
    $$ language 'plpgsql';

    -- 3. Створення ТРИГЕРА
    CREATE OR REPLACE TRIGGER update_posts_changetimestamp
    BEFORE UPDATE ON posts
    FOR EACH ROW
    EXECUTE FUNCTION update_changetimestamp_column();

    -- 4. Створення аналітичної ФУНКЦІЇ (Рейтинг)
    CREATE OR REPLACE FUNCTION get_post_rating(likes_count INT, dislikes_count INT)
    RETURNS INT AS $$
    BEGIN
        RETURN likes_count - dislikes_count;
    END;
    $$ LANGUAGE plpgsql;
    """
    cur.execute(sql_objects)

    conn.commit()
    cur.close()
    print("Таблиці та об'єкти БД створено успішно.")


def populate_db():
    conn = get_db()
    if conn is None: return
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO posts (title, content) VALUES (%s, %s)',
                    ('Привіт, Postgres!', 'Цей сайт тепер працює на професійній базі даних.'))

        cur.execute('INSERT INTO posts (title, content, likes, dislikes) VALUES (%s, %s, %s, %s)',
                    ('Популярна тема', 'PostgreSQL набагато потужніший за SQLite.', 100, 5))

        cur.execute('INSERT INTO audit_log (action) VALUES (%s)',
                    ('Міграція на PostgreSQL виконана',))

        conn.commit()
        print("Тестові дані додано.")
    except Exception as e:
        conn.rollback()
        print(f"Помилка наповнення: {e}")
    finally:
        cur.close()


def setup_database():
    pass


# --- МАРШРУТИ ---

@app.route('/')
def index():
    try:
        # ВИКОРИСТАННЯ ФУНКЦІЇ БД: Викликаємо get_post_rating прямо в SELECT
        sql_query = """
        SELECT 
            id, 
            title, 
            content, 
            likes, 
            dislikes, 
            updated_at, -- Для перевірки роботи ТРИГЕРА
            get_post_rating(likes, dislikes) AS rating -- ВИКЛИК ФУНКЦІЇ
        FROM posts 
        ORDER BY id DESC
        """
        posts = query_db(sql_query)
        logs = query_db('SELECT * FROM audit_log ORDER BY id DESC LIMIT 10')
        res = query_db('SELECT COUNT(*) as count FROM archives', one=True)
        archive_count = res['count'] if res else 0
    except Exception as e:
        posts = []
        logs = []
        archive_count = 0
        print(f"Error loading index: {e}")

    return render_template('index.html', posts=posts, logs=logs, archive_count=archive_count)


@app.route('/archive')
def view_archive():
    posts = query_db('SELECT * FROM archives ORDER BY deleted_at DESC')
    return render_template('archive.html', posts=posts)


@app.route('/add', methods=['POST'])
def add_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        conn = get_db()
        cur = conn.cursor()
        try:
            # Тут оновлення: старий пост видаляється, новий створюється.
            # Нам потрібен маршрут для РЕДАГУВАННЯ, щоб продемонструвати ТРИГЕР.
            cur.execute('INSERT INTO posts (title, content) VALUES (%s, %s)', (title, content))
            cur.execute('INSERT INTO audit_log (action) VALUES (%s)', (f"Створено пост: {title}",))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(e)
        finally:
            cur.close()

        return redirect(url_for('index'))


# НОВИЙ МАРШРУТ для редагування (щоб викликати ТРИГЕР)
@app.route('/edit/<int:id>', methods=['POST'])
def edit_post(id):
    title = request.form.get('title')
    content = request.form.get('content')

    conn = get_db()
    cur = conn.cursor()
    try:
        # ВИКОРИСТАННЯ ТРИГЕРА: цей UPDATE автоматично оновить updated_at
        cur.execute('UPDATE posts SET title = %s, content = %s WHERE id = %s', (title, content, id))
        cur.execute('INSERT INTO audit_log (action) VALUES (%s)', (f"Редаговано пост ID {id}",))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
        return "Помилка редагування", 500
    finally:
        cur.close()

    return redirect(url_for('index'))


@app.route('/delete/<int:id>', methods=['POST'])
def delete_post(id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute('SELECT * FROM posts WHERE id = %s', (id,))
        post = cur.fetchone()

        if post:
            cur.execute('INSERT INTO archives (original_id, title, content) VALUES (%s, %s, %s)',
                        (post['id'], post['title'], post['content']))
            cur.execute('DELETE FROM posts WHERE id = %s', (id,))
            cur.execute('INSERT INTO audit_log (action) VALUES (%s)',
                        (f"Видалено та архівовано пост ID {id}",))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(e)
    finally:
        cur.close()

    return redirect(url_for('index'))


@app.route('/react/<int:id>/<string:action>', methods=['POST'])
def react_post(id, action):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute('SELECT title FROM posts WHERE id = %s', (id,))
        post = cur.fetchone()

        if post:
            if action == 'like':
                sql = 'UPDATE posts SET likes = likes + 1 WHERE id = %s'
                emoji = '👍'
            elif action == 'dislike':
                sql = 'UPDATE posts SET dislikes = dislikes + 1 WHERE id = %s'
                emoji = '👎'

            cur.execute(sql, (id,))
            log_msg = f"Реакція {emoji} на пост '{post['title']}'"
            cur.execute('INSERT INTO audit_log (action) VALUES (%s)', (log_msg,))
            conn.commit()

    except Exception as e:
        conn.rollback()
        print(e)
    finally:
        cur.close()

    return redirect(url_for('index'))


@app.route('/reset', methods=['POST'])
def reset_db():
    try:
        init_db()
        populate_db()
        return redirect(url_for('index'))
    except Exception as e:
        return f"Error: {e}", 500


@app.route('/test')
def test_yourself():
    options = ["Artem", "Shapoval", "ISD-31"]
    return random.choice(options)


if __name__ == '__main__':
    app.run(debug=True)