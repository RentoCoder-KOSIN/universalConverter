@extends('layouts.app')

@section('title', $code.' '.$heading.' | Universal Converter')

@section('content')
    <section class="fault" role="alert">
        <div class="fault-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 8v5M12 17h.01M4.5 19h15a1.5 1.5 0 0 0 1.3-2.25l-7.5-12.5a1.5 1.5 0 0 0-2.6 0L3.2 16.75A1.5 1.5 0 0 0 4.5 19z"/></svg>
        </div>
        <div class="fault-code"><span class="pill">エラー {{ $code }}</span></div>
        <h1>{{ $heading }}</h1>
        <p>{{ $detail }}</p>
        <div class="actions">
            <a class="button" href="{{ url('/converter') }}">変換の画面へ</a>
            <a class="button secondary" href="{{ url('/') }}">対応形式を見る</a>
        </div>
    </section>
@endsection
