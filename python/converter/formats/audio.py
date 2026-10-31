import json
import os
import shutil
import subprocess
import time

# 読み込みを許可するコンテナ形式（ffprobe の format_name に含まれる名前）。
# ここに無い形式（HLS のプレイリストや動画専用の形式など）は拒否する。
ALLOWED_INPUT_FORMATS = {"mp3", "wav", "flac", "ogg", "m4a"}

# 音声の最大長（秒）。圧縮率の高い小さなファイルから巨大な出力ができるのを防ぐ。
MAX_DURATION_SECONDS = 180

# 出力ファイルの最大サイズ（バイト）。WAV のような非圧縮出力でメモリ・ディスクを使い切らないための上限。
MAX_OUTPUT_BYTES = 32 * 1024 * 1024

# ffprobe と FFmpeg を合わせた上限（秒）。Laravel 側の CONVERTER_TIMEOUT より短くする。
DEFAULT_TIMEOUT_SECONDS = 25

# 出力形式名 -> (ffmpeg に渡すエンコード引数, 最大チャンネル数)
_OUTPUT_FORMATS = {
    "mp3": (["-c:a", "libmp3lame", "-b:a", "192k"], 2),
    "wav": (["-c:a", "pcm_s16le"], None),
    "m4a": (["-c:a", "aac", "-b:a", "192k"], None),
    "flac": (["-c:a", "flac"], None),
    "ogg": (["-c:a", "libvorbis", "-q:a", "5"], 2),
}

# 出力形式名 -> ffmpeg の出力コンテナ（拡張子に頼らず明示する）
_CONTAINERS = {
    "mp3": "mp3",
    "wav": "wav",
    "m4a": "ipod",
    "flac": "flac",
    "ogg": "ogg",
}


_TIMEOUT_MESSAGE = "処理に時間がかかりすぎたため中止しました（音声が長すぎる可能性があります）"


def make_converter(target):
    """音声を target 形式（mp3 / wav / m4a / flac / ogg）へ変換する関数を作る。"""

    options, max_channels = _OUTPUT_FORMATS[target]
    container = _CONTAINERS[target]

    def convert(input_path, output_path):
        _convert(input_path, output_path, options, max_channels, container)

    convert.__name__ = f"audio_to_{target}"
    return convert


def _timeout():
    try:
        value = float(os.environ.get("CONVERTER_FFMPEG_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        return float(DEFAULT_TIMEOUT_SECONDS)

    return value if value > 0 else float(DEFAULT_TIMEOUT_SECONDS)


def _find(tool, env_name):
    """ffmpeg / ffprobe の実行ファイルを探す。無ければ ImportError（unavailable として扱われる）。"""

    configured = os.environ.get(env_name) or tool
    found = shutil.which(configured)

    if found is None:
        raise ImportError(f"{tool} が見つかりません")

    return found


def _run(command, deadline):
    """deadline（time.monotonic() の時刻）までに終わらなければ中止する。"""

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError(_TIMEOUT_MESSAGE)

    try:
        return subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(_TIMEOUT_MESSAGE) from None


def _probe(ffprobe, input_path, deadline):
    """入力の中身を調べる。音声として扱えなければ ValueError。"""

    result = _run(
        [
            ffprobe,
            "-v", "error",
            "-protocol_whitelist", "file",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            f"file:{input_path}",
        ],
        deadline,
    )

    try:
        info = json.loads(result.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        info = None

    if result.returncode != 0 or not isinstance(info, dict):
        raise ValueError(
            "音声として読み込めません（対応: MP3 / WAV / M4A / FLAC / OGG）"
        )

    format_names = set(str(info.get("format", {}).get("format_name", "")).split(","))
    if not format_names & ALLOWED_INPUT_FORMATS and "mov" not in format_names:
        raise ValueError(
            "音声として読み込めません（対応: MP3 / WAV / M4A / FLAC / OGG）"
        )

    audio_streams = [
        stream for stream in info.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise ValueError("音声データが含まれていません")

    duration = _duration(info, audio_streams[0])
    if duration is None:
        raise ValueError("音声の長さを確認できないため変換できません")
    if duration > MAX_DURATION_SECONDS:
        raise ValueError(
            f"音声が長すぎます（最大 {MAX_DURATION_SECONDS // 60} 分）"
        )

    return audio_streams[0]


def _duration(info, stream):
    for source in (info.get("format", {}), stream):
        try:
            value = float(source.get("duration"))
        except (TypeError, ValueError):
            continue

        if value >= 0:
            return value

    return None


def _convert(input_path, output_path, options, max_channels, container):
    ffmpeg = _find("ffmpeg", "CONVERTER_FFMPEG")
    ffprobe = _find("ffprobe", "CONVERTER_FFPROBE")
    deadline = time.monotonic() + _timeout()

    stream = _probe(ffprobe, input_path, deadline)

    command = [
        ffmpeg,
        "-nostdin", "-hide_banner", "-loglevel", "error",
        "-protocol_whitelist", "file",
        "-y",
        "-i", f"file:{input_path}",
        "-map", "0:a:0",   # 最初の音声ストリームだけ（カバー画像・動画は捨てる）
        "-map_metadata", "-1",   # タグなどのメタデータは引き継がない
        "-vn",
    ]

    channels = stream.get("channels")
    if max_channels and isinstance(channels, int) and channels > max_channels:
        command += ["-ac", str(max_channels)]

    command += options
    # 上限に達したら ffmpeg に書き出しを止めさせ、下で拒否する
    command += ["-fs", str(MAX_OUTPUT_BYTES), "-f", container, f"file:{output_path}"]

    result = _run(command, deadline)

    if os.path.isfile(output_path) and os.path.getsize(output_path) >= MAX_OUTPUT_BYTES:
        os.remove(output_path)
        raise ValueError(
            f"変換後のファイルが大きすぎます（最大 {MAX_OUTPUT_BYTES // (1024 * 1024)} MB）。"
            "WAV など圧縮しない形式は、短い音声だけ変換できます"
        )

    if result.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        # 失敗した出力は残さない
        try:
            os.remove(output_path)
        except OSError:
            pass

        raise ValueError("音声データが壊れているため変換できませんでした")
