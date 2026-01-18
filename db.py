import sqlite3

DB_PATH = "data/kakeibo.db"

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # expenses テーブルを重複OKに変更
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        item TEXT,
        amount INTEGER,
        billing TEXT,
        category TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        sort_order INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS category_items (
        category TEXT,
        item TEXT,
        UNIQUE(category, item)
    )
    """)

    # その他を最後に固定
    cur.execute("INSERT OR IGNORE INTO categories(name, sort_order) VALUES ('その他', 999)")

    conn.commit()
    conn.close()