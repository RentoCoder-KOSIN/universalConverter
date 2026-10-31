import json

# 文字コードの推定順。UTF-8（BOM 付き含む）→ UTF-16（BOM があるときだけ）→ Shift_JIS 系 → EUC-JP。
# cp932 は Windows / Excel が出力する Shift_JIS 拡張。EUC-JP と判別がつかない場合は cp932 を優先する。
_CANDIDATE_ENCODINGS = ("utf-8-sig", "cp932", "euc_jp")


def json_format(input_path, output_path):
    """JSON を読み込み、インデント付きで整形して書き出す（同時に JSON として正しいか検証する）。"""

    with open(input_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    with open(output_path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def txt_to_utf8(input_path, output_path):
    """テキスト（txt / csv）の文字コードを推定して UTF-8（BOM なし）で書き出す。"""

    with open(input_path, "rb") as file:
        raw = file.read()

    text = _decode(raw)

    # 改行コードはそのまま保つ（newline="" で変換しない）
    with open(output_path, "w", encoding="utf-8", newline="") as file:
        file.write(text)


def _decode(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            raise ValueError("UTF-16 として読み込めませんでした") from None

    # NUL バイトを含むなら、テキストではなくバイナリの可能性が高い
    if b"\x00" in raw:
        raise ValueError("テキストファイルではないようです")

    for encoding in _CANDIDATE_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(
        "文字コードを判別できませんでした（対応: UTF-8 / UTF-16 / Shift_JIS(cp932) / EUC-JP）"
    )
