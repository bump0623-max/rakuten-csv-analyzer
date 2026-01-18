from flask import Flask, render_template, request, redirect, url_for, make_response
import pandas as pd
from db import init_db, get_db
from category_match import resolve_category

app = Flask(__name__)
init_db()

@app.route("/", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files["file"]
        billing = file.filename[5:11]


        df = pd.read_csv(file, usecols=["利用日", "利用店名・商品名", "利用金額"])
        df = df.rename(columns={
        "利用日": "date",
        "利用店名・商品名": "item",
        "利用金額": "amount"
        })


        df["billing"] = billing
        df["category"] = df["item"].apply(resolve_category)


        conn = get_db()
        df.to_sql("expenses", conn, if_exists="append", index=False)
        conn.commit()
        conn.close()


        return redirect(url_for("summary", yyyymm=billing))


    return render_template("upload.html")




@app.route("/summary/<yyyymm>")
def summary(yyyymm):
    conn = get_db()

    # 当月データ
    df = pd.read_sql(
        "SELECT * FROM expenses WHERE billing = ?",
        conn,
        params=(yyyymm,)
    )

    # 前月・次月計算
    year = int(yyyymm[:4])
    month = int(yyyymm[4:6])

    prev_yyyymm = f"{year-1}12" if month == 1 else f"{year}{month-1:02d}"
    next_yyyymm = f"{year+1}01" if month == 12 else f"{year}{month+1:02d}"

    def month_sum(b):
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE billing = ?", (b,))
        return cur.fetchone()[0]

    prev_enabled = month_sum(prev_yyyymm) > 0
    next_enabled = month_sum(next_yyyymm) > 0

    cur = conn.cursor()
    cur.execute("""
        SELECT name, color
        FROM categories
        ORDER BY sort_order
    """)
    rows = cur.fetchall()

    categories = []
    category_colors = {}

    for name, color in rows:
        categories.append(name)
        category_colors[name] = color

    # category別合計（まず辞書で作る）
    raw_pie = df.groupby("category")["amount"].sum().to_dict()

    pie = {}

    # カテゴリDB順で合計を作る
    for c in categories:
        pie[c] = int(df[df["category"] == c]["amount"].sum())

    conn.close()

    month_total = int(df["amount"].sum())

    pie_labels = list(pie.keys())
    pie_values = list(pie.values())

    print("PIE LABELS:", pie_labels)

    resp = make_response(render_template(
        "summary.html",
        yyyymm=yyyymm,
        data=df.to_dict("records"),
        pie_labels=pie_labels,
        pie_values=pie_values,
        category_colors=category_colors,
        prev_yyyymm=prev_yyyymm,
        next_yyyymm=next_yyyymm,
        prev_enabled=prev_enabled,
        next_enabled=next_enabled,
        categories=categories,
        month_total=month_total
    ))

    # キャッシュ無効化ヘッダを追加
    resp.headers["Cache-Control"] = "no-store"

    return resp



@app.route("/categories")
def categories():
    conn = get_db()
    cur = conn.cursor()

    # カテゴリ一覧（色つき・順番どおり・その他除外）
    cur.execute("""
        SELECT name, color
        FROM categories
        WHERE name != 'その他'
        ORDER BY sort_order
    """)
    category_rows = cur.fetchall()

    categories = []
    category_items = {}

    for name, color in category_rows:
        categories.append({
            "name": name,
            "color": color or "#cccccc"
        })
        category_items[name] = []

    # item 一覧
    cur.execute("""
        SELECT category, item
        FROM category_items
    """)
    for category, item in cur.fetchall():
        if category in category_items:
            category_items[category].append(item)

    conn.close()

    return render_template(
        "categories.html",
        categories=categories,
        category_items=category_items
    )



@app.route("/update_category", methods=["POST"])
def update_category():
    item = request.form["item"]
    category = request.form["category"]

    conn = get_db()
    cur = conn.cursor()

    # カテゴリがなければ作成
    cur.execute("""
        INSERT OR IGNORE INTO categories(name, sort_order)
        VALUES (
            ?,
            (
                SELECT MIN(t.n)
                FROM (
                    SELECT 1 AS n
                    UNION ALL
                    SELECT sort_order + 1
                    FROM categories
                    WHERE sort_order BETWEEN 1 AND 998
                ) t
                WHERE t.n NOT IN (
                    SELECT sort_order
                    FROM categories
                    WHERE sort_order BETWEEN 1 AND 998
                )
            )
        )
    """, (category,))

    # 既存の item 紐付けを一旦消す
    cur.execute(
        "DELETE FROM category_items WHERE item = ?",
        (item,)
    )

    # itemをカテゴリに再登録
    cur.execute(
        "INSERT INTO category_items(category, item) VALUES (?, ?)",
        (category, item)
    )

    # expenses 側も更新
    cur.execute(
        "UPDATE expenses SET category = ? WHERE item = ?",
        (category, item)
    )

    conn.commit()
    conn.close()

    return "OK"


@app.route("/delete_item_category", methods=["POST"])
def delete_item_category():
    item = request.form["item"]

    conn = get_db()
    cur = conn.cursor()

    # ① item の元カテゴリを取得
    cur.execute(
        "SELECT category FROM category_items WHERE item = ?",
        (item,)
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return "", 204

    old_category = row[0]

    # ② category_items から item を削除
    cur.execute(
        "DELETE FROM category_items WHERE item = ?",
        (item,)
    )

    # ③ expenses のカテゴリを「その他」に戻す
    cur.execute(
        "UPDATE expenses SET category = 'その他' WHERE item = ?",
        (item,)
    )

    # ④ そのカテゴリに item が残っているか確認
    cur.execute(
        "SELECT COUNT(*) FROM category_items WHERE category = ?",
        (old_category,)
    )
    count = cur.fetchone()[0]

    # ⑤ 0件ならカテゴリ削除（その他は消さない）
    if count == 0 and old_category != "その他":
        cur.execute(
            "DELETE FROM categories WHERE name = ?",
            (old_category,)
        )

    conn.commit()
    conn.close()

    return "", 204

    @app.get("/summary_debug")
    def summary_debug():
        con = sqlite3.connect("db.sqlite3")
        df = pd.read_sql("SELECT DISTINCT category FROM transactions", con)
        con.close()
        return df.to_dict(orient="records")

# 円グラフ色設定
@app.route("/update_category_color", methods=["POST"])
def update_category_color():
    category = request.form["category"]
    color = request.form["color"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE categories SET color = ? WHERE name = ?",
        (color, category)
    )
    conn.commit()
    conn.close()
    return "", 204


if __name__ == "__main__":
    app.run(debug=True)