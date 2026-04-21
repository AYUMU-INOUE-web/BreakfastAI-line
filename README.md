# 朝ごはん献立 LINE 配信アプリ

登録した食材から毎朝 7:00 に合計 **700kcal 前後** の朝食献立を自動生成し、LINE で通知する Python アプリ。

## 特徴

- 食材ごとにカロリー・単位・分量範囲を管理 (CRUD)
- 許容 **650〜750kcal** のランダム献立を自動生成
- 直近 **3日以内と同じ献立は回避**(飽きずに食べられる)
- 生成に失敗した場合は **固定の代替メニュー** を配信
- **配信テンプレートを Web UI から編集可能**(Jinja2)
- 食材の追加 / 編集 / 削除を Web UI から操作可能
- 管理画面 (Flask) からプレビュー / 即時送信が可能

## 構成

```
.
├── app/
│   ├── admin.py              # 管理用 Flask Web アプリ + REST API
│   ├── config.py             # 環境変数読み込み
│   ├── database.py           # SQLAlchemy セッション管理
│   ├── line_notifier.py      # LINE Messaging API 連携
│   ├── menu_generator.py     # 献立生成ロジック
│   ├── models.py             # Ingredient / MenuHistory / MessageTemplate
│   ├── scheduler.py          # APScheduler 毎朝 7:00 起動
│   ├── seed_data.py          # サンプル食材
│   └── template_renderer.py  # Jinja2 テンプレート描画
├── tests/                  # pytest
├── main.py                 # エントリーポイント (serve / send-now / seed)
├── requirements.txt
└── .env.example
```

## セットアップ

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env を編集: LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を設定
python main.py seed        # サンプル食材を投入
```

## 使い方

### 1. 常駐サーバで運用

```bash
python main.py serve
```

- `http://localhost:5000/` … Web 管理アプリ(3タブ)
  - **ダッシュボード**: 献立プレビュー / LINE 即時送信
  - **食材**: 追加 / 削除 / 一覧
  - **テンプレート**: 配信文面編集 + リアルタイムプレビュー
- 毎朝 7:00(`TIMEZONE` / `NOTIFY_HOUR` で変更可)に LINE 配信

### 2. cron / systemd タイマーから単発実行

APScheduler を使わず OS のスケジューラに任せる場合:

```bash
# 例: crontab -e
0 7 * * * /path/to/.venv/bin/python /path/to/main.py send-now >> /var/log/breakfast.log 2>&1
```

### 3. GitHub Actions から一時公開 URL で開く

手元に環境がなくてもブラウザから管理 UI を開けます。

1. リポジトリ → `Actions` タブ → `Admin UI (tunnel)` を選択
2. `Run workflow` を押して、稼働時間(分)を指定して実行
3. ジョブのサマリに `https://xxx.trycloudflare.com` という URL が表示されるのでタップ
4. 管理 UI(ダッシュボード / 食材 / テンプレート)が開く
5. 終了は Actions 画面の `Cancel workflow` を押すか、指定時間経過で自動停止

制約:
- URL は起動ごとに変わる(Cloudflare Quick Tunnel)
- ジョブ終了と同時に DB は消える(編集内容は引き継がれない)
- 最大 6 時間(GitHub Actions の上限)
- アクセス制御なし → URL の取り扱いに注意

### 4. 食材 API (curl サンプル)

```bash
curl -X POST http://localhost:5000/api/ingredients \
  -H 'Content-Type: application/json' \
  -d '{"name":"食パン","category":"main","unit":"枚","calories_per_unit":160,
       "default_portion":1,"min_portion":1,"max_portion":2}'
```

カテゴリは `main` / `protein` / `side` / `drink` の 4 種類。各カテゴリから 1 品ずつ選んで献立を組む。

## 環境変数

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `LINE_CHANNEL_ACCESS_TOKEN` | (必須) | LINE Messaging API のチャネルアクセストークン |
| `LINE_USER_ID` | (必須) | 配信先ユーザー ID |
| `DATABASE_URL` | `sqlite:///breakfast.db` | SQLAlchemy 接続文字列 |
| `NOTIFY_HOUR` / `NOTIFY_MINUTE` | `7` / `0` | 配信時刻 |
| `TIMEZONE` | `Asia/Tokyo` | スケジューラの TZ |
| `ADMIN_HOST` / `ADMIN_PORT` | `0.0.0.0` / `5000` | 管理 UI 待ち受け |

## テスト

```bash
.venv/bin/python -m pytest -q
```

## LINE 通知サンプル

```
🍳 きょうの朝ごはん
《食パンを中心とした朝ごはん》
合計カロリー: 692 kcal
─────────────
・食パン(6枚切): 1枚 (160 kcal)
・目玉焼き: 1個 (110 kcal)
・バナナ: 1本 (90 kcal)
・牛乳: 200ml (134 kcal)

今日も一日がんばろう!
```

## 配信テンプレート

配信文面は Jinja2 テンプレートで、Web UI の **「テンプレート」タブ** から編集できます。
保存前に構文チェックが走るので壊れたテンプレートは保存できません。

利用できる変数:

| 変数 | 説明 |
| --- | --- |
| `menu_name` | 献立の名前 |
| `total_calories` | 合計カロリー(小数) |
| `total_calories_int` | 合計カロリー(整数丸め) |
| `is_fallback` | 代替メニューかどうか |
| `items` | 食材リスト。各要素は `name / portion / portion_display / unit / calories / calories_int` |
| `date` | 配信日 `YYYY-MM-DD` |

既定テンプレート(`app/template_renderer.py` の `DEFAULT_TEMPLATE_BODY`):

```
🍳 きょうの朝ごはん{% if is_fallback %}(代替メニュー){% endif %}
《{{ menu_name }}》
合計カロリー: {{ total_calories_int }} kcal
─────────────
{% for item in items -%}
・{{ item.name }}: {{ item.portion_display }}{{ item.unit }} ({{ item.calories_int }} kcal)
{% endfor %}
今日も一日がんばろう!
```

## 献立生成アルゴリズム(概要)

1. 有効な食材をカテゴリ別に分類
2. 必須カテゴリがすべて揃わなければ代替メニューを返す
3. 最大 200 回試行:
   - 各カテゴリから 1 品ずつランダム選択
   - `min_portion`〜`max_portion` を 5 段階に量子化して分量を決定
   - 直近 3 日と同じ食材+分量の組み合わせはスキップ
   - 合計 650〜750kcal に収まれば採用
4. 範囲内で見つからなかった場合、700kcal ±15% に最も近い候補で妥協
5. それも無ければ代替の固定メニューを返す
