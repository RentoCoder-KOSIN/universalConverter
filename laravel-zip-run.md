# Laravel プロジェクトの zip 化・解凍・実行

## 1. zip 化(元の環境)

`vendor` と `node_modules` は容量が大きく、解凍先で再生成できるので除外します。

```bash
cd /path/to/親ディレクトリ
zip -r myapp.zip myapp \
  -x "myapp/vendor/*" \
  -x "myapp/node_modules/*" \
  -x "myapp/storage/logs/*" \
  -x "myapp/.git/*"
```

- `.env` はデフォルトで含まれます。DBパスワードなどが入っているので、他人に渡すときは `-x "myapp/.env"` で除外してください。
- `vendor` ごと固めたい場合は除外指定なしで `zip -r myapp.zip myapp` を実行します。

## 2. 解凍

```bash
unzip myapp.zip -d myapp
cd myapp
```

`unzip` が無い場合は `sudo apt install unzip` を実行します。

## 3. セットアップと起動

`composer.json` の `setup` スクリプトで、以下を一括実行できます。

1. `composer install`
2. `.env` の作成(`.env.example` をコピー)
3. `php artisan key:generate`
4. `php artisan migrate --force`
5. `npm install --ignore-scripts`
6. `npm run build`

```bash
composer setup
php artisan serve
```

`http://127.0.0.1:8000` でアクセスできます。外部からアクセスする場合は次のようにします。

```bash
php artisan serve --host=0.0.0.0 --port=8000
```

`composer dev` なら、`artisan dev` でまとめて起動します。

## 4. 手動で実行する場合

```bash
composer install
cp .env.example .env
php artisan key:generate
chmod -R 775 storage bootstrap/cache
php artisan migrate
npm install
npm run build
php artisan serve
```

## 5. 注意点

- **PHP**: `php ^8.3` が必要です(`php -v` で確認)。
- **DB(既定)**: `.env.example` は `DB_CONNECTION=sqlite` です。zip に `database/database.sqlite` が含まれているので、そのまま `migrate` できます。
- **DB(MariaDB を使う場合)**: 先にDBとユーザーを作成し、`.env` を書き換えてから `php artisan migrate` を実行します。

```env
DB_CONNECTION=mariadb
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=myapp
DB_USERNAME=ユーザー名
DB_PASSWORD=パスワード
```

- **権限エラー**: `chmod -R 775 storage bootstrap/cache` を実行します。
- **`migrate` の前**: `.env` のDB設定を済ませておきます。

## 6. 動作確認用ルート(`routes/web.php`)

| URL | 内容 |
|---|---|
| `/` | welcome ページ |
