"""管理 Web アプリ。

朝ごはん(/breakfast): ダッシュボード / 食材。配信文面は AI が出力したものを
そのまま使う方針で、テンプレ編集機能は持たない。
掃除(/cleaning): ダッシュボード / 担当者 / 場所 / テンプレート編集。
"""
from __future__ import annotations

import hmac

from flask import Flask, Response, jsonify, render_template_string, request

from app import cleaning as cleaning_mod
from app.ai_suggester import is_available as ai_is_available
from app.config import ADMIN_PASSWORD, AUTO_SEED, CRON_SECRET
from app.database import init_db, session_scope
from app.line_notifier import format_breakfast, send_breakfast
from app.menu_generator import generate_breakfast, save_history
from app.models import Cleaner, CleaningLocation, Ingredient, MessageTemplate
from app.seed_data import seed_default_ingredients

VALID_CATEGORIES = {"main", "protein", "side", "drink"}
CATEGORY_LABEL = {
    "main": "主食",
    "protein": "たんぱく",
    "side": "副菜",
    "drink": "飲み物",
}

LANDING_HTML = """
<!doctype html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>AIオカン</title>
<style>
  :root{--bg:#fdf7eb;--card:#fff;--fg:#3a2e22;--muted:#7a6a5a;--border:#e8dcc8;--accent:#d94876;--accent-soft:#fce3ec;--purple:#b49ed4;--tech:#6dbfd6;}
  *{box-sizing:border-box;}
  body{font-family:system-ui,-apple-system,\"Hiragino Kaku Gothic ProN\",\"Hiragino Maru Gothic ProN\",sans-serif;margin:0;background:var(--bg);color:var(--fg);min-height:100vh;display:flex;flex-direction:column;
    background-image:radial-gradient(circle at 90% 0%, #fce3ec 0%, transparent 40%), radial-gradient(circle at 0% 100%, #e7dcee 0%, transparent 40%);
  }
  header{padding:24px 20px 0;text-align:center;}
  .logo{display:inline-flex;align-items:baseline;gap:4px;font-weight:700;font-size:22px;}
  .logo .ai{color:var(--accent);letter-spacing:0.5px;}
  main{flex:1;padding:16px 16px 48px;}
  .hero{max-width:720px;margin:0 auto;text-align:center;}
  .avatar{width:min(280px,70vw);aspect-ratio:1/1;margin:8px auto 16px;border-radius:50%;overflow:hidden;background:linear-gradient(135deg,#fce3ec 0%,#e7dcee 100%);box-shadow:0 12px 30px -10px rgba(217,72,118,0.25);position:relative;}
  .avatar img{width:100%;height:100%;object-fit:cover;display:block;}
  .avatar.no-image::after{content:\"👩🏻‍🍳\";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:min(120px,30vw);}
  h1{margin:8px 0 4px;font-size:28px;letter-spacing:0.5px;}
  h1 .ai{color:var(--accent);}
  .tagline{color:var(--muted);margin:0 0 24px;font-size:14px;}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;max-width:720px;margin:24px auto 0;}
  a.card{display:block;background:var(--card);border:1px solid var(--border);border-radius:16px;padding:24px;text-decoration:none;color:var(--fg);transition:transform 0.1s,box-shadow 0.15s;text-align:left;}
  a.card:hover{transform:translateY(-3px);box-shadow:0 10px 24px -8px rgba(58,46,34,0.15);}
  a.card .emoji{font-size:40px;margin-bottom:8px;}
  a.card h2{margin:0 0 6px;font-size:18px;}
  a.card p{margin:0;color:var(--muted);font-size:13px;line-height:1.6;}
  a.card.breakfast{border-top:4px solid var(--accent);}
  a.card.cleaning{border-top:4px solid var(--purple);}
  footer{text-align:center;padding:16px;color:var(--muted);font-size:12px;}
</style>
</head>
<body>
<header><span class=\"logo\"><span class=\"ai\">AI</span>オカン</span></header>
<main>
  <section class=\"hero\">
    <div class=\"avatar\" id=\"avatar\"><img src=\"/static/ai-okan.png\" alt=\"AIオカン\" onerror=\"document.getElementById('avatar').classList.add('no-image');this.style.display='none';\"></div>
    <h1><span class=\"ai\">AI</span>オカン</h1>
    <p class=\"tagline\">先端技術で「小言」が最適化される — 朝ごはんも掃除も、オカンにおまかせ 🍳🧹</p>
  </section>
  <div class=\"grid\">
    <a class=\"card breakfast\" href=\"/breakfast\">
      <div class=\"emoji\">🍳</div>
      <h2>オカンの朝ごはん</h2>
      <p>素材を登録しとけば、毎朝 6:00 に AI オカンが献立を LINE で送ってくれるで。</p>
    </a>
    <a class=\"card cleaning\" href=\"/cleaning\">
      <div class=\"emoji\">🧹</div>
      <h2>オカンの掃除当番</h2>
      <p>担当者と場所を登録したら、毎週土曜 8:00 に AI オカンがランダムで割り振るわ。</p>
    </a>
  </div>
</main>
<footer>愛情ベース: 100% 💗</footer>
</body></html>
"""

