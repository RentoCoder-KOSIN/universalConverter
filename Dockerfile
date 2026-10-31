# Universal Converter — Render 用（PHP / Laravel + Python + FFmpeg を 1 つのサービスにまとめる）
FROM php:8.4-apache

ENV DEBIAN_FRONTEND=noninteractive \
    APACHE_DOCUMENT_ROOT=/var/www/html/public \
    PORT=10000 \
    CONVERTER_PYTHON=/opt/venv/bin/python

# FFmpeg（音声変換）、Python（変換エンジン）、Composer に必要なツール
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg python3 python3-venv git unzip \
    && rm -rf /var/lib/apt/lists/*

# Apache: 公開ディレクトリを public/ にし、Render が渡す $PORT で待ち受ける
RUN a2enmod rewrite headers \
    && echo 'Listen ${PORT}' > /etc/apache2/ports.conf
COPY docker/apache-vhost.conf /etc/apache2/sites-available/000-default.conf
COPY docker/apache-mpm.conf /etc/apache2/conf-available/converter-mpm.conf
RUN a2enconf converter-mpm
COPY docker/php.ini /usr/local/etc/php/conf.d/zz-converter.ini

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /var/www/html

# Python の依存関係（変更が少ないので先にインストールしてキャッシュを効かせる）
COPY python/requirements.txt python/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r python/requirements.txt

# PHP の依存関係
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist --no-interaction

# アプリ本体（.dockerignore で .env やテスト用ファイルを除外している）
COPY . .
RUN composer dump-autoload --no-dev --optimize --no-interaction \
    && mkdir -p storage/app/private/converter storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache \
    && chown -R www-data:www-data storage bootstrap/cache

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 10000
ENTRYPOINT ["entrypoint.sh"]
CMD ["apache2-foreground"]
