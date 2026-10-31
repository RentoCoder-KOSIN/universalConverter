<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Python 実行ファイル
    |--------------------------------------------------------------------------
    | 環境ごとに異なるため環境変数で変更できる。
    | 例: CONVERTER_PYTHON=/path/to/.venv/bin/python
    */
    'python' => env('CONVERTER_PYTHON', 'python3'),

    // Python を実行する作業ディレクトリ（converter パッケージがある場所）
    'working_directory' => base_path('python'),

    // 1 回の変換に許す秒数。超えたらプロセスを止める。
    'timeout' => (int) env('CONVERTER_TIMEOUT', 30),

    // アップロードの上限（KB）。PHP 側の upload_max_filesize / post_max_size も上限になる。
    'max_upload_kb' => (int) env('CONVERTER_MAX_UPLOAD_KB', 2048),

    // 同時に実行できる変換の数。超えたリクエストは「混み合っています」と返す。
    // 複数のサーバープロセス間でも守られるよう、キャッシュのロックで数える。
    'max_concurrent' => max(1, (int) env('CONVERTER_MAX_CONCURRENT', 2)),

    // 作業ディレクトリがこの分数より古ければ、残骸として自動削除する。
    // 通常はリクエストごとに削除されるので、異常終了したときの保険。
    'cleanup_minutes' => max(1, (int) env('CONVERTER_CLEANUP_MINUTES', 60)),

    // 画面に出す、グループごとのアイコン（24x24 の線画の path）。無いグループは書類のアイコンになる。
    'group_icons' => [
        'データ' => 'M4 5h16v14H4z M4 10h16 M10 5v14',
        'テキスト' => 'M5 6h14 M12 6v13 M9 19h6',
        '画像' => 'M4 5h16v14H4z M4 16l5-5 4 4 3-3 4 4 M15.5 9.5h.01',
        '音声' => 'M4 10v4 M8 6v12 M12 3v18 M16 7v10 M20 10v4',
        'PDF' => 'M6 3h8l4 4v14H6z M14 3v4h4 M9 13h6 M9 17h4',
        '動画' => 'M3 6h14v12H3z M17 10l4-2v8l-4-2',
        'アーカイブ' => 'M4 7h16v4H4z M5 11v9h14v-9 M10 15h4',
    ],

    // 画面に出す、グループごとの説明（制限や注意）。無いグループは説明なしで表示する。
    'group_notes' => [
        'データ' => 'CSV と JSON を相互に変換します。',
        'テキスト' => 'JSON の整形・検証と、UTF-8 / Shift_JIS / EUC-JP / UTF-16 の文字コードを UTF-8 に変換できます。',
        '画像' => 'アニメーション GIF は最初の 1 コマだけが変換されます。撮影情報などのメタデータは引き継ぎません。',
        '音声' => '3 分まで、変換後 32 MB までです。タグやカバー画像は引き継がず、MP3 / OGG は 3 チャンネル以上がステレオになります。',
        'PDF' => '文字の抽出（画像だけの PDF は不可）と、ページの画像化（全ページは 50 ページまで）に対応します。パスワード付きは扱えません。',
        '動画' => '60 秒まで、フル HD まで、変換後 50 MB までです。撮影場所などのメタデータは引き継がず、変換には時間がかかります。',
        'アーカイブ' => 'ZIP と tar.gz は相互に変換できます。リンク・暗号化・危険なパスを含むものや、展開後 100 MB・1000 ファイルを超えるものは断ります。',
    ],

    /*
    |--------------------------------------------------------------------------
    | 対応する変換
    |--------------------------------------------------------------------------
    | キーは python/converter/registry.py の OPERATIONS と一致させる。
    | 形式を追加するときは Python 側と、ここの両方に登録する。
    */
    'operations' => [
        // group: 画面の選択肢のグループ名
        // output_extension: null のときは入力と同じ拡張子で出力する
        // max_upload_kb: （省略可）この変換だけのアップロード上限。省略時は上の max_upload_kb
        // timeout: （省略可）この変換だけのタイムアウト秒。省略時は上の timeout
        'csv_to_json' => [
            'group' => 'データ',
            'label' => 'CSV → JSON',
            'input_extensions' => ['csv'],
            'output_extension' => 'json',
            'mime' => 'application/json',
        ],
        'json_to_csv' => [
            'group' => 'データ',
            'label' => 'JSON → CSV',
            'input_extensions' => ['json'],
            'output_extension' => 'csv',
            'mime' => 'text/csv',
        ],
        'json_format' => [
            'group' => 'テキスト',
            'label' => 'JSON を整形・検証',
            'input_extensions' => ['json'],
            'output_extension' => 'json',
            'mime' => 'application/json',
        ],
        'txt_to_utf8' => [
            'group' => 'テキスト',
            'label' => '文字コードを UTF-8 に変換（txt / csv）',
            'input_extensions' => ['txt', 'csv'],
            'output_extension' => null,
            'mime' => 'text/plain',
        ],
        'image_to_png' => [
            'group' => '画像',
            'label' => '画像 → PNG',
            'input_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'],
            'output_extension' => 'png',
            'mime' => 'image/png',
        ],
        'image_to_jpeg' => [
            'group' => '画像',
            'label' => '画像 → JPEG',
            'input_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'],
            'output_extension' => 'jpg',
            'mime' => 'image/jpeg',
        ],
        'image_to_webp' => [
            'group' => '画像',
            'label' => '画像 → WebP',
            'input_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'],
            'output_extension' => 'webp',
            'mime' => 'image/webp',
        ],
        'image_to_bmp' => [
            'group' => '画像',
            'label' => '画像 → BMP',
            'input_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'],
            'output_extension' => 'bmp',
            'mime' => 'image/bmp',
        ],
        'image_to_gif' => [
            'group' => '画像',
            'label' => '画像 → GIF',
            'input_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'],
            'output_extension' => 'gif',
            'mime' => 'image/gif',
        ],
        'audio_to_mp3' => [
            'group' => '音声',
            'label' => '音声 → MP3',
            'input_extensions' => ['mp3', 'wav', 'm4a', 'flac', 'ogg'],
            'output_extension' => 'mp3',
            'mime' => 'audio/mpeg',
        ],
        'audio_to_wav' => [
            'group' => '音声',
            'label' => '音声 → WAV',
            'input_extensions' => ['mp3', 'wav', 'm4a', 'flac', 'ogg'],
            'output_extension' => 'wav',
            'mime' => 'audio/wav',
        ],
        'audio_to_m4a' => [
            'group' => '音声',
            'label' => '音声 → M4A（AAC）',
            'input_extensions' => ['mp3', 'wav', 'm4a', 'flac', 'ogg'],
            'output_extension' => 'm4a',
            'mime' => 'audio/mp4',
        ],
        'audio_to_flac' => [
            'group' => '音声',
            'label' => '音声 → FLAC',
            'input_extensions' => ['mp3', 'wav', 'm4a', 'flac', 'ogg'],
            'output_extension' => 'flac',
            'mime' => 'audio/flac',
        ],
        'audio_to_ogg' => [
            'group' => '音声',
            'label' => '音声 → OGG（Vorbis）',
            'input_extensions' => ['mp3', 'wav', 'm4a', 'flac', 'ogg'],
            'output_extension' => 'ogg',
            'mime' => 'audio/ogg',
        ],
        // --- PDF（pypdf / pypdfium2 / Pillow が必要） ---
        'pdf_to_txt' => [
            'group' => 'PDF',
            'label' => 'PDF → テキスト',
            'input_extensions' => ['pdf'],
            'output_extension' => 'txt',
            'mime' => 'text/plain',
            'max_upload_kb' => 10240,
        ],
        'pdf_first_page_to_png' => [
            'group' => 'PDF',
            'label' => 'PDF の 1 ページ目 → PNG',
            'input_extensions' => ['pdf'],
            'output_extension' => 'png',
            'mime' => 'image/png',
            'max_upload_kb' => 10240,
        ],
        'pdf_to_png_zip' => [
            'group' => 'PDF',
            'label' => 'PDF の全ページ → PNG（ZIP にまとめる）',
            'input_extensions' => ['pdf'],
            'output_extension' => 'zip',
            'mime' => 'application/zip',
            'max_upload_kb' => 10240,
        ],
        'image_to_pdf' => [
            'group' => 'PDF',
            'label' => '画像 → PDF',
            'input_extensions' => ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'],
            'output_extension' => 'pdf',
            'mime' => 'application/pdf',
            'max_upload_kb' => 10240,
        ],
        // --- 動画（FFmpeg / ffprobe が必要）。重い処理なので、タイムアウトとアップロード上限を個別に設定する ---
        'video_to_mp4' => [
            'group' => '動画',
            'label' => '動画 → MP4（H.264）',
            'input_extensions' => ['mp4', 'mov', 'webm'],
            'output_extension' => 'mp4',
            'mime' => 'video/mp4',
            'max_upload_kb' => 30720,
            'timeout' => 120,
        ],
        'video_to_mp4_small' => [
            'group' => '動画',
            'label' => '動画 → MP4（圧縮・高さ最大 720）',
            'input_extensions' => ['mp4', 'mov', 'webm'],
            'output_extension' => 'mp4',
            'mime' => 'video/mp4',
            'max_upload_kb' => 30720,
            'timeout' => 120,
        ],
        'video_to_webm' => [
            'group' => '動画',
            'label' => '動画 → WebM（VP9）',
            'input_extensions' => ['mp4', 'mov', 'webm'],
            'output_extension' => 'webm',
            'mime' => 'video/webm',
            'max_upload_kb' => 30720,
            'timeout' => 120,
        ],
        'video_extract_audio' => [
            'group' => '動画',
            'label' => '動画から音声を取り出す（MP3）',
            'input_extensions' => ['mp4', 'mov', 'webm'],
            'output_extension' => 'mp3',
            'mime' => 'audio/mpeg',
            'max_upload_kb' => 30720,
            'timeout' => 120,
        ],
        // --- アーカイブ ---
        'zip_to_targz' => [
            'group' => 'アーカイブ',
            'label' => 'ZIP → tar.gz',
            'input_extensions' => ['zip'],
            'output_extension' => 'tar.gz',
            'mime' => 'application/gzip',
            'max_upload_kb' => 10240,
        ],
        'targz_to_zip' => [
            'group' => 'アーカイブ',
            'label' => 'tar.gz → ZIP',
            'input_extensions' => ['gz', 'tgz'],
            'output_extension' => 'zip',
            'mime' => 'application/zip',
            'max_upload_kb' => 10240,
        ],
        'zip_info' => [
            'group' => 'アーカイブ',
            'label' => 'ZIP の中身を調べる（JSON）',
            'input_extensions' => ['zip'],
            'output_extension' => 'json',
            'mime' => 'application/json',
            'max_upload_kb' => 10240,
        ],
    ],

];
