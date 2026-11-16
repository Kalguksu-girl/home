#!/usr/bin/env python3
"""K-apt 단지 정보(세대수·지하철/버스 도보시간·주변 학교) 연결.
사용: python3 enrich.py --key <서비스키> --data data.json --out kapt.json [--prev kapt_prev.json]
data.json의 cands/popular 단지를 (동, 단지명)으로 K-apt 단지 목록과 짝지은 뒤 기본·상세 정보를 받아 저장.
이전 kapt.json을 --prev로 주면 이미 받은 단지는 다시 호출하지 않음(30일 지난 것만 갱신)."""
import argparse, json, re, time, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

BASE = "https://apis.data.go.kr/1613000/"


def get(key, path, tries=3):
    url = f"{BASE}{path}&serviceKey={key}&_type=json"
    for a in range(tries):
        try:
            t = urllib.request.urlopen(url, timeout=40).read().decode("utf-8")
            j = json.loads(t)
            return j.get("response", {}).get("body", {})
        except Exception:
            if a == tries - 1: return None
            time.sleep(2)


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\(.*?\)", lambda m: m.group(0)[1:-1], s)  # 괄호 안 글자는 살리고 괄호만 제거
    s = re.sub(r"[\s\-·.,&()'’]|아파트|apt", "", s)
    s = s.replace("단지", "").replace("차", "")
    return s


def subway_max(t):
    t = (t or "").replace(" ", "")
    m = re.findall(r"(\d+)", t)
    if not m: return None
    if "초과" in t: return 99
    return max(int(x) for x in m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True); ap.add_argument("--prev")
    a = ap.parse_args()
    d = json.load(open(a.data, encoding="utf-8"))
    want = set()
    for k in ("cands", "popular"):
        for x in d.get(k, []):
            want.add((x["dong"], x["apt"]))
    prev = {}
    if a.prev:
        try: prev = json.load(open(a.prev, encoding="utf-8")).get("map", {})
        except Exception: prev = {}
    # 1) 전체 단지 목록
    first = get(a.key, "AptListService4/getTotalAptList4?numOfRows=1000&pageNo=1")
    if not first: raise SystemExit("단지 목록 호출 실패")
    total = int(first.get("totalCount", 0)); pages = (total + 999) // 1000
    with ThreadPoolExecutor(6) as ex:
        rest = list(ex.map(lambda p: get(a.key, f"AptListService4/getTotalAptList4?numOfRows=1000&pageNo={p}"), range(2, pages + 1)))
    items = list(first.get("items", []))
    for b in rest:
        if b: items += b.get("items", [])
    bydong = {}
    for it in items:
        for dn in (it.get("as3"), it.get("as4")):
            if dn: bydong.setdefault(dn.strip(), []).append((norm(it.get("kaptName")), it.get("kaptCode"), it.get("kaptName")))
    # 2) 매칭
    match = {}
    for dong, apt in want:
        cands = bydong.get(dong, []); n = norm(apt)
        if not n or not cands: continue
        exact = [c for c in cands if c[0] == n]
        if len(exact) == 1: match[(dong, apt)] = exact[0]; continue
        cont = [c for c in cands if c[0] and (n in c[0] or c[0] in n)]
        if len(cont) == 1: match[(dong, apt)] = cont[0]
    # 3) 단지 정보 (캐시 활용)
    today = dt.date.today()
    need = {}
    for key, (nn, code, kname) in match.items():
        k = f"{key[0]}|{key[1]}"
        p = prev.get(k)
        if p and p.get("code") == code and (today - dt.date.fromisoformat(p.get("at", "2000-01-01"))).days < 30: continue
        need[code] = kname

    def info(code):
        b = get(a.key, f"AptBasisInfoServiceV5/getAphusBassInfoV5?kaptCode={code}")
        t = get(a.key, f"AptBasisInfoServiceV5/getAphusDtlInfoV5?kaptCode={code}")
        bi = (b or {}).get("item") or {}; ti = (t or {}).get("item") or {}
        if not bi and not ti: return code, None
        hh = bi.get("kaptdaCnt"); hh = int(hh) if hh else None
        park = None
        try:
            pc = float(ti.get("kaptdPcnt") or 0) + float(ti.get("kaptdPcntu") or 0)
            park = round(pc / hh, 2) if hh and pc else None
        except Exception: pass
        edu = re.sub(r"\s+", " ", (ti.get("educationFacility") or "")).strip()
        return code, dict(hh=hh, dongs=int(bi.get("kaptDongCnt") or 0) or None, top=bi.get("ktownFlrNo"),
                          sub=(ti.get("subwayStation") or "").strip() or None, line=(ti.get("subwayLine") or "").strip() or None,
                          subT=(ti.get("kaptdWtimesub") or "").strip() or None, subMax=subway_max(ti.get("kaptdWtimesub")),
                          busT=(ti.get("kaptdWtimebus") or "").strip() or None, edu=edu[:120] or None, park=park, kname=bi.get("kaptName"))
    with ThreadPoolExecutor(8) as ex:
        got = dict(ex.map(info, list(need)))
    out = {}
    for key, (nn, code, kname) in match.items():
        k = f"{key[0]}|{key[1]}"
        if code in got and got[code]:
            out[k] = {**got[code], "code": code, "at": today.isoformat()}
        elif k in prev and prev[k].get("code") == code:
            out[k] = prev[k]
    kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
    json.dump(dict(updated=kst.strftime("%Y-%m-%d %H:%M"), source="국토교통부 공동주택 단지 목록·기본 정보(K-apt)", map=out),
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"want={len(want)} matched={len(match)} fetched={len(need)} saved={len(out)}")


if __name__ == "__main__":
    main()
