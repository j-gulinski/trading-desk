import sys
import time

import psutil

pid, out_path, seconds = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
root = psutil.Process(pid)
tree = [root, *root.children(recursive=True)]
serving = tree[1:] or tree
for process in tree:
    process.cpu_percent()

with open(out_path, "w") as out:
    out.write("second,cpu_percent,rss_mb\n")
    for second in range(1, seconds + 1):
        time.sleep(1)
        cpu = sum(process.cpu_percent() for process in tree)
        rss = sum(process.memory_info().rss for process in serving) / 2**20
        out.write(f"{second},{cpu:.1f},{rss:.1f}\n")
