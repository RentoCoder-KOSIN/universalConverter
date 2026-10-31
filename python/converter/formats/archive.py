"""アーカイブ（ZIP / tar.gz）の変換と調査。

ファイルシステムに展開せず、エントリーを 1 件ずつ読み取って別の形式に詰め直す。
そのためパス・トラバーサル（../ で外に書き出す攻撃）はそもそも起きないが、
危険な名前・リンク・暗号化・過大な展開は明示的に拒否する。
"""

import json
import re
import shutil
import tarfile
import time
import zipfile
import zlib

# エントリー数、展開後の合計サイズ、圧縮率の上限
MAX_ENTRIES = 1000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_RATIO = 200          # 展開後 / 圧縮後 がこれを超えたら拒否（ZIP 爆弾対策）
RATIO_MIN_SIZE = 1024 * 1024  # 小さいファイルの高圧縮率は普通なので、1MB 以上の場合だけ見る

_MAX_NAME_LENGTH = 1024
_MAX_PART_LENGTH = 255
_ZIP_MIN_DATE = 315532800  # 1980-01-01。ZIP が表せる最小の日付

# ZIP / tar の読み込み中に起きる「壊れたファイル」系のエラー
_BROKEN_ARCHIVE_ERRORS = (
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    tarfile.TarError,
    NotImplementedError,  # 未対応の圧縮方式
    RuntimeError,         # パスワード付きの ZIP
)


def zip_to_targz(input_path, output_path):
    """ZIP を tar.gz に変換する。"""

    try:
        with zipfile.ZipFile(input_path) as source, tarfile.open(output_path, "w:gz") as target:
            entries = source.infolist()
            _check_count(len(entries))
            total = 0

            for info in entries:
                name = _safe_name(info.filename)
                _reject_unsafe_zip_entry(info)

                if name is None:
                    continue

                if info.is_dir():
                    target.addfile(_tar_info(name + "/", 0, info.date_time, directory=True))
                    continue

                total += info.file_size
                _check_size(total)
                _check_ratio(info.file_size, info.compress_size)

                with source.open(info) as stream:
                    target.addfile(_tar_info(name, info.file_size, info.date_time), stream)
    except zipfile.BadZipFile:
        raise ValueError("ZIP として読み込めません") from None
    except _BROKEN_ARCHIVE_ERRORS as error:
        raise _as_value_error(error) from None


def targz_to_zip(input_path, output_path):
    """tar.gz を ZIP に変換する。"""

    try:
        with tarfile.open(input_path, "r:gz") as source, \
                zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as target:
            count = 0
            total = 0

            for member in source:
                count += 1
                _check_count(count)

                if not (member.isreg() or member.isdir()):
                    # シンボリックリンク、ハードリンク、デバイスファイルなど
                    raise ValueError("リンクや特殊ファイルを含むアーカイブには対応していません")

                name = _safe_name(member.name)
                if name is None:
                    continue

                mtime = time.gmtime(max(member.mtime, _ZIP_MIN_DATE))[:6]

                if member.isdir():
                    info = zipfile.ZipInfo(name + "/", mtime)
                    info.external_attr = (0o40755 << 16) | 0x10
                    target.writestr(info, b"")
                    continue

                total += member.size
                _check_size(total)

                info = zipfile.ZipInfo(name, mtime)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16

                stream = source.extractfile(member)
                with target.open(info, "w", force_zip64=member.size > 2**31) as out:
                    shutil.copyfileobj(stream, out, 1024 * 1024)
    except ValueError:
        raise
    except tarfile.ReadError:
        raise ValueError("tar.gz として読み込めません") from None
    except _BROKEN_ARCHIVE_ERRORS as error:
        raise _as_value_error(error) from None


