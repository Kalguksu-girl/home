# 새 데이터가 비었거나 30% 이상 줄면 이전 파일로 되돌린다.
import json, sys, shutil
new, prev, keys = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
def n(p, k):
    try:
        v = json.load(open(p)).get(k)
        return len(v) if v is not None else 0
    except Exception:
        return -1
ok = True
for k in keys:
    a, b = n(new, k), n(prev, k)
    print(f"{new} {k}: {b} -> {a}")
    if a <= 0 or (b > 0 and a < b * 0.7):
        ok = False
if not ok:
    shutil.copy(prev, new); print("RESTORED", new)