INDEX_HTML = """
<!doctype html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>AIオカン — 朝ごはん</title>
<style>
  :root { --bg:#fdf7eb; --fg:#3a2e22; --muted:#7a6a5a; --accent:#d94876; --accent-soft:#fce3ec; --purple:#b49ed4; --border:#e8dcc8; }
  *{box-sizing:border-box}
  body{font-family:system-ui,-apple-system,\"Hiragino Kaku Gothic ProN\",\"Hiragino Maru Gothic ProN\",sans-serif;margin:0;background:var(--bg);color:var(--fg);}
  header{background:#fff;border-bottom:1px solid var(--border);padding:14px 20px;display:flex;align-items:center;gap:12px;}
  header .avatar{width:44px;height:44px;border-radius:50%;overflow:hidden;background:linear-gradient(135deg,#fce3ec,#e7dcee);flex:0 0 auto;position:relative;}
  header .avatar img{width:100%;height:100%;object-fit:cover;display:block;}
  header .avatar.no-image::after{content:\"👩🏻\";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:24px;}
  header h1{margin:0;font-size:16px;flex:1;}
  header h1 .ai{color:var(--accent);font-weight:700;}
  header a.home{display:inline-flex;align-items:center;gap:4px;padding:8px 14px;border-radius:999px;background:var(--accent-soft);color:var(--accent);text-decoration:none;font-size:13px;font-weight:600;border:1px solid #f4c0d2;white-space:nowrap;}
  header a.home:hover{background:var(--accent);color:#fff;}
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
  button[disabled]{opacity:0.5;cursor:not-allowed;}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid #eee;border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:-2px;margin-right:8px;}
  @keyframes spin{to{transform:rotate(360deg);}}
  .loading{display:flex;align-items:center;gap:8px;padding:14px;background:var(--accent-soft);border:1px solid #f4c0d2;border-radius:8px;font-size:13px;margin-top:12px;color:#8a2d4e;}
  .loading .sub{color:var(--muted);font-size:12px;}
  .source-ai{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:var(--accent-soft);color:#8a2d4e;}
  .source-rule{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#eee6d9;color:#6c5a3d;}
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
<header>
  <div class=\"avatar\" id=\"hAvatar\"><img src=\"/static/ai-okan.png\" alt=\"AIオカン\" onerror=\"document.getElementById('hAvatar').classList.add('no-image');this.style.display='none';\"></div>
  <h1><span class=\"ai\">AI</span>オカンの朝ごはん 🍳</h1>
  <a class=\"home\" href=\"/\">🏠 トップ</a>
</header>
<nav>
  <button data-tab=\"dashboard\" class=\"active\">ダッシュボード</button>
  <button data-tab=\"ingredients\">食材</button>
</nav>
<main>

<section id=\"sec-dashboard\" class=\"active\">
  <div class=\"card\">
    <h2>本日の献立プレビュー</h2>
    <p class=\"muted\">登録済みの素材から AI が 700kcal / 300kcal の朝食を組み立てます。LINEへは送信されません。</p>
    <p class=\"muted\" id=\"aiBadge\" style=\"margin:4px 0;\"></p>
    <div class=\"actions\">
      <button class=\"primary\" id=\"btnPreview\" onclick=\"preview()\">プレビュー生成</button>
      <button class=\"secondary\" id=\"btnSendNow\" onclick=\"sendNow()\">いますぐ LINE 送信</button>
    </div>
    <div class=\"loading\" id=\"dashLoading\" style=\"display:none;\">
      <span class=\"spinner\"></span>
      <div>
        <div id=\"dashLoadingMain\">🤖 AI が献立を考えています...</div>
        <div class=\"sub\" id=\"dashLoadingSub\">20〜40 秒ほどかかります</div>
      </div>
    </div>
    <div id=\"dashSource\" style=\"margin-top:12px;\"></div>
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

<div style=\"text-align:center;margin:32px 0 8px;\">
  <a href=\"/\" style=\"display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:999px;background:#fff;border:1px solid var(--border);color:var(--fg);text-decoration:none;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.04);\">🏠 トップに戻る</a>
</div>

</main>
<script>
const tabs = document.querySelectorAll('nav button');
const sections = document.querySelectorAll('main section');
tabs.forEach(b => b.onclick = () => {
  tabs.forEach(x => x.classList.remove('active'));
  sections.forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  document.getElementById('sec-' + b.dataset.tab).classList.add('active');
  if(b.dataset.tab === 'ingredients') loadIngredients();
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

function _setDashBusy(busy, mainText, subText){
  const loading = document.getElementById('dashLoading');
  const btns = [document.getElementById('btnPreview'), document.getElementById('btnSendNow')];
  btns.forEach(b => { if(b) b.disabled = busy; });
  if(busy){
    document.getElementById('dashLoadingMain').textContent = mainText || '🤖 AI が献立を考えています...';
    document.getElementById('dashLoadingSub').textContent = subText || '20〜40 秒ほどかかります';
    loading.style.display = 'flex';
    document.getElementById('dashSource').innerHTML = '';
  } else {
    loading.style.display = 'none';
  }
}
function _renderSourceBadges(menus){
  const wrap = document.getElementById('dashSource');
  wrap.innerHTML = '';
  for(const m of menus){
    const label = m.source === 'ai' ? 'AI 生成' : 'ルールベース';
    const cls = m.source === 'ai' ? 'source-ai' : 'source-rule';
    const span = document.createElement('span');
    span.className = cls;
    span.style.marginRight = '6px';
    span.textContent = `${m.profile_name}: ${label}`;
    wrap.appendChild(span);
  }
}
async function preview(){
  _setDashBusy(true);
  try {
    const res = await fetch('/api/preview', {method:'POST'});
    if(!res.ok){
      document.getElementById('dashOut').textContent = '失敗: ' + await res.text();
      return;
    }
    const data = await res.json();
    _renderSourceBadges(data.menus || []);
    document.getElementById('dashOut').textContent = data.rendered + '\\n\\n― 生成内容 ―\\n' + JSON.stringify(data.menus, null, 2);
  } finally {
    _setDashBusy(false);
  }
}
async function sendNow(){
  if(!confirm('LINEへ即時送信します。よろしいですか?')) return;
  _setDashBusy(true, '🤖 AI が献立を考え、LINE に送信します...', 'LINE の配信まで含めて 30〜60 秒ほどかかることがあります');
  try {
    const res = await fetch('/api/send-now', {method:'POST'});
    if(!res.ok){
      document.getElementById('dashOut').textContent = '失敗: ' + await res.text();
      return;
    }
    const data = await res.json();
    _renderSourceBadges(data.menus || []);
    document.getElementById('dashOut').textContent = data.rendered + '\\n\\n(送信しました)';
  } finally {
    _setDashBusy(false);
  }
}
function escapeHtml(s){ return String(s).replace(/[&<>\"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;','\\'':'&#39;' })[c]); }

// AI の有効/無効バッジをダッシュボードに出す
async function updateAiBadge(){
  const res = await fetch('/api/ai/status');
  const data = await res.json();
  const el = document.getElementById('aiBadge');
  if(!el) return;
  if(data.available){
    el.textContent = '🤖 AIオカンが考えてくれるで(AI 有効)';
    el.style.color = '#8a2d4e';
  } else {
    el.textContent = '⚠️ ANTHROPIC_API_KEY 未設定 — ルールベースで動作中';
    el.style.color = '#c43';
  }
}
loadIngredients();
updateAiBadge();
</script>
</body></html>
"""


