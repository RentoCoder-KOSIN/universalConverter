import csv
import json


def json_to_csv(input_path, output_path):
    """JSONファイル（オブジェクトの配列）をCSVファイルに変換する。"""

    with open(input_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("JSONの最上位は配列である必要があります")

    if not all(isinstance(row, dict) for row in data):
        raise ValueError("JSONの配列の要素はすべてオブジェクトである必要があります")

    # 列は最初に登場した順に集める（行ごとにキーが違っても欠けさせない）
    fieldnames = []
    for row in data:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(output_path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in data:
            writer.writerow({
                key: _to_cell(value) for key, value in row.items()
            })


def _to_cell(value):
    """CSVのセルに入れられる値へ変換する。"""

    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value
