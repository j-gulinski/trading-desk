import csv
import json
import sys

flow, variant, level, run, usage_path, results_dir = sys.argv[1:7]
with open(usage_path) as usage:
    cores = [round(float(row["cpu_percent"]) / 100, 3) for row in csv.DictReader(usage)]
point = {
    "variant": variant, "level": int(level), "run": int(run),
    "result": json.load(sys.stdin), "cpu_cores": cores,
}
with open(f"{results_dir}/{flow}.jsonl", "a") as out:
    out.write(json.dumps(point) + "\n")
print(flow, variant, level, run)
