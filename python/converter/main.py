import argparse
import csv
import json
import sys
import traceback
from pathlib import Path

from converter.registry import get_operation, operation_names


def convert(operation, input_path, output_path):
    """指定された変換処理を実行する。"""

    func = get_operation(operation)

    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.is_file():
        raise FileNotFoundError(
            f"入力ファイルが見つかりません: {input_file}"
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)

    func(input_file, output_file)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="万能ファイル変換ツール"
    )

    parser.add_argument(
        "operation",
        choices=operation_names(),
        help="実行する変換処理",
    )

    parser.add_argument("input", help="入力ファイルのパス")
    parser.add_argument("output", help="出力ファイルのパス")

    args = parser.parse_args()

    try:
        output_file = convert(
            args.operation,
            args.input,
            args.output,
        )

        print(json.dumps({
            "success": True,
            "output": str(output_file),
        }, ensure_ascii=False))

    except (ValueError, csv.Error) as error:
        # 入力内容の問題。メッセージに内部パスは含まれないので表示してよい。
        _fail("invalid_input", str(error))

    except ImportError:
        # 変換に必要なライブラリ・外部ツール（Pillow / FFmpeg など）が入っていない。環境の問題。
        _fail("unavailable", "この変換に必要なライブラリまたは外部ツールが見つかりません")

    except OSError as error:
        # ファイルの欠損・権限など。メッセージにパスが含まれるため
        # 呼び出し側には汎用メッセージだけを返す。
        _fail("io_error", "ファイルの読み書きに失敗しました")

    except Exception:
        # 想定外のエラー。詳細は標準エラーに出し（利用者には見せない）、結果は JSON で返す。
        traceback.print_exc(file=sys.stderr)
        _fail("internal_error", "変換中に予期しないエラーが発生しました")


def _fail(code, message):
    print(json.dumps({
        "success": False,
        "code": code,
        "error": message,
    }, ensure_ascii=False))

    sys.exit(1)


if __name__ == "__main__":
    main()
