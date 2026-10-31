import warnings

# 読み込みを許可する形式。内容から判定し、ここに無い形式（TIFF など）は拒否する。
ALLOWED_INPUT_FORMATS = ["PNG", "JPEG", "WEBP", "BMP", "GIF"]

# 画像の最大画素数。これを超える画像は「画像爆弾」の可能性があるため拒否する。
MAX_PIXELS = 25_000_000

# 出力形式名 -> (Pillow の形式名)
_OUTPUT_FORMATS = {
    "png": "PNG",
    "jpeg": "JPEG",
    "webp": "WEBP",
    "bmp": "BMP",
    "gif": "GIF",
}


def make_converter(target):
    """画像を target 形式（png / jpeg / webp / bmp / gif）へ変換する関数を作る。"""

    pillow_format = _OUTPUT_FORMATS[target]

    def convert(input_path, output_path):
        _convert(input_path, output_path, pillow_format)

    convert.__name__ = f"image_to_{target}"
    return convert


def load_image(input_path):
    """画像を安全に読み込み、向きを補正した Pillow の画像を返す。

    形式は拡張子ではなく中身で判定し、許可していない形式と巨大な画像は拒否する。
    入力ファイルに起因するエラーはすべて ValueError にする。
    """

    # Pillow は必要になったときだけ読み込む（未導入でもテキスト変換は使えるように）
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS

    try:
        with warnings.catch_warnings():
            # 上限超過の警告を例外にする
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(input_path, formats=ALLOWED_INPUT_FORMATS) as source:
                source.load()
                # GIF アニメは最初のフレームだけを使う（load() 後は先頭フレーム）
                image = ImageOps.exif_transpose(source)
                return image.copy()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError(
            f"画像が大きすぎます（最大 {MAX_PIXELS // 1_000_000} メガピクセル）"
        ) from None
    except Image.UnidentifiedImageError:
        raise ValueError(
            "画像として読み込めません（対応: PNG / JPEG / WebP / BMP / GIF）"
        ) from None
    except (OSError, SyntaxError, ValueError):
        # 途中で切れた画像・壊れた画像など
        raise ValueError("画像データが壊れているため読み込めません") from None


def flatten_to_rgb(image):
    """透明を白背景に合成して RGB にする（JPEG や PDF など、透明を持てない形式向け）。"""

    return _prepare(image, "JPEG")


def _convert(input_path, output_path, pillow_format):
    image = load_image(input_path)
    image = _prepare(image, pillow_format)

    # --- 書き出し（ここの OSError はディスクなど環境の問題として呼び出し側に伝える） ---
    # メタデータ（EXIF など）は引き継がない
    save_options = {}
    if pillow_format == "JPEG":
        save_options = {"quality": 90, "optimize": True}
    elif pillow_format == "WEBP":
        save_options = {"quality": 90}

    image.save(output_path, format=pillow_format, **save_options)


def _prepare(image, pillow_format):
    """出力形式で表現できるモードに整える。"""

    from PIL import Image

    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )

    if pillow_format == "JPEG":
        # JPEG は透明を持てないので白背景に合成する
        if has_alpha:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        return image.convert("RGB")

    if pillow_format == "GIF":
        # GIF は 256 色のパレット形式（透明は 1 色のみ）
        return image.convert("RGBA" if has_alpha else "RGB").convert(
            "P", palette=Image.Palette.ADAPTIVE
        )

    if pillow_format == "BMP":
        # BMP は透明を扱いにくいので白背景に合成する
        if has_alpha:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        return image.convert("RGB")

    # PNG / WebP は透明を保てる
    if image.mode in ("RGB", "RGBA", "L", "LA"):
        return image
    return image.convert("RGBA" if has_alpha else "RGB")
