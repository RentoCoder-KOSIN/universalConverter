"""利用可能な変換処理の登録と管理。

形式を追加するときは、formats/ に変換関数を作り、ここの OPERATIONS に登録する。
変換関数の形: func(input_path: Path, output_path: Path) -> None
入力が不正なら ValueError（または csv.Error）、読み書きの失敗は OSError を送出する。
"""

from converter.formats.archive import targz_to_zip, zip_info, zip_to_targz
from converter.formats.audio import make_converter as make_audio_converter
from converter.formats.csv_json import csv_to_json
from converter.formats.image import make_converter
from converter.formats.json_csv import json_to_csv
from converter.formats.pdf import (
    image_to_pdf,
    pdf_first_page_to_png,
    pdf_to_png_zip,
    pdf_to_txt,
)
from converter.formats.text import json_format, txt_to_utf8
from converter.formats.video import make_converter as make_video_converter

OPERATIONS = {
    # データ
    "csv_to_json": csv_to_json,
    "json_to_csv": json_to_csv,
    # テキスト
    "json_format": json_format,
    "txt_to_utf8": txt_to_utf8,
    # 画像（Pillow が必要。未導入のときは変換実行時にエラーを返す）
    "image_to_png": make_converter("png"),
    "image_to_jpeg": make_converter("jpeg"),
    "image_to_webp": make_converter("webp"),
    "image_to_bmp": make_converter("bmp"),
    "image_to_gif": make_converter("gif"),
    # 音声（FFmpeg / ffprobe が必要。未導入のときは変換実行時にエラーを返す）
    "audio_to_mp3": make_audio_converter("mp3"),
    "audio_to_wav": make_audio_converter("wav"),
    "audio_to_m4a": make_audio_converter("m4a"),
    "audio_to_flac": make_audio_converter("flac"),
    "audio_to_ogg": make_audio_converter("ogg"),
    # 動画（FFmpeg / ffprobe が必要）
    "video_to_mp4": make_video_converter("mp4"),
    "video_to_mp4_small": make_video_converter("mp4_small"),
    "video_to_webm": make_video_converter("webm"),
    "video_extract_audio": make_video_converter("extract_audio"),
    # PDF（pypdf / pypdfium2 / Pillow が必要）
    "pdf_to_txt": pdf_to_txt,
    "pdf_first_page_to_png": pdf_first_page_to_png,
    "pdf_to_png_zip": pdf_to_png_zip,
    "image_to_pdf": image_to_pdf,
    # アーカイブ
    "zip_info": zip_info,
    "zip_to_targz": zip_to_targz,
    "targz_to_zip": targz_to_zip,
}


def get_operation(name):
    """登録済みの変換関数を返す。未登録なら ValueError。"""

    try:
        return OPERATIONS[name]
    except KeyError:
        raise ValueError(f"未対応の変換形式です: {name}") from None


def operation_names():
    return sorted(OPERATIONS)
