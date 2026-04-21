"""管理 Web アプリ。

タブ構成:
  - ダッシュボード: プレビュー / LINE 即時送信
  - 食材管理:    追加 / 編集 / 削除 / 有効化切替
  - テンプレート: 配信文面の編集 + プレビュー

REST API:
  GET    /api/ingredients                一覧
  POST   /api/ingredients                追加
  PUT    /api/ingredients/<id>           編集
  DELETE /api/ingredients/<id>           削除
  GET    /api/template                   現在のアクティブテンプレ
  PUT    /api/template                   テンプレート本文を更新
  POST   /api/template/reset             既定に戻す
  POST   /api/template/preview           任意の本文+サンプルデータでプレビュー
  POST   /api/preview                    現在の食材で1献立試し生成
  POST   /api/send-now                   生成 + LINE 配信を即時実行
"""
from __future__ import annotations

import hmac

from flask import Flask, Response, jsonify, render_template_string, request

from app.ai_suggester import AISuggesterUnavailableError, is_available as ai_is_available, suggest_dishes
from app.config import ADMIN_PASSWORD, AUTO_SEED, CRON_SECRET
from app.database import init_db, session_scope
from app.line_notifier import send_breakfast
from app.menu_generator import generate_breakfast, save_history
from app.models import Ingredient, MessageTemplate
from app.seed_data import seed_default_ingredients
from app.template_renderer import (
    AVAILABLE_VARIABLES,
    DEFAULT_TEMPLATE_BODY,
    DEFAULT_TEMPLATE_NAME,
    ensure_default_template,
    get_active_body,
    render,
    sample_menus,
    strict_render,
)

VALID_CATEGORIES = {"main", "protein", "side", "drink"}
CATEGORY_LABEL = {
    "main": "主食",
    "protein": "たんぱく",
    "side": "副菜",
    "drink": "飲み物",
}

