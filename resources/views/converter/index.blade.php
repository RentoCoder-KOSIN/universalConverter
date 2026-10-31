@extends('layouts.app')

@section('title', '変換する | Universal Converter')

@section('content')
    @php
        $groups = collect($operations)->groupBy('group', preserveKeys: true);
        $notes = config('converter.group_notes', []);
        $icons = config('converter.group_icons', []);
        $fallbackIcon = 'M6 3h8l4 4v14H6z M14 3v4h4 M9 13h6 M9 17h4';

        // 選択中の変換。入力エラーで戻ってきたときは、直前の選択を保つ。
        $selectedKey = old('operation');
        if (! is_string($selectedKey) || ! array_key_exists($selectedKey, $operations)) {
            $selectedKey = array_key_first($operations);
        }
        $selected = $operations[$selectedKey];
        $selectedLimitKb = $selected['max_upload_kb'] ?? $maxUploadKb;
        $idleText = $errors->any() ? 'ファイルを選び直してください' : 'ファイルを待っています';
    @endphp

    <div class="page-head">
        <h1 class="page-title">ファイルを変換する</h1>
        <p class="page-lead">種類と変換を選んで、ファイルを入れるだけ。結果はそのままダウンロードされます。</p>
    </div>

    <form id="converter-form" class="bench" method="POST" action="{{ route('converter.convert') }}" enctype="multipart/form-data">
        @csrf

        <div class="flow">
        <nav class="rail" id="rail" aria-label="変換の種類">
            <h2 class="step-title"><span class="step-no" aria-hidden="true">1</span>種類を選ぶ</h2>
            <ul class="rail-list" role="tablist" id="rail-list"></ul>
        </nav>

        <div>
            <h2 class="step-title"><span class="step-no" aria-hidden="true">2</span>変換を選ぶ</h2>
            <div class="choices-panel">
                @foreach ($groups as $group => $items)
                    @php
                        $groupId = 'group-'.$loop->iteration;
                        $groupLimitKb = $items->max(fn ($o) => $o['max_upload_kb'] ?? $maxUploadKb);
                        $tone = ($loop->iteration - 1) % 6 + 1;
                    @endphp
                    <section class="group" id="{{ $groupId }}" data-group="{{ $group }}" data-tone="{{ $tone }}" aria-labelledby="{{ $groupId }}-name">
                        <div class="group-head">
                            <span class="icon-bubble" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="{{ $icons[$group] ?? $fallbackIcon }}"/></svg></span>
                            <h3 class="group-name" id="{{ $groupId }}-name">{{ $group }}</h3>
                            <span class="pill group-limit">上限 {{ number_format($groupLimitKb / 1024, 0) }} MB</span>
                        </div>
                        @if (isset($notes[$group]))
                            <p class="group-note">{{ $notes[$group] }}</p>
                        @endif
                        <div class="choices" role="radiogroup" aria-labelledby="{{ $groupId }}-name">
                            @foreach ($items as $key => $operation)
                                <label class="choice">
                                    <input type="radio" name="operation" value="{{ $key }}"
                                           data-label="{{ $operation['label'] }}"
                                           data-accept="{{ implode(',', array_map(fn ($e) => '.'.$e, $operation['input_extensions'])) }}"
                                           data-in="{{ implode(',', $operation['input_extensions']) }}"
                                           data-out="{{ $operation['output_extension'] ?? '' }}"
                                           data-limit-kb="{{ $operation['max_upload_kb'] ?? $maxUploadKb }}"
                                           @checked($key === $selectedKey)
                                           required>
                                    <span class="choice-face">
                                        <span class="choice-name">{{ $operation['label'] }}</span>
                                        <span class="choice-out">{{ $operation['output_extension'] ? '.'.$operation['output_extension'] : '同じ形式' }}</span>
                                    </span>
                                </label>
                            @endforeach
                        </div>
                    </section>
                @endforeach
            </div>
        </div>
        </div>

        <div class="station">
            <div class="station-head">
                <h2 class="step-title"><span class="step-no" aria-hidden="true">3</span>ファイル</h2>
                <div class="state-pill" id="state" role="status">
                    <span class="lamp" aria-hidden="true"></span>
                    <span id="state-text" data-idle="{{ $idleText }}">{{ $idleText }}</span>
                </div>
            </div>

            <div class="readout" aria-live="polite">
                <div class="readout-name" id="readout-name">{{ $selected['label'] }}</div>
                <div class="readout-line">
                    <div class="readout-in" id="readout-in">
                        @foreach ($selected['input_extensions'] as $extension)
                            <span>.{{ $extension }}</span>
                        @endforeach
                    </div>
                    <div class="readout-arrow" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg></div>
                    @if ($selected['output_extension'])
                        <div class="readout-out" id="readout-out">.{{ $selected['output_extension'] }}</div>
                    @else
                        <div class="readout-out is-text" id="readout-out">入力と同じ形式</div>
                    @endif
                </div>
            </div>

            <div>
                <div class="dropzone" id="dropzone">
                    <input id="file" type="file" name="file" required aria-label="変換するファイル" aria-describedby="file-hint">
                    <span class="dropzone-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg></span>
                    <span class="dropzone-main" id="dropzone-main">ファイルを選ぶか、ここへドロップ</span>
                    <span class="dropzone-sub" id="dropzone-sub">上限 {{ number_format($selectedLimitKb / 1024, 0) }} MB</span>
                </div>
                <p class="hint" id="file-hint"></p>
            </div>

            @if ($errors->any())
                <div class="alert" role="alert">
                    <strong>変換できませんでした</strong>
                    @foreach ($errors->all() as $message)
                        <div>{{ $message }}</div>
                    @endforeach
                </div>
            @endif

            <button id="submit" class="button" type="submit">変換してダウンロード</button>
            <div class="working-bar" aria-hidden="true"></div>
            <p class="status" id="status" role="status"></p>

            <p class="limits">
                <strong>1 ファイルの上限</strong><br>
                @foreach ($groups as $group => $items)
                    {{ $group }} {{ number_format($items->max(fn ($o) => $o['max_upload_kb'] ?? $maxUploadKb) / 1024, 0) }} MB{{ $loop->last ? '' : '、' }}
                @endforeach
                <br>形式ごとの制限は <a href="{{ url('/') }}">対応形式</a> のページにあります。混み合っているときは、しばらく待ってからもう一度お試しください。
            </p>
        </div>
    </form>
