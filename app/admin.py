"""食材管理用の最小限の REST API + 簡易UI。

エンドポイント:
  GET    /                  食材一覧の管理画面 (HTML)
  GET    /api/ingredients   一覧
  POST   /api/ingredients   追加
  PUT    /api/ingredients/<id> 編集
  DELETE /api/ingredients/<id> 削除
  POST   /api/preview       現在の食材で1献立試し生成
  POST   /api/send-now      生成 + LINE 配信を即時実行
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template_string, request

from app.database import init_db, session_scope
from app.line_notifier import send_menu
from app.menu_generator import generate_menu, save_history
from app.models import Ingredient

VALID_CATEGORIES = {"main", "protein", "side", "drink"}

INDEX_HTML = """
<!doctype html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\">
<title>朝ごはん献立管理</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 12px;}
  table{width:100%;border-collapse:collapse;margin-bottom:16px;}
  th,td{border:1px solid #ddd;padding:6px 8px;font-size:14px;text-align:left;}
  th{background:#f4f4f4;}
  form{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-bottom:24px;}
  form input,form select{padding:6px;}
  button{padding:6px 12px;}
  .actions{display:flex;gap:8px;}
</style>
</head>
<body>
<h1>朝ごはん献立 管理</h1>

<h2>登録済み食材</h2>
<table id=\"ingredients\">
  <thead><tr><th>名前</th><th>カテゴリ</th><th>kcal/単位</th><th>標準量</th><th>範囲</th><th>有効</th><th></th></tr></thead>
  <tbody></tbody>
</table>

<h2>食材を追加</h2>
<form id=\"addForm\">
  <input name=\"name\" placeholder=\"名前 (例: 食パン)\" required>
  <select name=\"category\" required>
    <option value=\"main\">main(主食)</option>
    <option value=\"protein\">protein(たんぱく)</option>
    <option value=\"side\">side(副菜)</option>
    <option value=\"drink\">drink(飲み物)</option>
  </select>
  <input name=\"unit\" placeholder=\"単位 (例: 枚, g, ml)\" required>
  <input name=\"calories_per_unit\" type=\"number\" step=\"0.1\" placeholder=\"1単位あたり kcal\" required>
  <input name=\"default_portion\" type=\"number\" step=\"0.1\" placeholder=\"標準量\" required>
  <input name=\"min_portion\" type=\"number\" step=\"0.1\" placeholder=\"最小量\" required>
  <input name=\"max_portion\" type=\"number\" step=\"0.1\" placeholder=\"最大量\" required>
  <button type=\"submit\">追加</button>
</form>

<h2>動作確認</h2>
<div class=\"actions\">
  <button onclick=\"preview()\">献立プレビュー</button>
  <button onclick=\"sendNow()\">いますぐLINE送信</button>
</div>
<pre id=\"out\"></pre>

<script>
async function load(){
  const res = await fetch('/api/ingredients');
  const data = await res.json();
  const tbody = document.querySelector('#ingredients tbody');
  tbody.innerHTML = '';
  for(const ing of data){
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${ing.name}</td><td>${ing.category}</td>` +
      `<td>${ing.calories_per_unit}</td><td>${ing.default_portion}${ing.unit}</td>` +
      `<td>${ing.min_portion}〜${ing.max_portion}${ing.unit}</td>` +
      `<td>${ing.active ? '✓' : '×'}</td>` +
      `<td><button data-id=\"${ing.id}\" class=\"del\">削除</button></td>`;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll('.del').forEach(b => b.onclick = async () => {
    if(!confirm('削除しますか?')) return;
    await fetch('/api/ingredients/' + b.dataset.id, {method:'DELETE'});
    load();
  });
}
document.getElementById('addForm').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  for(const k of ['calories_per_unit','default_portion','min_portion','max_portion']) body[k] = Number(body[k]);
  const res = await fetch('/api/ingredients', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if(res.ok){ e.target.reset(); load(); } else { alert('追加失敗: ' + await res.text()); }
};
async function preview(){
  const res = await fetch('/api/preview', {method:'POST'});
  document.getElementById('out').textContent = JSON.stringify(await res.json(), null, 2);
}
async function sendNow(){
  if(!confirm('LINEへ即時送信します。よろしいですか?')) return;
  const res = await fetch('/api/send-now', {method:'POST'});
  document.getElementById('out').textContent = JSON.stringify(await res.json(), null, 2);
}
load();
</script>
</body></html>
"""


def _validate_payload(payload: dict) -> tuple[dict, str | None]:
    required = [
        "name",
        "category",
        "unit",
        "calories_per_unit",
        "default_portion",
        "min_portion",
        "max_portion",
    ]
    missing = [k for k in required if payload.get(k) in (None, "")]
    if missing:
        return {}, f"missing fields: {', '.join(missing)}"
    if payload["category"] not in VALID_CATEGORIES:
        return {}, f"category must be one of {sorted(VALID_CATEGORIES)}"
    cleaned = {
        "name": str(payload["name"]).strip(),
        "category": payload["category"],
        "unit": str(payload["unit"]).strip(),
        "calories_per_unit": float(payload["calories_per_unit"]),
        "default_portion": float(payload["default_portion"]),
        "min_portion": float(payload["min_portion"]),
        "max_portion": float(payload["max_portion"]),
        "active": bool(payload.get("active", True)),
    }
    if cleaned["min_portion"] > cleaned["max_portion"]:
        return {}, "min_portion must be <= max_portion"
    if cleaned["calories_per_unit"] < 0:
        return {}, "calories_per_unit must be >= 0"
    return cleaned, None


def create_app() -> Flask:
    init_db()
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(INDEX_HTML)

    @app.get("/api/ingredients")
    def list_ingredients():
        with session_scope() as s:
            rows = s.query(Ingredient).order_by(Ingredient.category, Ingredient.name).all()
            return jsonify([r.to_dict() for r in rows])

    @app.post("/api/ingredients")
    def create_ingredient():
        cleaned, err = _validate_payload(request.get_json(force=True))
        if err:
            return err, 400
        with session_scope() as s:
            ing = Ingredient(**cleaned)
            s.add(ing)
            s.flush()
            return jsonify(ing.to_dict()), 201

    @app.put("/api/ingredients/<int:ingredient_id>")
    def update_ingredient(ingredient_id: int):
        cleaned, err = _validate_payload(request.get_json(force=True))
        if err:
            return err, 400
        with session_scope() as s:
            ing = s.get(Ingredient, ingredient_id)
            if ing is None:
                return "not found", 404
            for k, v in cleaned.items():
                setattr(ing, k, v)
            s.flush()
            return jsonify(ing.to_dict())

    @app.delete("/api/ingredients/<int:ingredient_id>")
    def delete_ingredient(ingredient_id: int):
        with session_scope() as s:
            ing = s.get(Ingredient, ingredient_id)
            if ing is None:
                return "not found", 404
            s.delete(ing)
        return "", 204

    @app.post("/api/preview")
    def preview():
        with session_scope() as s:
            menu = generate_menu(s)
            return jsonify(menu.to_payload())

    @app.post("/api/send-now")
    def send_now():
        with session_scope() as s:
            menu = generate_menu(s)
            save_history(s, menu)
        send_menu(menu)
        return jsonify(menu.to_payload())

    return app
