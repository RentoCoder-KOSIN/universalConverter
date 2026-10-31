@extends('layouts.app')

@section('title', 'Universal Converter')

@section('content')
    @php
        $groups = collect($operations)->groupBy('group', preserveKeys: true);

        // 形式ごとの制限・注意は config/converter.php の group_notes
        $notes = config('converter.group_notes', []);
        $icons = config('converter.group_icons', []);
        $fallbackIcon = 'M6 3h8l4 4v14H6z M14 3v4h4 M9 13h6 M9 17h4';
    @endphp

    <section class="hero">
        <h1>ファイルの形式を、<br>かんたんに変えよう。</h1>
        <p>CSV、画像、音声、動画、PDF、ZIP などを別の形式に変換できます。登録は要りません。ファイルを選ぶだけです。</p>
        <a class="button" href="{{ route('converter.index') }}">変換をはじめる</a>
    </section>

    <section class="spec" aria-label="対応している変換">
        @foreach ($groups as $group => $items)
            <article class="spec-card" data-tone="{{ ($loop->iteration - 1) % 6 + 1 }}">
                <header>
                    <span class="icon-bubble" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="{{ $icons[$group] ?? $fallbackIcon }}"/></svg></span>
                    <h2>{{ $group }}</h2>
                    <span class="pill">上限 {{ number_format($items->max(fn ($o) => $o['max_upload_kb'] ?? $maxUploadKb) / 1024, 0) }} MB</span>
                </header>
                <ul>
                    @foreach ($items as $operation)
                        <li>{{ $operation['label'] }}</li>
                    @endforeach
                </ul>
                @if (isset($notes[$group]))
                    <p class="note">{{ $notes[$group] }}</p>
                @endif
            </article>
        @endforeach
    </section>

    <p class="promise">
        同時に処理できる数には限りがあります。混み合っているときは、しばらく待ってからもう一度お試しください。
    </p>
@endsection
