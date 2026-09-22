# Samples CPU and memory (RSS) of a server and all its worker processes once a second.
# Usage: python monitor.py <server pid> <out.csv> <seconds>
import sys
import time

import psutil

pid, out, seconds = int(sys.argv[1]), sys.argv[2], float(sys.argv[3])
root = psutil.Process(pid)
seen = {}

with open(out, "w") as f:
    f.write("second,cpu_percent,rss_mb\n")
    for second in range(int(seconds)):
        cpu = rss = 0.0
        for proc in [root, *root.children(recursive=True)]:
            proc = seen.setdefault(proc.pid, proc)
            try:
                cpu += proc.cpu_percent(None)  # since the previous sample; 0 on the first
                rss += proc.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        if second:
            f.write(f"{second},{cpu:.1f},{rss / 2**20:.1f}\n")
        time.sleep(1)
