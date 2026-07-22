# スロット期待値

Streamlit + Supabase で動く、ログイン付きの ana-slo 日別ページ分析アプリです。  
管理者が `マルハン綾瀬上土棚店` の日別ページURL、保存HTML、コピー本文を1件ずつ登録し、友達はログイン後に分析結果だけ閲覧できます。

分析結果は過去データに基づく推定であり、高設定投入や勝利を保証しません。

## 実装内容

- Supabase Auth によるメールアドレス・パスワードログイン
- `admin` / `viewer` の権限分離
- ana-slo日別URLの検証、requests取得、403時のPlaywright fallback
- 保存HTMLアップロード解析、コピー本文貼り付け解析、複数日分の一括本文取込
- ana-slo表示ページから本文をコピーしやすくするブックマークレット
- 全台データの抽出、プレビュー、Supabase upsert保存
- `store_name + date + machine_no` の重複更新
- 店舗、日別、曜日別、特定日別、機種別、台別の分析
- 店に行く日、曜日、特定日、店長X示唆メモを考慮したルールベースの狙い台ランキング
- 分析表と勝率表示は小数点以下なしで表示
- 管理者用の削除、CSV入出力、取得履歴、エラー履歴、特定日編集、ユーザー権限変更
- pytest による HTML解析、数値変換、日付抽出、店舗判定、重複更新、スコア計算、権限判定、不正URL拒否テスト

## ファイル構成

```text
.
├── app.py
├── analyzer.py
├── ana_slo_importer.py
├── auth.py
├── config.py
├── database.py
├── app_pages/
├── components/
├── services/
├── pages/
├── sql/001_schema.sql
├── tests/
├── requirements.txt
├── .env.example
├── .streamlit/config.toml
├── .streamlit/secrets.toml.example
└── README.md
```

`pages/` は要件として残していますが、閲覧者に管理画面リンクを表示しないため、実画面は `app.py` の権限付きナビゲーションと `app_pages/` で制御しています。

## Supabase設定手順

1. Supabaseで新しいプロジェクトを作成します。
2. `SQL Editor` を開きます。
3. `sql/001_schema.sql` の内容を貼り付けて実行します。
4. `Authentication > Providers > Email` を有効にします。
5. 必要に応じて `Confirm email` をオンにします。初心者向けに最初だけオフにして動作確認しても構いません。
6. `Project Settings > API` から次を控えます。
   - Project URL
   - anon public key
   - service_role key

`service_role key` は管理者用のサーバー側処理だけに使います。GitHubへは絶対にコミットしないでください。

## Streamlit Secrets設定

ローカルでは `.streamlit/secrets.toml.example` を参考に、`.streamlit/secrets.toml` を作成します。

```toml
[supabase]
url = "https://your-project-ref.supabase.co"
anon_key = "your-anon-key"
service_role_key = "your-service-role-key-for-server-side-admin-only"

APP_ADMIN_EMAILS = "your-admin@example.com"
```

Streamlit Community Cloud では、アプリの `Settings > Secrets` に同じ内容を貼り付けます。

## 初回管理者作成方法

推奨手順:

1. `.streamlit/secrets.toml` または Streamlit Cloud Secrets の `APP_ADMIN_EMAILS` に自分のメールアドレスを入れます。
2. `SUPABASE_SERVICE_ROLE_KEY` も設定します。
3. アプリの新規ユーザー作成で同じメールアドレスを登録します。
4. そのメールアドレスでログインすると、サーバー側処理で `admin` に昇格します。

うまくいかない場合は Supabase SQL Editor で以下を実行します。

```sql
update public.profiles
set role = 'admin'
where email = 'your-admin@example.com';
```

## ローカル起動方法

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Playwright fallbackをローカルで使う場合:

```bash
playwright install chromium
```

requestsやPlaywrightで取得できない場合でも、ブラウザで保存したHTMLファイル、またはページ本文をコピーしたテキストを管理画面から解析できます。コピー本文取込は複数日分をまとめて貼り付けできます。

## GitHubへの公開手順

```bash
git init
git add .
git commit -m "Initial Streamlit Supabase analysis app"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

`.env` と `.streamlit/secrets.toml` は `.gitignore` 済みです。秘密情報はGitHubへ置かず、Streamlit Secretsに設定してください。

## Streamlit Community Cloudへのデプロイ手順

1. GitHubへこのプロジェクトをpushします。
2. Streamlit Community Cloudで `New app` を選びます。
3. Repository、branch、main file path に `app.py` を指定します。
4. `Settings > Secrets` に Supabase設定を貼り付けます。
5. Deployします。
6. 起動後、自分のメールでログインし、管理画面が表示されることを確認します。

## ana-slo取込ルール

- 対象店舗は `マルハン綾瀬上土棚店` 固定です。
- 入力できるのは ana-slo の日別ページURLだけです。
- 店舗一覧ページや他店舗URLは拒否します。
- 同じURLの短時間連続実行はアプリ内で制限します。
- CAPTCHA回避、アクセス制限の不正突破、大量巡回は実装していません。
- 取得失敗時は保存HTMLアップロード、またはコピー本文取込を使ってください。
- 管理画面に表示されるブックマークレットをブラウザのブックマークに保存すると、ana-slo日別ページ上でURLと本文を1クリックコピーできます。
- 店長Xの示唆は自動取得せず、ランキング画面のメモ欄、または管理画面の特定日メモへ貼り付けて使います。

## テスト

```bash
pytest
```

対象:

- HTML解析
- 数値変換
- 日付抽出
- 対象店舗判定
- 不正URL拒否
- 重複更新カウント
- スコア計算
- 権限判定

## 既知の制限

- ana-sloのHTML構造が大きく変わった場合、`ana_slo_importer.py` のヘッダー対応を修正してください。
- ana-sloがStreamlit Cloudや自動ブラウザに空ページを返す場合があります。その場合は保存HTML取込またはコピー本文取込を使えます。
- 初当たり回数は、HTMLに明示列がない場合はAT/ART回数を優先し、取れない場合は0になります。
- ランキングは最初の実装としてルールベースです。勝敗や設定を保証するものではありません。
- Supabase無料枠ではデータ量やAPI回数に上限があります。

## 今後改善できる点

- ana-slo構造変更に備えたパーサープロファイルの追加
- 機械学習スコアリングへの差し替え
- 店舗カレンダーの一括編集
- 日別ページのスクリーンショット保存
- Supabase Edge Functions への取込処理分離
- 友達ごとの閲覧ログや通知
