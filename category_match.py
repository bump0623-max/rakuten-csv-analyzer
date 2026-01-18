from db import get_db

def resolve_category(item):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
    "SELECT category FROM category_items WHERE ? LIKE '%' || item || '%'",
    (item,)
    )
    row = cur.fetchone()
    conn.close()


    return row[0] if row else "その他"