INDEX_HTML = """
<!doctype html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>朝ごはん献立 管理</title>
<style>
  :root { --bg:#fafaf7; --fg:#222; --muted:#666; --accent:#ff8a4c; --border:#e0ddd5; }
  *{box-sizing:border-box}
  body{font-family:system-ui,-apple-system,\"Hiragino Kaku Gothic ProN\",sans-serif;margin:0;background:var(--bg);color:var(--fg);}
  header{background:#fff;border-bottom:1px solid var(--border);padding:16px 20px;}
  header h1{margin:0;font-size:18px;}
  nav{background:#fff;border-bottom:1px solid var(--border);display:flex;}
  nav button{background:none;border:0;padding:14px 20px;font-size:14px;cursor:pointer;color:var(--muted);border-bottom:3px solid transparent;}
  nav button.active{color:var(--accent);border-color:var(--accent);font-weight:600;}
  main{max-width:900px;margin:24px auto;padding:0 16px;}
  section{display:none;}
  section.active{display:block;}
  h2{font-size:16px;margin:24px 0 12px;}
  .card{background:#fff;border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px;}
  table{width:100%;border-collapse:collapse;background:#fff;}
  th,td{border-bottom:1px solid var(--border);padding:10px 8px;font-size:13px;text-align:left;}
  th{background:#f4f2ec;font-weight:600;}
  tr:last-child td{border-bottom:0;}
  .row{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px;}
  .row input,.row select{padding:8px;font-size:13px;border:1px solid var(--border);border-radius:4px;}
  textarea{width:100%;min-height:220px;font-family:\"SF Mono\",Menlo,monospace;font-size:13px;padding:10px;border:1px solid var(--border);border-radius:4px;}
  button.primary{background:var(--accent);color:#fff;border:0;padding:10px 16px;border-radius:4px;font-size:14px;cursor:pointer;}
  button.secondary{background:#fff;color:var(--fg);border:1px solid var(--border);padding:10px 16px;border-radius:4px;font-size:14px;cursor:pointer;}
  button.danger{background:#fff;color:#c43;border:1px solid #f0cfc5;padding:6px 10px;border-radius:4px;font-size:12px;cursor:pointer;}
  button.small{padding:4px 10px;font-size:12px;border-radius:4px;cursor:pointer;}
  button.small.primary{background:var(--accent);color:#fff;border:0;}
  button.small.secondary{background:#fff;color:var(--fg);border:1px solid var(--border);}
  td.edit input,td.edit select{width:100%;padding:4px;font-size:12px;border:1px solid var(--border);border-radius:3px;box-sizing:border-box;}
  td.edit .range{display:flex;gap:2px;align-items:center;}
  td.edit .range input{width:50%;}
  .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}
  pre.preview{background:#f9f6ef;border:1px solid var(--border);border-radius:4px;padding:14px;white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.7;}
  .muted{color:var(--muted);font-size:12px;}
  .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#eee6d9;color:#6c5a3d;}
  .badge.inactive{background:#eee;color:#888;}
  .help{background:#fff7ef;border:1px solid #f5d9b8;border-radius:4px;padding:10px 12px;font-size:12px;margin:10px 0;}
  .help code{background:rgba(0,0,0,.06);padding:1px 5px;border-radius:3px;}
  .group{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
  @media (max-width:640px){ .row{grid-template-columns:repeat(2,1fr);} .group{grid-template-columns:1fr;} }
</style>
</head>
<body>
<header><h1>🍳 朝ごはん献立 管理</h1></header>
<nav>
  <button data-tab=\"dashboard\" class=\"active\">ダッシュボード</button>
  <button data-tab=\"ingredients\">食材</button>
  <button data-tab=\"ai\">AI提案</button>
  <button data-tab=\"template\">テンプレート</button>
</nav>
<main>

<section id=\"sec-dashboard\" class=\"active\">
  <div class=\"card\">
    <h2>本日の献立プレビュー</h2>
    <p class=\"muted\">現在の食材と有効テンプレートを使って1献立をシミュレートします。LINEへは送信されません。</p>
    <div class=\"actions\">
      <button class=\"primary\" onclick=\"preview()\">プレビュー生成</button>
      <button class=\"secondary\" onclick=\"sendNow()\">いますぐ LINE 送信</button>
    </div>
    <pre class=\"preview\" id=\"dashOut\">(未生成)</pre>
  </div>
</section>

<section id=\"sec-ingredients\">
  <div class=\"card\">
    <h2>食材を追加</h2>
    <form id=\"addForm\">
      <div class=\"row\">
        <input name=\"name\" placeholder=\"名前 (例: 食パン)\" required>
        <select name=\"category\" required>
          <option value=\"main\">主食</option>
          <option value=\"protein\">たんぱく</option>
          <option value=\"side\">副菜</option>
          <option value=\"drink\">飲み物</option>
        </select>
        <input name=\"unit\" placeholder=\"単位 (枚, g, ml)\" required>
        <input name=\"calories_per_unit\" type=\"number\" step=\"0.01\" placeholder=\"1単位あたり kcal\" required>
      </div>
      <div class=\"row\">
        <input name=\"default_portion\" type=\"number\" step=\"0.1\" placeholder=\"標準量\" required>
        <input name=\"min_portion\" type=\"number\" step=\"0.1\" placeholder=\"最小量\" required>
        <input name=\"max_portion\" type=\"number\" step=\"0.1\" placeholder=\"最大量\" required>
        <button type=\"submit\" class=\"primary\">追加</button>
      </div>
    </form>
  </div>
  <div class=\"card\">
    <h2>登録済み食材</h2>
    <table id=\"ingredients\">
      <thead><tr><th>名前</th><th>カテゴリ</th><th>kcal/単位</th><th>標準量</th><th>範囲</th><th>状態</th><th></th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section id=\"sec-ai\">
  <div class=\"card\">
    <h2>AI 料理提案</h2>
    <p class=\"muted\">登録済み食材を元に、Claude が簡単な朝食料理を提案します。良さそうなものは「食材として登録」で反映できます。</p>
    <div class=\"row\" style=\"grid-template-columns:1fr auto auto;\">
      <input id=\"aiExtra\" placeholder=\"追加食材(例: 梅干し, しゃけ) カンマ区切り・任意\">
      <input id=\"aiCount\" type=\"number\" min=\"1\" max=\"10\" value=\"5\" style=\"width:80px\">
      <button class=\"primary\" onclick=\"aiSuggest()\">提案する</button>
    </div>
    <p class=\"muted\" id=\"aiStatus\"></p>
  </div>
  <div id=\"aiResults\"></div>
</section>

<section id=\"sec-template\">
  <div class=\"card\">
    <h2>配信テンプレートの編集</h2>
    <p class=\"muted\">Jinja2 構文で編集できます。<code>menus</code> は 700kcal / 300kcal の 2 要素配列です。保存すると次回の配信から反映されます。</p>
    <textarea id=\"tmplBody\"></textarea>
    <div class=\"actions\">
      <button class=\"primary\" onclick=\"saveTemplate()\">保存</button>
      <button class=\"secondary\" onclick=\"previewTemplate()\">プレビュー</button>
      <button class=\"secondary\" onclick=\"resetTemplate()\">既定に戻す</button>
    </div>
    <div class=\"help\">
      <strong>使える変数</strong>
      <ul id=\"varList\" style=\"margin:6px 0 0 18px;padding:0;\"></ul>
    </div>
  </div>
  <div class=\"card\">
    <h2>プレビュー(サンプル献立で描画)</h2>
    <pre class=\"preview\" id=\"tmplOut\">(未プレビュー)</pre>
  </div>
</section>

</main>
<script>
const tabs = document.querySelectorAll('nav button');
const sections = document.querySelectorAll('main section');
tabs.forEach(b => b.onclick = () => {
  tabs.forEach(x => x.classList.remove('active'));
  sections.forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  document.getElementById('sec-' + b.dataset.tab).classList.add('active');
  if(b.dataset.tab === 'template') loadTemplate();
  if(b.dataset.tab === 'ingredients') loadIngredients();
  if(b.dataset.tab === 'ai') checkAiStatus();
});

const CATEGORY_LABEL = {main:'主食',protein:'たんぱく',side:'副菜',drink:'飲み物'};

async function loadIngredients(){
  const res = await fetch('/api/ingredients');
  const data = await res.json();
  const tbody = document.querySelector('#ingredients tbody');
  tbody.innerHTML = '';
  for(const ing of data){
    tbody.appendChild(renderViewRow(ing));
  }
}

function renderViewRow(ing){
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${escapeHtml(ing.name)}</td>` +
    `<td>${CATEGORY_LABEL[ing.category] || ing.category}</td>` +
    `<td>${ing.calories_per_unit}</td>` +
    `<td>${ing.default_portion}${escapeHtml(ing.unit)}</td>` +
    `<td>${ing.min_portion}〜${ing.max_portion}${escapeHtml(ing.unit)}</td>` +
    `<td><span class="badge ${ing.active?'':'inactive'}">${ing.active?'有効':'無効'}</span></td>` +
    `<td><button class="small secondary" data-act="edit">編集</button> <button class="danger" data-act="delete">削除</button></td>`;
  tr.querySelector('[data-act=edit]').onclick = () => tr.replaceWith(renderEditRow(ing));
  tr.querySelector('[data-act=delete]').onclick = async () => {
    if(!confirm(`${ing.name} を削除しますか?`)) return;
    const res = await fetch('/api/ingredients/' + ing.id, {method:'DELETE'});
    if(res.ok) loadIngredients();
    else alert('削除失敗: ' + await res.text());
  };
  return tr;
}

function renderEditRow(ing){
  const tr = document.createElement('tr');
  const catOptions = ['main','protein','side','drink']
    .map(c => `<option value="${c}" ${c===ing.category?'selected':''}>${CATEGORY_LABEL[c]}</option>`)
    .join('');
  tr.innerHTML = `
    <td class="edit"><input name="name" value="${escapeHtml(ing.name)}"></td>
    <td class="edit"><select name="category">${catOptions}</select></td>
    <td class="edit"><input name="calories_per_unit" type="number" step="0.01" value="${ing.calories_per_unit}"></td>
    <td class="edit"><div class="range"><input name="default_portion" type="number" step="0.1" value="${ing.default_portion}"><input name="unit" value="${escapeHtml(ing.unit)}" style="width:40%"></div></td>
    <td class="edit"><div class="range"><input name="min_portion" type="number" step="0.1" value="${ing.min_portion}"><span>〜</span><input name="max_portion" type="number" step="0.1" value="${ing.max_portion}"></div></td>
    <td class="edit"><label style="font-size:12px;"><input type="checkbox" name="active" ${ing.active?'checked':''}> 有効</label></td>
    <td><button class="small primary" data-act="save">保存</button> <button class="small secondary" data-act="cancel">取消</button></td>
  `;
  tr.querySelector('[data-act=save]').onclick = async () => {
    const get = (n) => tr.querySelector(`[name="${n}"]`);
    const body = {
      name: get('name').value.trim(),
      category: get('category').value,
      unit: get('unit').value.trim(),
      calories_per_unit: Number(get('calories_per_unit').value),
      default_portion: Number(get('default_portion').value),
      min_portion: Number(get('min_portion').value),
      max_portion: Number(get('max_portion').value),
      active: get('active').checked,
    };
    const res = await fetch('/api/ingredients/' + ing.id, {
      method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if(res.ok) loadIngredients();
    else alert('保存失敗: ' + await res.text());
  };
  tr.querySelector('[data-act=cancel]').onclick = () => tr.replaceWith(renderViewRow(ing));
  return tr;
}
document.getElementById('addForm').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  for(const k of ['calories_per_unit','default_portion','min_portion','max_portion']) body[k] = Number(body[k]);
  const res = await fetch('/api/ingredients', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if(res.ok){ e.target.reset(); loadIngredients(); } else { alert('追加失敗: ' + await res.text()); }
};

async function loadTemplate(){
  const res = await fetch('/api/template');
  const data = await res.json();
  document.getElementById('tmplBody').value = data.body;
  const ul = document.getElementById('varList');
  ul.innerHTML = '';
  for(const v of data.variables){
    const li = document.createElement('li');
    li.innerHTML = `<code>${escapeHtml(v.name)}</code> — ${escapeHtml(v.description)}`;
    ul.appendChild(li);
  }
}
async function saveTemplate(){
  const body = document.getElementById('tmplBody').value;
  const res = await fetch('/api/template', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({body})});
  if(res.ok){ await previewTemplate(); alert('保存しました'); } else { alert('保存失敗: ' + await res.text()); }
}
async function previewTemplate(){
  const body = document.getElementById('tmplBody').value;
  const res = await fetch('/api/template/preview', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({body})});
  const data = await res.json();
  document.getElementById('tmplOut').textContent = data.preview;
}
async function resetTemplate(){
  if(!confirm('テンプレートを既定に戻しますか?')) return;
  const res = await fetch('/api/template/reset', {method:'POST'});
  if(res.ok){ loadTemplate(); }
}
async function preview(){
  const res = await fetch('/api/preview', {method:'POST'});
  const data = await res.json();
  document.getElementById('dashOut').textContent = data.rendered + '\\n\\n― 生成内容 ―\\n' + JSON.stringify(data.menus, null, 2);
}
async function sendNow(){
  if(!confirm('LINEへ即時送信します。よろしいですか?')) return;
  const res = await fetch('/api/send-now', {method:'POST'});
  const data = await res.json();
  document.getElementById('dashOut').textContent = data.rendered + '\\n\\n(送信しました)';
}
function escapeHtml(s){ return String(s).replace(/[&<>\"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;','\\'':'&#39;' })[c]); }

async function checkAiStatus(){
  const res = await fetch('/api/ai/status');
  const data = await res.json();
  const el = document.getElementById('aiStatus');
  if(!data.available){
    el.textContent = '⚠️ ANTHROPIC_API_KEY が未設定です。Vercel の Environment Variables で登録してください。';
    el.style.color = '#c43';
  } else {
    el.textContent = '';
  }
}
async function aiSuggest(){
  const extraRaw = document.getElementById('aiExtra').value.trim();
  const n = Number(document.getElementById('aiCount').value || 5);
  let ingredients = null;
  if(extraRaw){
    // 追加入力があれば、既存食材 + 追加食材をマージして渡す
    const existing = await (await fetch('/api/ingredients')).json();
    const extra = extraRaw.split(/[,\\u3001]/).map(s => s.trim()).filter(Boolean);
    ingredients = [...existing.map(i => i.name), ...extra];
  }
  const results = document.getElementById('aiResults');
  results.innerHTML = '<div class=\"card muted\">提案中...</div>';
  const res = await fetch('/api/ai/suggest', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ingredients, n}),
  });
  if(!res.ok){
    results.innerHTML = `<div class=\"card\" style=\"color:#c43\">失敗: ${escapeHtml(await res.text())}</div>`;
    return;
  }
  const data = await res.json();
  if(!data.dishes || data.dishes.length === 0){
    results.innerHTML = '<div class=\"card muted\">提案が得られませんでした。</div>';
    return;
  }
  results.innerHTML = '';
  for(const dish of data.dishes){
    const card = document.createElement('div');
    card.className = 'card';
    const uses = (dish.uses_ingredients || []).map(escapeHtml).join(', ');
    card.innerHTML = `
      <div style=\"display:flex;justify-content:space-between;align-items:baseline;gap:8px;\">
        <strong>${escapeHtml(dish.name)}</strong>
        <span class=\"badge\">${CATEGORY_LABEL[dish.category] || dish.category}</span>
      </div>
      <div class=\"muted\" style=\"margin:4px 0 8px;\">${escapeHtml(dish.description || '')}</div>
      <div style=\"font-size:12px;color:#555;\">使う食材: ${uses || '—'}</div>
      <div style=\"font-size:12px;color:#555;\">目安: ${dish.default_portion}${escapeHtml(dish.unit)} / ${dish.calories_per_unit} kcal/単位 (${dish.min_portion}〜${dish.max_portion}${escapeHtml(dish.unit)})</div>
      <div class=\"actions\"><button class=\"small primary\">食材として登録</button></div>
    `;
    card.querySelector('button').onclick = async () => {
      const body = {
        name: dish.name,
        category: dish.category,
        unit: dish.unit,
        calories_per_unit: Number(dish.calories_per_unit),
        default_portion: Number(dish.default_portion),
        min_portion: Number(dish.min_portion),
        max_portion: Number(dish.max_portion),
      };
      const r = await fetch('/api/ingredients', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      if(r.ok){ card.querySelector('button').disabled = true; card.querySelector('button').textContent = '登録済み'; }
      else { alert('登録失敗: ' + await r.text()); }
    };
    results.appendChild(card);
  }
}
loadIngredients();
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


def _bootstrap_db() -> None:
    """初回起動(or コールドスタート)時の自動初期化。

    - テーブル作成
    - デフォルトテンプレート投入
    - AUTO_SEED=1 かつ食材 0 件なら seed_default_ingredients を実行
    全て冪等。既に入っているデータは上書きしない。
    """
    init_db()
    with session_scope() as s:
        ensure_default_template(s)
    if AUTO_SEED:
        with session_scope() as s:
            if s.query(Ingredient).count() == 0:
                seed_default_ingredients()


def create_app() -> Flask:
    _bootstrap_db()
    app = Flask(__name__)

    @app.before_request
    def _require_basic_auth():
        if not ADMIN_PASSWORD:
            return None
        # Cron エンドポイントは CRON_SECRET で別途認証
        if request.path.startswith("/api/cron/"):
            return None
        auth = request.authorization
        if auth and auth.password and hmac.compare_digest(auth.password, ADMIN_PASSWORD):
            return None
        return Response(
            "認証が必要です",
            401,
            {"WWW-Authenticate": 'Basic realm="Breakfast admin"'},
        )

    @app.get("/")
    def index():
        return render_template_string(INDEX_HTML)

    # ---- ingredients ----
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

    # ---- template ----
    @app.get("/api/template")
    def get_template():
        with session_scope() as s:
            body = get_active_body(s)
        return jsonify(
            {
                "body": body,
                "variables": [{"name": n, "description": d} for n, d in AVAILABLE_VARIABLES],
            }
        )

    @app.put("/api/template")
    def update_template():
        payload = request.get_json(force=True) or {}
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip():
            return "body must be a non-empty string", 400
        # 保存前に構文チェック(エラーは400で返して編集中の事故を防ぐ)
        try:
            strict_render(body, sample_menus())
        except Exception as exc:  # noqa: BLE001
            return f"template render failed: {exc}", 400
        with session_scope() as s:
            active = (
                s.query(MessageTemplate).filter(MessageTemplate.is_active.is_(True)).first()
            )
            if active is None:
                active = MessageTemplate(name=DEFAULT_TEMPLATE_NAME, body=body, is_active=True)
                s.add(active)
            else:
                active.body = body
            s.flush()
            return jsonify(active.to_dict())

    @app.post("/api/template/reset")
    def reset_template():
        with session_scope() as s:
            active = (
                s.query(MessageTemplate).filter(MessageTemplate.is_active.is_(True)).first()
            )
            if active is None:
                active = MessageTemplate(
                    name=DEFAULT_TEMPLATE_NAME, body=DEFAULT_TEMPLATE_BODY, is_active=True
                )
                s.add(active)
            else:
                active.body = DEFAULT_TEMPLATE_BODY
            s.flush()
            return jsonify(active.to_dict())

    @app.post("/api/template/preview")
    def preview_template():
        payload = request.get_json(force=True) or {}
        body = payload.get("body") or DEFAULT_TEMPLATE_BODY
        try:
            rendered = strict_render(body, sample_menus())
        except Exception as exc:  # noqa: BLE001
            return f"render failed: {exc}", 400
        return jsonify({"preview": rendered})

    # ---- menu generation / delivery ----
    @app.post("/api/preview")
    def preview_menu():
        with session_scope() as s:
            menus = generate_breakfast(s)
            body = get_active_body(s)
        return jsonify({
            "menus": [m.to_payload() for m in menus],
            "rendered": render(body, menus),
        })

    @app.post("/api/send-now")
    def send_now():
        with session_scope() as s:
            menus = generate_breakfast(s)
            save_history(s, menus)
            body = get_active_body(s)
        send_breakfast(menus, template_body=body)
        return jsonify({
            "menus": [m.to_payload() for m in menus],
            "rendered": render(body, menus),
        })

    # ---- AI 料理提案 ----
    @app.get("/api/ai/status")
    def ai_status():
        return jsonify({"available": ai_is_available()})

    @app.post("/api/ai/suggest")
    def ai_suggest():
        payload = request.get_json(force=True) or {}
        ingredients = payload.get("ingredients")
        n = int(payload.get("n", 5))
        if ingredients is None:
            # 省略時は登録済みの active 食材名を使う
            with session_scope() as s:
                ingredients = [
                    name for (name,) in s.query(Ingredient.name)
                    .filter(Ingredient.active.is_(True))
                    .all()
                ]
        if not isinstance(ingredients, list):
            return "ingredients must be an array of strings", 400
        try:
            dishes = suggest_dishes(ingredients, n=n)
        except AISuggesterUnavailableError as exc:
            return str(exc), 503
        except Exception as exc:  # noqa: BLE001
            return f"AI suggestion failed: {exc}", 502
        return jsonify({"dishes": dishes})

    # ---- Vercel Cron からの定時配信 ----
    @app.route("/api/cron/send", methods=["GET", "POST"])
    def cron_send():
        if CRON_SECRET:
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {CRON_SECRET}"
            if not hmac.compare_digest(auth, expected):
                return "unauthorized", 401
        with session_scope() as s:
            menus = generate_breakfast(s)
            save_history(s, menus)
            body = get_active_body(s)
        send_breakfast(menus, template_body=body)
        return jsonify({
            "sent": True,
            "menus": [{
                "profile_name": m.profile_name,
                "menu_name": m.menu_name,
                "total_calories": m.total_calories,
                "is_fallback": m.is_fallback,
            } for m in menus],
        })

    return app