def zip_info(input_path, output_path):
    """ZIP の中身を展開せずに調べ、一覧と注意点を JSON で書き出す。"""

    try:
        with zipfile.ZipFile(input_path) as source:
            infos = source.infolist()
            entries = []
            warnings = []
            total = 0

            for info in infos[:MAX_ENTRIES]:
                problems = _entry_problems(info)

                entries.append({
                    "name": info.filename,
                    "is_dir": info.is_dir(),
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                    "problems": problems,
                })
                total += info.file_size

                for problem in problems:
                    warnings.append(f"{info.filename}: {problem}")

            if len(infos) > MAX_ENTRIES:
                warnings.append(f"エントリーが多いため、先頭の {MAX_ENTRIES} 件だけを表示しています")
                total += sum(i.file_size for i in infos[MAX_ENTRIES:])

            if total > MAX_TOTAL_BYTES:
                warnings.append("展開後の合計サイズが大きすぎます（変換機能では扱えません）")

            result = {
                "count": len(infos),
                "total_size": total,
                "entries": entries,
                "warnings": warnings,
            }
    except zipfile.BadZipFile:
        raise ValueError("ZIP として読み込めません") from None
    except _BROKEN_ARCHIVE_ERRORS as error:
        raise _as_value_error(error) from None

    with open(output_path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write("\n")


# ---- 内部処理 -------------------------------------------------------------


def _safe_name(raw_name):
    """アーカイブ内のパスを検査し、安全な相対パス（区切りは /）にして返す。

    危険な名前は ValueError。実体のない名前（"./" など）は None を返す。
    """

    if "\x00" in raw_name:
        raise ValueError("不正なファイル名を含むアーカイブです")

    name = raw_name.replace("\\", "/")

    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise ValueError("絶対パスを含むアーカイブには対応していません")

    parts = [part for part in name.split("/") if part not in ("", ".")]

    if any(part == ".." for part in parts):
        raise ValueError("親ディレクトリ（..）を指すパスを含むアーカイブには対応していません")

    if not parts:
        return None

    if len(name) > _MAX_NAME_LENGTH or any(len(part) > _MAX_PART_LENGTH for part in parts):
        raise ValueError("ファイル名が長すぎるアーカイブです")

    return "/".join(parts)


def _reject_unsafe_zip_entry(info):
    if info.flag_bits & 0x1:
        raise ValueError("パスワードで保護された ZIP には対応していません")

    # 上位 16 ビットに Unix のファイル種別が入っている。シンボリックリンクは拒否する。
    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
        raise ValueError("リンクを含むアーカイブには対応していません")


def _entry_problems(info):
    """zip_info 用。エラーにせず、問題点を文字列で返す。"""

    problems = []

    if info.flag_bits & 0x1:
        problems.append("暗号化されています")

    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
        problems.append("シンボリックリンクです")

    try:
        _safe_name(info.filename)
    except ValueError as error:
        problems.append(str(error))

    if (
        info.file_size >= RATIO_MIN_SIZE
        and info.compress_size > 0
        and info.file_size / info.compress_size > MAX_RATIO
    ):
        problems.append("圧縮率が極端に高いです（ZIP 爆弾の可能性）")

    return problems


def _check_count(count):
    if count > MAX_ENTRIES:
        raise ValueError(f"ファイル数が多すぎます（最大 {MAX_ENTRIES} 件）")


def _check_size(total):
    if total > MAX_TOTAL_BYTES:
        raise ValueError(
            f"展開後のサイズが大きすぎます（最大 {MAX_TOTAL_BYTES // (1024 * 1024)} MB）"
        )


def _check_ratio(size, compressed):
    if size >= RATIO_MIN_SIZE and compressed > 0 and size / compressed > MAX_RATIO:
        raise ValueError("圧縮率が極端に高いアーカイブです（ZIP 爆弾の可能性があるため拒否しました）")


def _tar_info(name, size, date_time, directory=False):
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = time.mktime(date_time + (0, 0, -1)) if date_time else 0
    info.mode = 0o755 if directory else 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""

    if directory:
        info.type = tarfile.DIRTYPE

    return info


def _as_value_error(error):
    if isinstance(error, RuntimeError):
        return ValueError("パスワードで保護されたアーカイブには対応していません")
    if isinstance(error, NotImplementedError):
        return ValueError("対応していない圧縮方式のアーカイブです")
    return ValueError("アーカイブが壊れているため読み込めません")
