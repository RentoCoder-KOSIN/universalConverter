import csv
import json

def csv_to_json(input_path, output_path):
    """CSVファイルをJSONファイルに変換"""

    with open(input_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=4)