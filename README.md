# AIオカン(朝ごはん + 掃除当番)

家庭の小言を先端技術で最適化する **AIオカン** 。同じドメイン上で 2 つのミニアプリを運用する Python アプリ。

- **🍳 オカンの朝ごはん**: 登録した素材から AI(Claude)が毎朝 **6:00** に合計 **700kcal / 300kcal 前後** の朝食献立を生成し、LINE で通知(登録素材以外は一切使わない厳格モード)
- **🧹 オカンの掃除当番**: 登録した担当者と掃除場所を、毎週土曜 8:00 にランダム割り当てて LINE 通知。場所の点数が担当者ごとに累積

ルートページ `/` は AIオカンのポータル。それぞれ `/breakfast` と `/cleaning` で管理できる。

## キャラクター画像

ランディングページと各ヘッダーには AIオカンの丸いイラストを表示します。
画像は `app/static/ai-okan.png` に配置してください。

- 推奨サイズ: 1024x1024 の正方形(CSS で丸く切り抜き)
- 置けていない場合はグラデーション + 絵文字のフォールバックになります
- Vercel デプロイ時は `@vercel/python` 経由で Flask が `/static/*` を配信します

## 特徴

- 素材(食材)ごとにカロリー・単位・分量範囲を管理 (CRUD)
- **AI(Claude)が登録素材から朝食献立を組み立てる**(例: 卵 + しゃけ + 梅干し + ごはん → しゃけ茶漬け + ゆで卵 + 緑茶)
- **2 プロファイルを同時生成**(700kcal たっぷり / 300kcal ひかえめ)
- プロファイルごとに直近 **3日以内と同じ献立は回避**
- AI が使えない / 失敗した場合は **ルールベース生成** に自動フォールバック
- 朝ごはんは **AI が出力した文面をそのまま LINE 配信**(テンプレート編集なし)。掃除は Jinja2 テンプレ編集に対応
- 素材の追加 / 編集 / 削除を Web UI から操作可能
- 管理画面 (Flask) からプレビュー / 即時送信が可能

## 構成

```
.
├── api/
│   └── index.py              # Vercel Serverless 関数エントリ
├── app/
│   ├── admin.py              # 管理用 Flask Web アプリ + REST API(朝ごはん / 掃除 両方)
│   ├── ai_suggester.py       # Claude による朝食献立生成
│   ├── cleaning.py           # 掃除当番のロジック / テンプレート
│   ├── config.py             # 環境変数読み込み
│   ├── database.py           # SQLAlchemy(SQLite / Postgres)+ 軽量マイグレーション
│   ├── line_notifier.py      # LINE Messaging API 連携
│   ├── menu_generator.py     # 朝食献立生成(AI → ルールベース)
│   ├── models.py             # Ingredient / MenuHistory / MessageTemplate / Cleaner / CleaningLocation / CleaningHistory
│   ├── scheduler.py          # APScheduler(ローカル/VPS 運用用)
│   └── seed_data.py          # サンプル食材
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

- `http://localhost:5000/` … トップページ(朝ごはん / 掃除の 2 入口)
- `http://localhost:5000/breakfast` … 朝ごはん管理(2 タブ: ダッシュボード / 食材)
- `http://localhost:5000/cleaning` … 掃除当番管理(4 タブ: ダッシュボード / 担当者 / 場所 / テンプレート)
- 毎朝 6:00(`NOTIFY_HOUR` で変更可)に朝ごはん LINE 配信
- 毎週土曜 8:00(Vercel Cron)に掃除当番 LINE 配信

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
| `ANTHROPIC_API_KEY` | Claude API キー(AI 料理提案タブを使う場合) | 任意 |
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

### 5. 定時配信(Vercel Cron)

`vercel.json` に 2 つの Cron を組み込み済み。Hobby プランでも無料で稼働。

```json
"crons": [
  { "path": "/api/cron/send",      "schedule": "0 21 * * *" },  // 毎朝 6:00 JST 朝食
  { "path": "/api/cron/cleaning",  "schedule": "0 23 * * 5" }   // 毎週土曜 8:00 JST 掃除
]
```

- UTC 21:00 = JST 翌 06:00(朝食)
- 金曜 UTC 23:00 = 土曜 JST 08:00(掃除)
- Vercel Cron は自動で Bearer トークン(`CRON_SECRET`)を付けて叩く
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
| `ANTHROPIC_API_KEY` | (空) | 設定すると AI 料理提案タブが有効化される |
| `AI_MODEL` | `claude-opus-4-7` | 料理提案で使う Claude モデル ID |

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

## 朝ごはんの配信文面