@endsection

@push('scripts')
    <script>
        (function () {
            document.documentElement.classList.add('js');

            const form = document.getElementById('converter-form');
            const radios = Array.from(form.querySelectorAll('input[name="operation"]'));
            const groups = Array.from(form.querySelectorAll('.group'));
            const railList = document.getElementById('rail-list');
            const file = document.getElementById('file');
            const zone = document.getElementById('dropzone');
            const zoneMain = document.getElementById('dropzone-main');
            const zoneSub = document.getElementById('dropzone-sub');
            const hint = document.getElementById('file-hint');
            const readName = document.getElementById('readout-name');
            const readIn = document.getElementById('readout-in');
            const readOut = document.getElementById('readout-out');
            const state = document.getElementById('state');
            const stateText = document.getElementById('state-text');
            const submit = document.getElementById('submit');
            const status = document.getElementById('status');

            const idleMain = zoneMain.textContent;
            const idleState = stateText.dataset.idle;
            let working = false;

            function current() {
                return form.querySelector('input[name="operation"]:checked');
            }

            function formatSize(bytes) {
                return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(bytes / 1024)) + ' KB';
            }

            function setState(kind, text) {
                state.className = 'state-pill' + (kind ? ' is-' + kind : '');
                stateText.textContent = text;
            }

            // ---- 1. 種類（タブ）----

            const tabs = groups.map(function (group, index) {
                const item = document.createElement('li');
                item.setAttribute('role', 'presentation');

                const tab = document.createElement('button');
                tab.type = 'button';
                tab.className = 'rail-tab';
                tab.id = group.id + '-tab';
                tab.setAttribute('role', 'tab');
                tab.setAttribute('aria-controls', group.id);

                const name = document.createElement('span');
                name.textContent = group.dataset.group;
                const count = document.createElement('span');
                count.className = 'rail-count';
                count.textContent = group.querySelectorAll('input[name="operation"]').length;
                const icon = group.querySelector('.icon-bubble').cloneNode(true);
                tab.dataset.tone = group.dataset.tone;
                name.className = 'rail-name';
                count.textContent = count.textContent + ' 件';
                tab.append(icon, name, count);

                tab.addEventListener('click', function () { showGroup(index, false); });
                tab.addEventListener('keydown', function (event) {
                    const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
                    if (event.key in keys) {
                        event.preventDefault();
                        showGroup((index + keys[event.key] + groups.length) % groups.length, true);
                    }
                });

                group.setAttribute('role', 'tabpanel');
                group.setAttribute('aria-labelledby', tab.id);

                item.append(tab);
                railList.append(item);
                return tab;
            });

            function showGroup(active, focusTab) {
                groups.forEach(function (group, index) {
                    group.hidden = index !== active;
                    tabs[index].setAttribute('aria-selected', index === active ? 'true' : 'false');
                    tabs[index].tabIndex = index === active ? 0 : -1;
                });

                if (focusTab) {
                    tabs[active].focus();
                }
            }

            function markChoice() {
                const op = current();
                tabs.forEach(function (tab, index) {
                    tab.classList.toggle('has-choice', !!op && groups[index].contains(op));
                });
            }

            // ---- 3. ファイル ----

            // 選んだファイルが、いまの変換に合っているかを知らせる（最終的な判定はサーバーが行う）
            function checkFile() {
                const op = current();
                hint.textContent = '';
                hint.classList.remove('is-warn');

                if (!file.files.length) {
                    submit.disabled = true;
                    if (!working) { setState('', idleState); }
                    return;
                }

                submit.disabled = working;

                const chosen = file.files[0];
                const extension = chosen.name.includes('.') ? chosen.name.split('.').pop().toLowerCase() : '';
                const allowed = op.dataset.in.split(',');
                const limitKb = Number(op.dataset.limitKb);

                if (!allowed.includes(extension)) {
                    hint.textContent = op.dataset.label + ' で選べるのは ' + allowed.map(function (e) { return '.' + e; }).join(' ') + ' です。';
                    hint.classList.add('is-warn');
                    if (!working) { setState('warn', 'ファイルを確認してください'); }
                } else if (chosen.size > limitKb * 1024) {
                    hint.textContent = 'ファイルが大きすぎます（上限 ' + Math.round(limitKb / 1024) + ' MB）。';
                    hint.classList.add('is-warn');
                    if (!working) { setState('warn', 'ファイルを確認してください'); }
                } else if (!working) {
                    setState('ready', '変換できます');
                }
            }

            function sync() {
                const op = current();
                if (!op) {
                    return;
                }

                // 変換の種類に合わせて、選べるファイルの拡張子を絞る
                file.accept = op.dataset.accept;

                readName.textContent = op.dataset.label;
                readIn.replaceChildren.apply(readIn, op.dataset.in.split(',').map(function (e) {
                    const chip = document.createElement('span');
                    chip.textContent = '.' + e;
                    return chip;
                }));

                if (op.dataset.out) {
                    readOut.textContent = '.' + op.dataset.out;
                    readOut.classList.remove('is-text');
                } else {
                    readOut.textContent = '入力と同じ形式';
                    readOut.classList.add('is-text');
                }

                zoneSub.textContent = file.files.length
                    ? formatSize(file.files[0].size)
                    : '上限 ' + Math.round(Number(op.dataset.limitKb) / 1024) + ' MB';

                markChoice();
                checkFile();
            }

            radios.forEach(function (radio) { radio.addEventListener('change', sync); });

            file.addEventListener('change', function () {
                const has = file.files.length > 0;
                zone.classList.toggle('has-file', has);
                zoneMain.textContent = has ? file.files[0].name : idleMain;
                sync();
            });

            ['dragenter', 'dragover'].forEach(function (name) {
                zone.addEventListener(name, function () { zone.classList.add('is-over'); });
            });
            ['dragleave', 'drop'].forEach(function (name) {
                zone.addEventListener(name, function () { zone.classList.remove('is-over'); });
            });

            // 二重送信を防ぐ
            form.addEventListener('submit', function () {
                working = true;
                submit.disabled = true;
                form.classList.add('is-working');
                setState('work', '変換しています');
                status.textContent = '終わるとダウンロードが始まります。';

                // ダウンロードが始まるとページ遷移しないため、少し後に戻す
                setTimeout(function () {
                    working = false;
                    form.classList.remove('is-working');
                    status.textContent = 'ダウンロードが始まらないときは、少し待ってからもう一度押してください。';
                    checkFile();
                }, 4000);
            });

            const selected = current();
            const start = selected ? groups.findIndex(function (group) { return group.contains(selected); }) : 0;
            showGroup(Math.max(start, 0), false);
            sync();
        })();
    </script>
@endpush
