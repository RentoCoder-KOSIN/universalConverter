"""動画の変換（FFmpeg / ffprobe を使う）。audio.py と同じ方針で、安全のために次を守る。

- コマンドは引数の配列で起動し、シェルを通さない。
- ローカルファイルだけを許可し（-protocol_whitelist file）、入力は中身（ffprobe の format_name）で
  判定する。HLS のプレイリストや concat など、他のファイルを参照する形式は拒否する。
- 長さ・解像度・出力サイズに上限を設ける。
- Laravel のタイムアウトより先に FFmpeg を止める（締め切り時刻方式）。
"""

import json
import os
import shutil
import subprocess
import time

# 読み込みを許可するコンテナ形式（ffprobe の format_name に含まれる名前）。
# MP4 / MOV は "mov,mp4,m4a,3gp,3g2,mj2"、WebM は "matroska,webm" と報告される。
ALLOWED_INPUT_FORMATS = {"mov", "matroska", "webm"}

# 入力の最大長（秒）。短くしておくのは、小さなサーバーでも時間内に終わらせるため。
MAX_DURATION_SECONDS = 60

# 入力の最大解像度（1 フレームの画素数）。フル HD まで。
MAX_FRAME_PIXELS = 1920 * 1088

# 出力ファイルの最大サイズ（バイト）。
MAX_OUTPUT_BYTES = 50 * 1024 * 1024

# ffprobe と FFmpeg を合わせた上限（秒）。Laravel 側の CONVERTER_TIMEOUT より短くする。
DEFAULT_TIMEOUT_SECONDS = 25

_TIMEOUT_MESSAGE = "処理に時間がかかりすぎたため中止しました（動画が長い、または解像度が大きい可能性があります）"
_UNREADABLE_MESSAGE = "動画として読み込めません（対応: MP4 / MOV / WebM）"

# 映像は 1 本目、音声は 1 本目だけ（無ければ音声なしで出力）。幅・高さは偶数にそろえる。
_MAP_VIDEO_AND_OPTIONAL_AUDIO = ["-map", "0:v:0", "-map", "0:a:0?"]
_EVEN_SCALE = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

# 出力形式名 -> (ffmpeg に渡す引数, 映像が必要か, 出力コンテナ)
_TARGETS = {
    "mp4": (
        [*_MAP_VIDEO_AND_OPTIONAL_AUDIO,
         "-vf", _EVEN_SCALE,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        True, "mp4",
    ),
    # 圧縮用: 高さを最大 720 に縮小（偶数）し、画質を下げてサイズを小さくする
    "mp4_small": (
        [*_MAP_VIDEO_AND_OPTIONAL_AUDIO,
         "-vf", "scale=-2:'min(720,trunc(ih/2)*2)'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"],
        True, "mp4",
    ),
    "webm": (
        [*_MAP_VIDEO_AND_OPTIONAL_AUDIO,
         "-vf", _EVEN_SCALE,
         "-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0",
         "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", "-pix_fmt", "yuv420p",
         "-c:a", "libopus", "-b:a", "96k"],
        True, "webm",
    ),
    # 動画から音声だけを取り出して MP3 にする
    "extract_audio": (
        ["-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-b:a", "192k"],
        False, "mp3",
    ),
}


def make_converter(target):
    """動画を target（mp4 / mp4_small / webm / extract_audio）へ変換する関数を作る。"""

    options, needs_video, container = _TARGETS[target]
    name = "video_extract_audio" if target == "extract_audio" else f"video_to_{target}"

    def convert(input_path, output_path):
        _convert(input_path, output_path, options, needs_video, container)

    convert.__name__ = name
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


def _probe(ffprobe, input_path, deadline, needs_video):
    """入力の中身を調べる。動画として（または音声付きとして）扱えなければ ValueError。"""

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
        raise ValueError(_UNREADABLE_MESSAGE)

    format_names = set(str(info.get("format", {}).get("format_name", "")).split(","))
    if not format_names & ALLOWED_INPUT_FORMATS:
        raise ValueError(_UNREADABLE_MESSAGE)

    streams = info.get("streams", [])

    # カバー画像（attached_pic）は映像として数えない
    video_streams = [
        s for s in streams
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
    ]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if needs_video and not video_streams:
        raise ValueError("映像が含まれていません")

    if not needs_video and not audio_streams:
        raise ValueError("音声データが含まれていません")

    if video_streams:
        width, height = video_streams[0].get("width"), video_streams[0].get("height")
        if isinstance(width, int) and isinstance(height, int) and width * height > MAX_FRAME_PIXELS:
            raise ValueError("解像度が大きすぎます（最大 1920 x 1080）")

    reference = (video_streams or audio_streams)[0]
    duration = _duration(info, reference)

    if duration is None:
        raise ValueError("動画の長さを確認できないため変換できません")
    if duration > MAX_DURATION_SECONDS:
        raise ValueError(f"動画が長すぎます（最大 {MAX_DURATION_SECONDS} 秒）")


def _duration(info, stream):
    for source in (info.get("format", {}), stream):
        try:
            value = float(source.get("duration"))
        except (TypeError, ValueError):
            continue

        if value >= 0:
            return value

    return None


def _convert(input_path, output_path, options, needs_video, container):
    ffmpeg = _find("ffmpeg", "CONVERTER_FFMPEG")
    ffprobe = _find("ffprobe", "CONVERTER_FFPROBE")
    deadline = time.monotonic() + _timeout()

    _probe(ffprobe, input_path, deadline, needs_video)

    command = [
        ffmpeg,
        "-nostdin", "-hide_banner", "-loglevel", "error",
        "-protocol_whitelist", "file",
        "-y",
        "-i", f"file:{input_path}",
        "-map_metadata", "-1",   # 撮影場所などのメタデータは引き継がない
        *options,
        # 上限に達したら ffmpeg に書き出しを止めさせ、下で拒否する
        "-fs", str(MAX_OUTPUT_BYTES), "-f", container, f"file:{output_path}",
    ]

    result = _run(command, deadline)

    if os.path.isfile(output_path) and os.path.getsize(output_path) >= MAX_OUTPUT_BYTES:
        os.remove(output_path)
        raise ValueError(
            f"変換後のファイルが大きすぎます（最大 {MAX_OUTPUT_BYTES // (1024 * 1024)} MB）"
        )

    if result.returncode != 0 or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        # 失敗した出力は残さない
        try:
            os.remove(output_path)
        except OSError:
            pass

        raise ValueError("動画データが壊れているため変換できませんでした")
