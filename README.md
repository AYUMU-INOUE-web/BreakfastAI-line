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
├── api/
│   └── index.py              # Vercel Serverless 関数エントリ
├── app/
│   ├── admin.py              # 管理用 Flask Web アプリ + REST API
│   ├── config.py             # 環境変数読み込み
│   ├── database.py           # SQLAlchemy(SQLite / Postgres)
│   ├── line_notifier.py      # LINE Messaging API 連携
│   ├── menu_generator.py     # 献立生成ロジック
│   ├── models.py             # Ingredient / MenuHistory / MessageTemplate
│   ├── scheduler.py          # APScheduler(ローカル/VPS 運用用)
│   ├── seed_data.py          # サンプル食材
│   └── template_renderer.py  # Jinja2 テンプレート描画
├── tests/                    # pytest
├── main.py                   # ローカル/CI 用エントリ (serve/send-now/seed)
├── vercel.json               # Vercel ルーティング + Cron 設定
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

## Vercel にデプロイして友人と共有する

固定 URL・編集永続化・Cron 配信込みで公開運用するための手順。

### 1. Postgres を用意する(Neon 無料枠を推奨)

1. [https://neon.tech](https://neon.tech) でアカウント作成(GitHub ログイン可)
2. 新規プロジェクト作成 → 自動でデータベースが1個できる
3. Dashboard の **Connection string** → *Pooled connection* をコピー
   - 形式: `postgresql://user:password@ep-xxx-pooler.region.aws.neon.tech/dbname?sslmode=require`

### 2. Vercel にプロジェクトを作る

1. [https://vercel.com](https://vercel.com) にログイン(GitHub 連携)
2. `Add New... → Project` → 本リポジトリを選択 → `Import`
3. Framework Preset は **Other** のまま
4. **Environment Variables** で以下を登録:

| Name | Value | 必須 |
| --- | --- | --- |
| `DATABASE_URL` | Neon の接続文字列 | ✅ |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE 発行のトークン | ✅ |
| `LINE_USER_ID` | 配信先の userId / groupId | ✅ |
| `CRON_SECRET` | 任意のランダム文字列(Cron エンドポイント保護) | ✅ |
| `ADMIN_PASSWORD` | 管理 UI にかけたい Basic 認証パスワード | 任意 |
| `TIMEZONE` | `Asia/Tokyo` | 任意 |
| `AUTO_SEED` | `1`(初回にサンプル食材を自動投入) | 任意 |

5. `Deploy` を押す → 数分で完了し `https://xxxxx.vercel.app` が発行される

### 3. 初回アクセス

- 発行された URL を開くと 3 タブの管理 UI が表示される
- 初回のコールドスタートで自動的に:
  - `CREATE TABLE IF NOT EXISTS` が走る
  - デフォルトテンプレートが1件挿入される
  - `AUTO_SEED=1` なら 19 品のサンプル食材が入る

### 4. 友人と共有する

- URL をグループLINEなどで共有
- `ADMIN_PASSWORD` を設定している場合は、ID は任意 / パスワードは設定値
- 編集内容は Postgres に即時保存され、全員に反映される

### 5. 毎朝 7:00 JST 配信(Vercel Cron)

`vercel.json` に組み込み済み。Hobby プランでも無料で稼働。

```json
"crons": [{ "path": "/api/cron/send", "schedule": "0 22 * * *" }]
```

- UTC 22:00 = JST 翌 07:00
- Vercel Cron は自動で Bearer トークン(Vercel が設定する `CRON_SECRET`)を付けて叩く
- 手動でも叩ける: `curl -H "Authorization: Bearer <CRON_SECRET>" https://xxxxx.vercel.app/api/cron/send`

### 6. 動作確認チェックリスト

- [ ] `/` → 管理 UI が表示される
- [ ] 食材タブで追加 / 削除できる
- [ ] テンプレートタブでプレビュー・保存できる
- [ ] ダッシュボードの「いますぐ LINE 送信」で LINE に届く
- [ ] 翌朝 7:00 に自動配信が来る(初日)

### 7. GitHub Actions は不要になる

Vercel Cron が定時配信を引き受けるので、以下のワークフローは無効化/削除して OK:

- `.github/workflows/daily-breakfast.yml`
- `.github/workflows/admin-ui.yml`(Tunnel 公開も不要)

削除しない場合も、Vercel 側の Cron と **二重配信** になる点に注意してください。

## 環境変数

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `LINE_CHANNEL_ACCESS_TOKEN` | (必須) | LINE Messaging API のチャネルアクセストークン |
| `LINE_USER_ID` | (必須) | 配信先ユーザー ID または グループ ID |
| `DATABASE_URL` | `sqlite:///breakfast.db` | SQLAlchemy 接続文字列(Vercel では Postgres 必須) |
| `NOTIFY_HOUR` / `NOTIFY_MINUTE` | `7` / `0` | 配信時刻(ローカル APScheduler 用) |
| `TIMEZONE` | `Asia/Tokyo` | スケジューラの TZ |
| `ADMIN_HOST` / `ADMIN_PORT` | `0.0.0.0` / `5000` | 管理 UI 待ち受け |
| `ADMIN_PASSWORD` | (空) | Basic 認証パスワード(空なら認証なし) |
| `CRON_SECRET` | (空) | `/api/cron/send` エンドポイントの Bearer 認証 |
| `AUTO_SEED` | `1` | 空DBに対し初回のみサンプル食材を投入 |

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
