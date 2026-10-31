<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>@yield('title', 'Universal Converter')</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;500;700&display=swap">
    <link rel="stylesheet" href="{{ asset('css/site.css') }}?v={{ @filemtime(public_path('css/site.css')) }}">
</head>
<body>
    <a class="skip-link" href="#main">本文へ移動</a>

    <header class="site-header">
        <div class="wrap">
            <a class="wordmark" href="{{ url('/') }}">
                <span class="logo-mark" aria-hidden="true">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h13M13 4l4 4-4 4M20 16H7M11 12l-4 4 4 4"/></svg>
                </span>
                Universal Converter
            </a>
            <nav class="site-nav" aria-label="メイン">
                <a href="{{ url('/') }}" @if (request()->is('/')) aria-current="page" @endif>対応形式</a>
                <a href="{{ url('/converter') }}" @if (request()->is('converter')) aria-current="page" @endif>変換する</a>
            </nav>
        </div>
    </header>

    <main id="main">
        <div class="wrap">
            @yield('content')
        </div>
    </main>

    <footer class="site-footer">
        <div class="wrap">アップロードしたファイルは、変換が終わると削除されます。変換結果もサーバーには残りません。</div>
    </footer>

    @stack('scripts')
</body>
</html>