CLEANING_HTML = """
<!doctype html>
<html lang=\"ja\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>AIオカン — 掃除当番</title>
<style>
  :root { --bg:#fdf7eb; --fg:#3a2e22; --muted:#7a6a5a; --accent:#8e74c4; --accent-soft:#ece3f6; --pink:#d94876; --border:#e8dcc8; }
  *{box-sizing:border-box}
  body{font-family:system-ui,-apple-system,\"Hiragino Kaku Gothic ProN\",\"Hiragino Maru Gothic ProN\",sans-serif;margin:0;background:var(--bg);color:var(--fg);}
  header{background:#fff;border-bottom:1px solid var(--border);padding:14px 20px;display:flex;align-items:center;gap:12px;}
  header .avatar{width:44px;height:44px;border-radius:50%;overflow:hidden;background:linear-gradient(135deg,#ece3f6,#fce3ec);flex:0 0 auto;position:relative;}
  header .avatar img{width:100%;height:100%;object-fit:cover;display:block;}
  header .avatar.no-image::after{content:\"👩🏻\";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:24px;}
  header h1{margin:0;font-size:16px;flex:1;}
  header h1 .ai{color:var(--pink);font-weight:700;}
  header a.home{display:inline-flex;align-items:center;gap:4px;padding:8px 14px;border-radius:999px;background:var(--accent-soft);color:var(--accent);text-decoration:none;font-size:13px;font-weight:600;border:1px solid #d4c0e8;white-space:nowrap;}
  header a.home:hover{background:var(--accent);color:#fff;}
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
  .row input,.row select,.row textarea{padding:8px;font-size:13px;border:1px solid var(--border);border-radius:4px;}
  textarea{width:100%;min-height:180px;font-family:\"SF Mono\",Menlo,monospace;font-size:13px;padding:10px;border:1px solid var(--border);border-radius:4px;}
  button.primary{background:var(--accent);color:#fff;border:0;padding:10px 16px;border-radius:4px;font-size:14px;cursor:pointer;}
  button.secondary{background:#fff;color:var(--fg);border:1px solid var(--border);padding:10px 16px;border-radius:4px;font-size:14px;cursor:pointer;}
  button.danger{background:#fff;color:#c43;border:1px solid #f0cfc5;padding:6px 10px;border-radius:4px;font-size:12px;cursor:pointer;}
  button.small{padding:4px 10px;font-size:12px;border-radius:4px;cursor:pointer;}
  button.small.primary{background:var(--accent);color:#fff;border:0;}
  button.small.secondary{background:#fff;color:var(--fg);border:1px solid var(--border);}
  button[disabled]{opacity:0.5;cursor:not-allowed;}
  .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;}
  pre.preview{background:#f4f9f7;border:1px solid var(--border);border-radius:4px;padding:14px;white-space:pre-wrap;word-break:break-word;font-size:13px;line-height:1.7;}
  .muted{color:var(--muted);font-size:12px;}
  .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#e7f0e3;color:#365;}
  .badge.inactive{background:#eee;color:#888;}
  .help{background:#f4f9f7;border:1px solid #bde0d8;border-radius:4px;padding:10px 12px;font-size:12px;margin:10px 0;}
  .help code{background:rgba(0,0,0,.06);padding:1px 5px;border-radius:3px;}
  .loading{display:flex;align-items:center;gap:8px;padding:14px;background:#f4f9f7;border:1px solid #bde0d8;border-radius:4px;font-size:13px;margin-top:12px;}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid #eee;border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;}
  @keyframes spin{to{transform:rotate(360deg);}}
  td.edit input,td.edit select,td.edit textarea{width:100%;padding:4px;font-size:12px;border:1px solid var(--border);border-radius:3px;box-sizing:border-box;}
  td.edit textarea{min-height:40px;font-family:inherit;}
  @media (max-width:640px){ .row{grid-template-columns:repeat(2,1fr);} }
</style>
</head>
<body>
<header>
  <div class=\"avatar\" id=\"hAvatar\"><img src=\"/static/ai-okan.png\" alt=\"AIオカン\" onerror=\"document.getElementById('hAvatar').classList.add('no-image');this.style.display='none';\"></div>
  <h1><span class=\"ai\">AI</span>オカンの掃除当番 🧹</h1>
  <a class=\"home\" href=\"/\">🏠 トップ</a>
</header>
<nav>
  <button data-tab=\"dashboard\" class=\"active\">ダッシュボード</button>
  <button data-tab=\"cleaners\">担当者</button>
  <button data-tab=\"locations\">場所</button>
  <button data-tab=\"template\">テンプレート</button>
</nav>
<main>

<section id=\"sec-dashboard\" class=\"active\">
  <div class=\"card\">
    <h2>今週の割り当てプレビュー</h2>
    <p class=\"muted\">担当者 × 場所をランダムに割り当てます。LINEへは送信されません。</p>
    <div class=\"actions\">
      <button class=\"primary\" id=\"btnPreview\" onclick=\"preview()\">プレビュー生成</button>
      <button class=\"secondary\" id=\"btnSendNow\" onclick=\"sendNow()\">いますぐ LINE 送信</button>
    </div>
    <div class=\"loading\" id=\"cleanLoading\" style=\"display:none;\"><span class=\"spinner\"></span><div>生成中...</div></div>
    <pre class=\"preview\" id=\"dashOut\">(未生成)</pre>
  </div>
  <div class=\"card\">
    <h2>累積ポイント</h2>
    <table id=\"leaderboard\">
      <thead><tr><th>順位</th><th>担当者</th><th>累積ポイント</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section id=\"sec-cleaners\">
  <div class=\"card\">
    <h2>担当者を追加</h2>
    <form id=\"addCleaner\">
      <div class=\"row\" style=\"grid-template-columns:1fr auto;\">
        <input name=\"name\" placeholder=\"名前\" required>
        <button type=\"submit\" class=\"primary\">追加</button>
      </div>
    </form>
  </div>
  <div class=\"card\">
    <h2>登録済み担当者</h2>
    <table id=\"cleaners\">
      <thead><tr><th>名前</th><th>累積ポイント</th><th>状態</th><th></th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section id=\"sec-locations\">
  <div class=\"card\">
    <h2>掃除場所を追加</h2>
    <form id=\"addLocation\">
      <div class=\"row\" style=\"grid-template-columns:1fr 80px 1fr auto;\">
        <input name=\"name\" placeholder=\"掃除の場所 (例: キッチン)\" required>
        <input name=\"points\" type=\"number\" min=\"0\" placeholder=\"点数\" required>
        <input name=\"notes\" placeholder=\"備考 / 実施内容\">
        <button type=\"submit\" class=\"primary\">追加</button>
      </div>
    </form>
  </div>
  <div class=\"card\">
    <h2>登録済み掃除場所</h2>
    <table id=\"locations\">
      <thead><tr><th>場所</th><th>点数</th><th>実施内容</th><th>状態</th><th></th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</section>

<section id=\"sec-template\">
  <div class=\"card\">
    <h2>配信テンプレートの編集</h2>
    <p class=\"muted\">Jinja2 構文で編集できます。<code>assignments</code> は割り当ての配列です。</p>
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
    <h2>プレビュー(サンプル割り当てで描画)</h2>
    <pre class=\"preview\" id=\"tmplOut\">(未プレビュー)</pre>
  </div>
</section>

<div style=\"text-align:center;margin:32px 0 8px;\">
  <a href=\"/\" style=\"display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:999px;background:#fff;border:1px solid var(--border);color:var(--fg);text-decoration:none;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.04);\">🏠 トップに戻る</a>
</div>

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
  if(b.dataset.tab === 'cleaners') loadCleaners();
  if(b.dataset.tab === 'locations') loadLocations();
  if(b.dataset.tab === 'dashboard') loadLeaderboard();
});

function escapeHtml(s){ return String(s).replace(/[&<>\"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;','\\'':'&#39;' })[c]); }

// ----- Cleaners -----
async function loadCleaners(){
  const res = await fetch('/api/cleaners');
  const data = await res.json();
  const tbody = document.querySelector('#cleaners tbody');
  tbody.innerHTML = '';
  for(const c of data){ tbody.appendChild(renderCleanerView(c)); }
}
function renderCleanerView(c){
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${escapeHtml(c.name)}</td>` +
    `<td>${c.total_points}</td>` +
    `<td><span class=\"badge ${c.active?'':'inactive'}\">${c.active?'有効':'無効'}</span></td>` +
    `<td><button class=\"small secondary\" data-act=\"edit\">編集</button> <button class=\"danger\" data-act=\"delete\">削除</button></td>`;
  tr.querySelector('[data-act=edit]').onclick = () => tr.replaceWith(renderCleanerEdit(c));
  tr.querySelector('[data-act=delete]').onclick = async () => {
    if(!confirm(`${c.name} を削除しますか?`)) return;
    const r = await fetch('/api/cleaners/' + c.id, {method:'DELETE'});
    if(r.ok) loadCleaners(); else alert('失敗: ' + await r.text());
  };
  return tr;
}
function renderCleanerEdit(c){
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td class=\"edit\"><input name=\"name\" value=\"${escapeHtml(c.name)}\"></td>
    <td class=\"edit\"><input name=\"total_points\" type=\"number\" value=\"${c.total_points}\"></td>
    <td class=\"edit\"><label style=\"font-size:12px;\"><input type=\"checkbox\" name=\"active\" ${c.active?'checked':''}> 有効</label></td>
    <td><button class=\"small primary\" data-act=\"save\">保存</button> <button class=\"small secondary\" data-act=\"cancel\">取消</button></td>
  `;
  tr.querySelector('[data-act=save]').onclick = async () => {
    const body = {
      name: tr.querySelector('[name=name]').value.trim(),
      total_points: Number(tr.querySelector('[name=total_points]').value) || 0,
      active: tr.querySelector('[name=active]').checked,
    };
    const r = await fetch('/api/cleaners/' + c.id, {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if(r.ok) loadCleaners(); else alert('失敗: ' + await r.text());
  };
  tr.querySelector('[data-act=cancel]').onclick = () => tr.replaceWith(renderCleanerView(c));
  return tr;
}
document.getElementById('addCleaner').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  const r = await fetch('/api/cleaners', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if(r.ok){ e.target.reset(); loadCleaners(); } else { alert('失敗: ' + await r.text()); }
};

// ----- Locations -----
async function loadLocations(){
  const res = await fetch('/api/cleaning_locations');
  const data = await res.json();
  const tbody = document.querySelector('#locations tbody');
  tbody.innerHTML = '';
  for(const l of data){ tbody.appendChild(renderLocationView(l)); }
}
function renderLocationView(l){
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${escapeHtml(l.name)}</td>` +
    `<td>${l.points}</td>` +
    `<td>${escapeHtml(l.notes || '')}</td>` +
    `<td><span class=\"badge ${l.active?'':'inactive'}\">${l.active?'有効':'無効'}</span></td>` +
    `<td><button class=\"small secondary\" data-act=\"edit\">編集</button> <button class=\"danger\" data-act=\"delete\">削除</button></td>`;
  tr.querySelector('[data-act=edit]').onclick = () => tr.replaceWith(renderLocationEdit(l));
  tr.querySelector('[data-act=delete]').onclick = async () => {
    if(!confirm(`${l.name} を削除しますか?`)) return;
    const r = await fetch('/api/cleaning_locations/' + l.id, {method:'DELETE'});
    if(r.ok) loadLocations(); else alert('失敗: ' + await r.text());
  };
  return tr;
}
function renderLocationEdit(l){
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td class=\"edit\"><input name=\"name\" value=\"${escapeHtml(l.name)}\"></td>
    <td class=\"edit\"><input name=\"points\" type=\"number\" min=\"0\" value=\"${l.points}\"></td>
    <td class=\"edit\"><textarea name=\"notes\">${escapeHtml(l.notes || '')}</textarea></td>
    <td class=\"edit\"><label style=\"font-size:12px;\"><input type=\"checkbox\" name=\"active\" ${l.active?'checked':''}> 有効</label></td>
    <td><button class=\"small primary\" data-act=\"save\">保存</button> <button class=\"small secondary\" data-act=\"cancel\">取消</button></td>
  `;
  tr.querySelector('[data-act=save]').onclick = async () => {
    const body = {
      name: tr.querySelector('[name=name]').value.trim(),
      points: Number(tr.querySelector('[name=points]').value) || 0,
      notes: tr.querySelector('[name=notes]').value,
      active: tr.querySelector('[name=active]').checked,
    };
    const r = await fetch('/api/cleaning_locations/' + l.id, {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    if(r.ok) loadLocations(); else alert('失敗: ' + await r.text());
  };
  tr.querySelector('[data-act=cancel]').onclick = () => tr.replaceWith(renderLocationView(l));
  return tr;
}
document.getElementById('addLocation').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  body.points = Number(body.points);
  const r = await fetch('/api/cleaning_locations', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if(r.ok){ e.target.reset(); loadLocations(); } else { alert('失敗: ' + await r.text()); }
};

// ----- Template -----
async function loadTemplate(){
  const res = await fetch('/api/cleaning_template');
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
  const res = await fetch('/api/cleaning_template', {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify({body})});
  if(res.ok){ await previewTemplate(); alert('保存しました'); } else { alert('失敗: ' + await res.text()); }
}
async function previewTemplate(){
  const body = document.getElementById('tmplBody').value;
  const res = await fetch('/api/cleaning_template/preview', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({body})});
  const data = await res.json();
  document.getElementById('tmplOut').textContent = data.preview;
}
async function resetTemplate(){
  if(!confirm('テンプレートを既定に戻しますか?')) return;
  const res = await fetch('/api/cleaning_template/reset', {method:'POST'});
  if(res.ok){ loadTemplate(); }
}

// ----- Dashboard -----
function _setBusy(busy){
  const loading = document.getElementById('cleanLoading');
  const btns = [document.getElementById('btnPreview'), document.getElementById('btnSendNow')];
  btns.forEach(b => { if(b) b.disabled = busy; });
  loading.style.display = busy ? 'flex' : 'none';
}
async function preview(){
  _setBusy(true);
  try {
    const res = await fetch('/api/cleaning_preview', {method:'POST'});
    if(!res.ok){ document.getElementById('dashOut').textContent = '失敗: ' + await res.text(); return; }
    const data = await res.json();
    document.getElementById('dashOut').textContent = data.rendered + '\\n\\n― 割り当て ―\\n' + JSON.stringify(data.assignments, null, 2);
  } finally { _setBusy(false); }
}
async function sendNow(){
  if(!confirm('LINEへ即時送信します。よろしいですか?')) return;
  _setBusy(true);
  try {
    const res = await fetch('/api/cleaning_send_now', {method:'POST'});
    if(!res.ok){ document.getElementById('dashOut').textContent = '失敗: ' + await res.text(); return; }
    const data = await res.json();
    document.getElementById('dashOut').textContent = data.rendered + '\\n\\n(送信しました。ポイントも加算されました)';
    loadLeaderboard();
  } finally { _setBusy(false); }
}
async function loadLeaderboard(){
  const res = await fetch('/api/cleaners');
  const data = await res.json();
  data.sort((a, b) => b.total_points - a.total_points);
  const tbody = document.querySelector('#leaderboard tbody');
  tbody.innerHTML = '';
  data.forEach((c, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${i + 1}</td><td>${escapeHtml(c.name)}</td><td>${c.total_points} pt</td>`;
    tbody.appendChild(tr);
  });
}
loadLeaderboard();
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
    """初回起動(or コールドスタート)時の自動初期化。"""
    init_db()
    with session_scope() as s:
        cleaning_mod.ensure_default_cleaning_template(s)
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
        return render_template_string(LANDING_HTML)

    @app.get("/breakfast")
    def breakfast_index():
        return render_template_string(INDEX_HTML)

    @app.get("/cleaning")
    def cleaning_index():
        return render_template_string(CLEANING_HTML)

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

    # ---- menu generation / delivery ----
    @app.post("/api/preview")
    def preview_menu():
        with session_scope() as s:
            menus = generate_breakfast(s)
        return jsonify({
            "menus": [m.to_payload() for m in menus],
            "rendered": format_breakfast(menus),
        })

    @app.post("/api/send-now")
    def send_now():
        with session_scope() as s:
            menus = generate_breakfast(s)
            save_history(s, menus)
        send_breakfast(menus)
        return jsonify({
            "menus": [m.to_payload() for m in menus],
            "rendered": format_breakfast(menus),
        })

    # ---- AI ステータス(UI にバッジを出すためだけに残す) ----
    @app.get("/api/ai/status")
    def ai_status():
        return jsonify({"available": ai_is_available()})

    # ==========================================================
    # 掃除当番機能
    # ==========================================================

    # ---- Cleaner CRUD ----
    def _validate_cleaner(payload: dict, require_name: bool = True) -> tuple[dict, str | None]:
        if not isinstance(payload, dict):
            return {}, "invalid payload"
        cleaned = {}
        if "name" in payload or require_name:
            name = str(payload.get("name") or "").strip()
            if not name:
                return {}, "name is required"
            cleaned["name"] = name
        if "total_points" in payload:
            try:
                cleaned["total_points"] = int(payload["total_points"])
            except (TypeError, ValueError):
                return {}, "total_points must be integer"
        if "active" in payload:
            cleaned["active"] = bool(payload["active"])
        return cleaned, None

    @app.get("/api/cleaners")
    def list_cleaners():
        with session_scope() as s:
            rows = s.query(Cleaner).order_by(Cleaner.id).all()
            return jsonify([r.to_dict() for r in rows])

    @app.post("/api/cleaners")
    def create_cleaner():
        cleaned, err = _validate_cleaner(request.get_json(force=True))
        if err:
            return err, 400
        with session_scope() as s:
            cleaner = Cleaner(**cleaned)
            s.add(cleaner)
            s.flush()
            return jsonify(cleaner.to_dict()), 201

    @app.put("/api/cleaners/<int:cleaner_id>")
    def update_cleaner(cleaner_id: int):
        cleaned, err = _validate_cleaner(request.get_json(force=True), require_name=False)
        if err:
            return err, 400
        with session_scope() as s:
            cleaner = s.get(Cleaner, cleaner_id)
            if cleaner is None:
                return "not found", 404
            for k, v in cleaned.items():
                setattr(cleaner, k, v)
            s.flush()
            return jsonify(cleaner.to_dict())

    @app.delete("/api/cleaners/<int:cleaner_id>")
    def delete_cleaner(cleaner_id: int):
        with session_scope() as s:
            cleaner = s.get(Cleaner, cleaner_id)
            if cleaner is None:
                return "not found", 404
            s.delete(cleaner)
        return "", 204

    # ---- CleaningLocation CRUD ----
    def _validate_location(payload: dict, require_all: bool = True) -> tuple[dict, str | None]:
        if not isinstance(payload, dict):
            return {}, "invalid payload"
        cleaned = {}
        if "name" in payload or require_all:
            name = str(payload.get("name") or "").strip()
            if not name:
                return {}, "name is required"
            cleaned["name"] = name
        if "points" in payload or require_all:
            try:
                points = int(payload.get("points", 0))
            except (TypeError, ValueError):
                return {}, "points must be integer"
            if points < 0:
                return {}, "points must be >= 0"
            cleaned["points"] = points
        if "notes" in payload or require_all:
            cleaned["notes"] = str(payload.get("notes") or "").strip()
        if "active" in payload:
            cleaned["active"] = bool(payload["active"])
        return cleaned, None

    @app.get("/api/cleaning_locations")
    def list_locations():
        with session_scope() as s:
            rows = s.query(CleaningLocation).order_by(CleaningLocation.id).all()
            return jsonify([r.to_dict() for r in rows])

    @app.post("/api/cleaning_locations")
    def create_location():
        cleaned, err = _validate_location(request.get_json(force=True))
        if err:
            return err, 400
        with session_scope() as s:
            loc = CleaningLocation(**cleaned)
            s.add(loc)
            s.flush()
            return jsonify(loc.to_dict()), 201

    @app.put("/api/cleaning_locations/<int:location_id>")
    def update_location(location_id: int):
        cleaned, err = _validate_location(request.get_json(force=True), require_all=False)
        if err:
            return err, 400
        with session_scope() as s:
            loc = s.get(CleaningLocation, location_id)
            if loc is None:
                return "not found", 404
            for k, v in cleaned.items():
                setattr(loc, k, v)
            s.flush()
            return jsonify(loc.to_dict())

    @app.delete("/api/cleaning_locations/<int:location_id>")
    def delete_location(location_id: int):
        with session_scope() as s:
            loc = s.get(CleaningLocation, location_id)
            if loc is None:
                return "not found", 404
            s.delete(loc)
        return "", 204

    # ---- 掃除テンプレート ----
    @app.get("/api/cleaning_template")
    def get_cleaning_template():
        with session_scope() as s:
            body = cleaning_mod.get_active_cleaning_body(s)
        return jsonify(
            {
                "body": body,
                "variables": [
                    {"name": n, "description": d}
                    for n, d in cleaning_mod.AVAILABLE_VARIABLES
                ],
            }
        )

    @app.put("/api/cleaning_template")
    def update_cleaning_template():
        payload = request.get_json(force=True) or {}
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip():
            return "body must be a non-empty string", 400
        try:
            cleaning_mod.strict_render(body, cleaning_mod.sample_assignments())
        except Exception as exc:  # noqa: BLE001
            return f"template render failed: {exc}", 400
        with session_scope() as s:
            active = (
                s.query(MessageTemplate)
                .filter(MessageTemplate.kind == "cleaning")
                .filter(MessageTemplate.is_active.is_(True))
                .first()
            )
            if active is None:
                active = MessageTemplate(
                    name=cleaning_mod.DEFAULT_CLEANING_TEMPLATE_NAME,
                    body=body,
                    is_active=True,
                    kind="cleaning",
                )
                s.add(active)
            else:
                active.body = body
            s.flush()
            return jsonify(active.to_dict())

    @app.post("/api/cleaning_template/reset")
    def reset_cleaning_template():
        with session_scope() as s:
            active = (
                s.query(MessageTemplate)
                .filter(MessageTemplate.kind == "cleaning")
                .filter(MessageTemplate.is_active.is_(True))
                .first()
            )
            if active is None:
                active = MessageTemplate(
                    name=cleaning_mod.DEFAULT_CLEANING_TEMPLATE_NAME,
                    body=cleaning_mod.DEFAULT_CLEANING_TEMPLATE_BODY,
                    is_active=True,
                    kind="cleaning",
                )
                s.add(active)
            else:
                active.body = cleaning_mod.DEFAULT_CLEANING_TEMPLATE_BODY
            s.flush()
            return jsonify(active.to_dict())

    @app.post("/api/cleaning_template/preview")
    def preview_cleaning_template():
        payload = request.get_json(force=True) or {}
        body = payload.get("body") or cleaning_mod.DEFAULT_CLEANING_TEMPLATE_BODY
        try:
            rendered = cleaning_mod.strict_render(body, cleaning_mod.sample_assignments())
        except Exception as exc:  # noqa: BLE001
            return f"render failed: {exc}", 400
        return jsonify({"preview": rendered})

    # ---- 掃除 割り当てプレビュー / 即時送信 ----
    @app.post("/api/cleaning_preview")
    def cleaning_preview():
        with session_scope() as s:
            assignments = cleaning_mod.generate_assignments(s)
            body = cleaning_mod.get_active_cleaning_body(s)
        return jsonify({
            "assignments": [a.to_payload() for a in assignments],
            "rendered": cleaning_mod.render(body, assignments),
        })

    @app.post("/api/cleaning_send_now")
    def cleaning_send_now():
        with session_scope() as s:
            assignments = cleaning_mod.generate_assignments(s)
            if assignments:
                cleaning_mod.save_history_and_update_points(s, assignments)
            body = cleaning_mod.get_active_cleaning_body(s)
        text = cleaning_mod.send_cleaning(assignments, template_body=body) if assignments else ""
        return jsonify({
            "assignments": [a.to_payload() for a in assignments],
            "rendered": text or cleaning_mod.render(body, assignments),
        })

    # ==========================================================
    # Vercel Cron からの定時配信
    # ==========================================================
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
        send_breakfast(menus)
        return jsonify({
            "sent": True,
            "menus": [{
                "profile_name": m.profile_name,
                "menu_name": m.menu_name,
                "total_calories": m.total_calories,
                "is_fallback": m.is_fallback,
            } for m in menus],
        })

    @app.route("/api/cron/cleaning", methods=["GET", "POST"])
    def cron_cleaning():
        if CRON_SECRET:
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {CRON_SECRET}"
            if not hmac.compare_digest(auth, expected):
                return "unauthorized", 401
        with session_scope() as s:
            assignments = cleaning_mod.generate_assignments(s)
            if assignments:
                cleaning_mod.save_history_and_update_points(s, assignments)
            body = cleaning_mod.get_active_cleaning_body(s)
        if assignments:
            cleaning_mod.send_cleaning(assignments, template_body=body)
        return jsonify({
            "sent": bool(assignments),
            "assignments": [a.to_payload() for a in assignments],
        })

    return app