朝ごはんは **テンプレート編集機能を持ちません**。AI が `submit_menu` ツールの
`line_text` フィールドに、プロファイルごとの LINE 配信用テキスト(絵文字入りの
読みやすい日本語)を書いてきます。`app/line_notifier.py::format_breakfast` は
プロファイルごとの `line_text` を区切り線でつなぐだけで、Jinja2 による変換は
一切行いません。

AI が失敗した / `ANTHROPIC_API_KEY` 未設定のときはルールベース生成の結果を
Python 側で簡易整形して送ります(`【profile】《menu_name》 合計 N kcal` 形式)。

## 掃除当番機能

`/cleaning` で管理する独立したミニアプリ。朝ごはんとは DB テーブル・テンプレートが別。

### データ

- **担当者(`cleaners`)**: `name`(名前のみ)/ `total_points`(累積ポイント)/ `active`
- **掃除場所(`cleaning_locations`)**: `name`(場所)/ `points`(点数)/ `notes`(備考・実施内容)/ `active`
- **履歴(`cleaning_history`)**: 割り当ての記録(担当者・場所・点数・日付)

### 配信ロジック(毎週土曜 08:00 JST)

1. 有効な担当者と掃除場所をそれぞれ取得
2. どちらかが 0 件ならスキップ(送信しない)
3. 場所と担当者をシャッフルし、順番にペアリング
   - 場所 ≥ 担当者 → 各担当者に **異なる場所** が割り当たる
   - 担当者 > 場所 → 場所を循環利用(同じ場所が複数人に)
4. 各担当者の `total_points` に割り当たった場所の `points` を加算
5. LINE にテンプレート経由で送信

### 配信文例(既定テンプレート)

```
🧹 今週の掃除当番 (2026-04-25)

━━━━━━━━━━━━━
【太郎】
📍 キッチン (3pt)
やること: コンロまわりとシンクを磨く

━━━━━━━━━━━━━
【花子】
📍 お風呂 (5pt)
やること: 浴槽と床、排水口まで

今週もよろしくお願いします!
```

### 累積ポイント

`/cleaning` のダッシュボードに順位表(累積ポイント降順)が出る。担当者タブで手動修正も可能。

### テンプレート変数

| 変数 | 説明 |
| --- | --- |
| `date` | 配信日 `YYYY-MM-DD` |
| `assignments` | 割り当てリスト |
| `assignments[i].cleaner_name` | 担当者の名前 |
| `assignments[i].location_name` | 掃除場所の名前 |
| `assignments[i].points` | その場所の点数 |
| `assignments[i].notes` | その場所の備考(実施内容) |

## 献立生成アルゴリズム(概要)

既定で 2 プロファイル分を生成する(`app/menu_generator.py::DEFAULT_PROFILES`)。

| プロファイル | 目標 | 許容範囲 | 構成 |
| --- | --- | --- | --- |
| 700kcal | 700kcal | 650〜750 | 主食 + たんぱく + 副菜 + 飲み物 |
| 300kcal | 300kcal | 250〜350 | 主食 + たんぱく + 飲み物 |

### パス A: AI 生成(`ANTHROPIC_API_KEY` が設定されている場合)

1. 登録済みの有効素材とそのカロリー情報を Claude に渡す
2. プロファイルの目標カロリー(例: 700 kcal / 許容 650〜750)も渡す
3. 直近 3 日と同じ食材+分量の組み合わせを避けるよう指示
4. Claude は `submit_menu` ツールの強制呼び出しで、料理名・分量・カロリー・使う素材・作り方メモを返す
5. **登録素材に無い名前を使う料理はサーバ側で除外**(調味料・水・氷も含め、登録リスト外は一切使わない厳格運用)
6. 返却をそのまま `MenuItem`(料理単位)として履歴と配信に使う

### パス B: ルールベース(AI が未設定 / 失敗時のフォールバック)

1. 有効な食材をカテゴリ別に分類
2. 必須カテゴリがすべて揃わなければ **空の is_fallback メニュー** を返す(未登録素材の既定料理は使わない)
3. 最大 200 回試行:
   - 各カテゴリから 1 品ずつランダム選択(登録素材だけを使う)
   - `min_portion`〜`max_portion` を 5 段階に量子化して分量を決定
   - 直近 3 日と同じ食材+分量の組み合わせはスキップ
   - そのプロファイルの許容範囲に収まれば採用
4. 範囲内で見つからなかった場合、ターゲット ±15% に最も近い候補で妥協
5. それも無ければ「登録済みの食材だけでは献立が組めませんでした」という空メニューを返す

2 プロファイル間で同一献立にならないよう、先に採用された献立のシグネチャを除外候補として渡す。
