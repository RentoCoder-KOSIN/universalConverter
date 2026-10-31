#!/bin/sh
# コンテナ起動時の準備。Apache（www-data）が書き込めるようにしてから起動する。
set -e

cd /var/www/html

if [ -z "${APP_KEY:-}" ]; then
    echo "ERROR: APP_KEY が設定されていません。'php artisan key:generate --show' で作った値を環境変数に設定してください。" >&2
    exit 1
fi

# 実行時に使うディレクトリ（イメージに含まれていない場合に備える）
mkdir -p storage/app/private/converter storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache

# SQLite を使う場合は、ファイルを用意する（変換機能は DB を使わない。ユーザー用テーブルなど Laravel 標準のマイグレーション用）
if [ "${DB_CONNECTION:-sqlite}" = "sqlite" ] && [ -n "${DB_DATABASE:-}" ] && [ "${DB_DATABASE}" != ":memory:" ]; then
    mkdir -p "$(dirname "${DB_DATABASE}")"
    touch "${DB_DATABASE}"
fi

chown -R www-data:www-data storage bootstrap/cache
[ -n "${DB_DATABASE:-}" ] && [ -f "${DB_DATABASE}" ] && chown www-data:www-data "${DB_DATABASE}" || true

artisan() {
    runuser -u www-data -- php artisan "$@"
}

# 設定とビューをキャッシュする（環境変数はここで確定する）
artisan config:cache
artisan view:cache

# マイグレーションの失敗で変換機能まで止めない
artisan migrate --force || echo "WARN: migrate に失敗しました（変換機能には影響しません）" >&2

# 異常終了で残った一時ファイルを定期的に削除する（リクエスト時にも削除している）
(
    while true; do
        sleep 600
        artisan converter:cleanup >/dev/null 2>&1 || true
    done
) &

# 変換に必要な外部ツールが使えるかを起動ログに残す
ffmpeg -version >/dev/null 2>&1 || echo "WARN: ffmpeg が見つかりません。音声変換は使えません。" >&2
"${CONVERTER_PYTHON:-python3}" -c "import PIL" >/dev/null 2>&1 || echo "WARN: Pillow が見つかりません。画像変換は使えません。" >&2

exec "$@"
