import csv
import json

NUMERICAL_DATA = (
    '#',
    'popularity',
    'dance',
    'energy',
    'acoustic',
    'instrumental',
    'happy',
    'speech',
    'live',
    'tempo',
)

STRIPPED_DATA = (
    'song', '#',
)

def slugify(string):
    return string.strip().replace(" ", "_").lower()

def convert(path):
    json_data = []
    with open(path) as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            processed_row = {}
            try:
                for key, value in row.items():
                    key = slugify(key)
                    if key in STRIPPED_DATA:
                        value = value.strip()
                    if key in NUMERICAL_DATA:
                        value = int(value)
                    processed_row[key] = value
            except ValueError:
                continue
            else:
                json_data.append(processed_row)
    with open(path + ".json", "w") as json_file:
        json.dump(json_data, json_file, indent=4)


if __name__ == "__main__":
    import sys
    convert(sys.argv[1])
