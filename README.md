# Universal Converter

CSV・JSON・テキスト・画像・音声・動画・PDF・アーカイブを、ひとつの画面から別の形式に変換する Web アプリです。
変換の実処理は Python、Web 画面・入力検証・ダウンロードは PHP / Laravel が担当します。

開発の方針・ロードマップ・各形式の制約の詳細は [PROJECT.md](PROJECT.md) にあります。

## 対応している変換

| カテゴリ | 変換 | 必要なもの |
|---|---|---|
| データ | CSV → JSON、JSON → CSV | — |
| テキスト | JSON の整形・検証、文字コードを UTF-8 へ（UTF-8 / UTF-16 / Shift_JIS / EUC-JP） | — |
| 画像 | PNG / JPEG / WebP / BMP / GIF の相互変換 | Pillow |
| 音声 | MP3 / WAV / M4A / FLAC / OGG の相互変換 | FFmpeg（ffprobe を含む） |
| PDF | PDF → テキスト（文字の抽出）、PDF → PNG（1 ページ目 / 全ページを ZIP で）、画像 → PDF | pypdf、pypdfium2、Pillow |
| 動画 | MP4 / MOV / WebM → MP4（H.264）、MP4（圧縮・高さ最大 720）、WebM（VP9）、音声の取り出し（MP3） | FFmpeg（ffprobe を含む） |
| アーカイブ | ZIP ⇄ tar.gz、ZIP の中身の調査（JSON） | — |

未対応（これから）: 複数ファイルの一括変換、変換オプションの指定（PDF のページ範囲・画質など）、画像だけの PDF の文字認識（OCR）。

### 制限

- アップロードは 1 ファイル 2 MB まで（`CONVERTER_MAX_UPLOAD_KB`）。PDF・アーカイブは 10 MB、動画は 30 MB まで（変換ごとの設定。`config/converter.php`）。
- 1 回の変換は 30 秒まで（`CONVERTER_TIMEOUT`。動画は 120 秒まで）。同時に実行できる変換は 2 件まで（`CONVERTER_MAX_CONCURRENT`）で、超えると「混み合っています」と表示します。
- 画像は 25 メガピクセルまで。音声は 3 分まで、変換後は 32 MB までです。動画は 60 秒・フル HD まで、変換後は 50 MB までです。
- PDF は文字の抽出が 200 ページ、画像化が 50 ページまで（パスワード付きは不可）。アーカイブは 1000 ファイル・展開後 100 MB までで、リンク・暗号化・危険なパス（`../` など）・極端な圧縮率のものは拒否します。
- 形式は拡張子ではなくファイルの**中身**で判定します。メタデータ（EXIF・音声タグ・カバー画像）は引き継ぎません。
- アップロードしたファイルは、変換が終わると削除します。変換結果はサーバーに保存しません。

## ローカルで動かす

必要なもの: PHP 8.3 以上、Composer、Python 3.10 以上、FFmpeg（音声・動画の変換を使う場合）。

```bash
# 1. PHP の依存関係と設定
composer install
cp .env.example .env          # 既に .env がある場合は不要
php artisan key:generate

# 2. Python の依存関係（仮想環境を推奨）
python3 -m venv .venv
.venv/bin/pip install -r python/requirements.txt
# .env の CONVERTER_PYTHON を .venv/bin/python のフルパスにする

# 3. FFmpeg（音声・動画の変換用）
sudo apt install ffmpeg       # Debian / Ubuntu。macOS は brew install ffmpeg

# 4. 起動
php artisan serve             # → http://localhost:8000/converter
```

Python の変換エンジンだけをコマンドラインで試すこともできます。

```bash
cd python
python -m converter.main audio_to_mp3 input.wav output.mp3
```

## テスト

```bash
# Python（Pillow が無いと画像、FFmpeg が無いと音声のテストだけスキップされる）
cd python && python3 -m unittest discover -s tests -t . -v

# Laravel（Python まで通した結合テスト）
php artisan test --filter=ConverterTest
php artisan test
```

## Render にデプロイする

`Dockerfile` が PHP（Apache）・Python・FFmpeg をひとつのイメージにまとめます。`render.yaml` に環境変数を用意してあります。

1. このリポジトリを GitHub にプッシュする（`.env` は含めない。`.gitignore` で除外済み）。
2. 手元で `php artisan key:generate --show` を実行し、`base64:...` の値を控える。
3. Render の **New > Blueprint** でリポジトリを選ぶ。
4. 環境変数 `APP_KEY` に、控えた値を設定する（`render.yaml` では `sync: false` にしてあり、画面から入力する）。
5. デプロイ後、サービスの URL に合わせて `APP_URL`（`https://<サービス名>.onrender.com`）を更新して再デプロイする。

注意:

- `plan: free` は動作確認用です。CPU が小さく、アイドル時に停止します。実運用では上位プランにし、`CONVERTER_MAX_CONCURRENT` を増やしてください。
- Render では `CONVERTER_TIMEOUT` と、Render 側のリクエスト時間の上限の両方に収まる必要があります。

### 環境変数

| 変数 | 既定値 | 内容 |
|---|---|---|
| `CONVERTER_PYTHON` | `python3` | Python 実行ファイル（Docker では `/opt/venv/bin/python`） |
| `CONVERTER_TIMEOUT` | `30` | 1 回の変換のタイムアウト（秒） |
| `CONVERTER_MAX_UPLOAD_KB` | `2048` | アップロード上限（KB） |
| `CONVERTER_MAX_CONCURRENT` | `2` | 同時に実行できる変換の数 |
| `CONVERTER_CLEANUP_MINUTES` | `60` | この分数より古い一時ファイルを自動削除する |
| `CONVERTER_FFMPEG` / `CONVERTER_FFPROBE` | `ffmpeg` / `ffprobe` | FFmpeg / ffprobe の場所（PATH にあれば不要） |
| `TRUSTED_PROXIES` | （空） | プロキシの内側で動かすとき `*` |

### デプロイ後の確認

デプロイしただけでは動作したことになりません。公開 URL で次を確かめてください。

- `/up` が 200 を返す。
- `/converter` が表示され、「音声」「画像」「PDF」「動画」「アーカイブ」などの選択肢が出る。
- 正常系: CSV → JSON、画像 → PNG、WAV → MP3、PDF → テキスト、短い動画 → MP4、ZIP → tar.gz をそれぞれ変換してダウンロードできる。
- 異常系: 中身が音声・動画でない `.mp3` / `.mp4`、壊れた画像、パスワード付き PDF、`../` を含む ZIP、上限を超えるファイルが、内部パスを含まないエラーで断られる。
- 混み合い: 同時に複数の変換を送ると、上限を超えた分が「混み合っています」になる。
- ログに、ファイルの内容やサーバー内のパスが出ていない（Render の Logs を確認）。

## ライセンス

Laravel は [MIT ライセンス](https://opensource.org/licenses/MIT) です。
