import io
import math
import zipfile

# PDF → テキストで読むページ数の上限
MAX_TEXT_PAGES = 200
# PDF → 画像で変換するページ数の上限（ZIP にまとめる場合）
MAX_IMAGE_PAGES = 50
# 画像化する解像度と、1 ページあたりの最大画素数
RENDER_DPI = 150
MAX_RENDER_PIXELS = 25_000_000


def pdf_to_txt(input_path, output_path):
    """PDF の文字（テキストレイヤー）を抜き出して UTF-8 のテキストにする。"""

    reader = _open_reader(input_path)
    page_count = len(reader.pages)

    if page_count > MAX_TEXT_PAGES:
        raise ValueError(f"ページ数が多すぎます（最大 {MAX_TEXT_PAGES} ページ）")

    texts = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:  # 壊れたページは飛ばし、他のページは読む
            texts.append("")

    result = "\n\n".join(texts).strip()

    if not result:
        raise ValueError(
            "テキストを取り出せませんでした（スキャンした画像だけの PDF の可能性があります）"
        )

    with open(output_path, "w", encoding="utf-8", newline="\n") as file:
        file.write(result + "\n")


def pdf_first_page_to_png(input_path, output_path):
    """PDF の最初のページを PNG にする。"""

    with _open_pdfium(input_path) as pdf:
        image = _render_page(pdf, 0)

    image.save(output_path, format="PNG")


def pdf_page_to_png(input_path, output_path, page_number):
    """PDF の指定ページ（1 始まり）を PNG にする。"""

    if page_number is None or page_number < 1 or page_number > MAX_IMAGE_PAGES:
        raise ValueError(f"ページ番号は 1 から {MAX_IMAGE_PAGES} の範囲で指定してください")

    with _open_pdfium(input_path) as pdf:
        if page_number > len(pdf):
            raise ValueError(f"指定したページがありません（全 {len(pdf)} ページ）")

        image = _render_page(pdf, page_number - 1)

    image.save(output_path, format="PNG")


def pdf_to_png_zip(input_path, output_path):
    """PDF の全ページを PNG にして、ZIP にまとめる（page_001.png, page_002.png ...）。"""

    with _open_pdfium(input_path) as pdf:
        page_count = len(pdf)

        if page_count > MAX_IMAGE_PAGES:
            raise ValueError(f"ページ数が多すぎます（最大 {MAX_IMAGE_PAGES} ページ）")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index in range(page_count):
                image = _render_page(pdf, index)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                archive.writestr(f"page_{index + 1:03d}.png", buffer.getvalue())


def image_to_pdf(input_path, output_path):
    """画像（PNG / JPEG / WebP / BMP / GIF）を 1 ページの PDF にする。"""

    from converter.formats.image import flatten_to_rgb, load_image

    image = flatten_to_rgb(load_image(input_path))

    # メタデータは引き継がない。解像度を指定して、ページの大きさを決める。
    image.save(output_path, format="PDF", resolution=float(RENDER_DPI))


# ---- 内部処理 -------------------------------------------------------------


def _open_reader(input_path):
    """pypdf で PDF を開く。壊れている・パスワード付きの場合は ValueError。"""

    from pypdf import PdfReader

    try:
        reader = PdfReader(str(input_path))

        if reader.is_encrypted:
            raise ValueError("パスワードで保護された PDF には対応していません")

        len(reader.pages)  # ページ構造を実際に読んで、壊れていればここで失敗させる
        return reader
    except ValueError:
        raise
    except (ImportError, OSError):
        raise
    except Exception:
        # pypdf は壊れたファイルでさまざまな例外を出すため、入力の問題としてまとめる
        raise ValueError("PDF として読み込めません") from None


class _open_pdfium:
    """pypdfium2 で PDF を開くコンテキスト。"""

    def __init__(self, input_path):
        import pypdfium2 as pdfium

        try:
            self.pdf = pdfium.PdfDocument(str(input_path))
        except pdfium.PdfiumError as error:
            message = str(error)
            if "password" in message.lower():
                raise ValueError("パスワードで保護された PDF には対応していません") from None
            raise ValueError("PDF として読み込めません") from None

    def __enter__(self):
        if len(self.pdf) == 0:
            raise ValueError("ページがない PDF です")
        return self.pdf

    def __exit__(self, *exc_info):
        self.pdf.close()
        return False


def _render_page(pdf, index):
    """1 ページを RGB の画像にする。巨大なページは画素数の上限に収まるよう縮小する。"""

    page = pdf[index]
    try:
        width, height = page.get_size()  # 単位はポイント（1/72 インチ）

        if width <= 0 or height <= 0:
            raise ValueError("ページの大きさが不正です")

        scale = RENDER_DPI / 72.0
        pixels = (width * scale) * (height * scale)

        if pixels > MAX_RENDER_PIXELS:
            scale *= math.sqrt(MAX_RENDER_PIXELS / pixels)

        return page.render(scale=scale).to_pil().convert("RGB")
    finally:
        page.close()
