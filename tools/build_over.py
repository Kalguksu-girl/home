#!/usr/bin/env python3
"""15억 초과 단지 탐색 - data.json 생성.
사용: python3 build_premium.py --key <서비스키> --out data.json
서울 25개 구 + 경기 규제지역. 최근 6개월(전체 지역) / 12개월(인기 8개 구) 매매·전세 실거래, 전용 40㎡ 이상, 중위가 15억 초과."""
import argparse, json, re, html, time, statistics as st, collections, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor
BASE = "https://apis.data.go.kr/1613000/"
SALE = "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RENT = "RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
AREAS = {
 '11110':('서울 종로',15),'11140':('서울 중구',12),'11170':('서울 용산',15),'11200':('서울 성동',25),'11215':('서울 광진',30),'11230':('서울 동대문',35),
 '11260':('서울 중랑',45),'11290':('서울 성북',35),'11305':('서울 강북',45),'11320':('서울 도봉',50),'11350':('서울 노원',55),'11380':('서울 은평',35),
 '11410':('서울 서대문',12),'11440':('서울 마포',6),'11470':('서울 양천',15),'11500':('서울 강서',25),'11530':('서울 구로',15),'11545':('서울 금천',20),
 '11560':('서울 영등포',6),'11590':('서울 동작',6),'11620':('서울 관악',15),'11650':('서울 서초',10),'11680':('서울 강남',15),'11710':('서울 송파',25),'11740':('서울 강동',40),
 '41210':('광명',30),'41450':('하남',60),'41290':('과천',30),'41173':('안양 동안',40),'41131':('성남 수정',55),'41133':('성남 중원',55),'41135':('성남 분당',35),
 '41430':('의왕',40),'41465':('용인 수지',45),'41463':('용인 기흥',65),'41111':('수원 장안',50),'41117':('수원 영통',70),'41115':('수원 팔달',45),'41310':('구리',55)}
POPULAR = {'11470':'양천','11500':'강서','11410':'서대문','11110':'종로','11560':'영등포','11440':'마포','11170':'용산','11590':'동작','11650':'서초','11680':'강남','11710':'송파'}
MIN = 150000

def fetch(key, ep, lawd, ymd):
    out, page = [], 1
    while True:
        url = f"{BASE}{ep}?serviceKey={key}&LAWD_CD={lawd}&DEAL_YMD={ymd}&numOfRows=1000&pageNo={page}"
        for a in range(3):
            try: t = urllib.request.urlopen(url, timeout=40).read().decode("utf-8"); break
            except Exception as e:
                if a == 2: return None, str(e)
                time.sleep(2)
        if "<resultCode>000</resultCode>" not in t:
            m = re.search(r"<(?:errMsg|returnAuthMsg|resultMsg)>(.*?)<", t); return None, m.group(1) if m else t[:100]
        for it in re.findall(r"<item>(.*?)</item>", t, re.S):
            out.append({k: v.strip() for k, v in re.findall(r"<(\w+)>(.*?)</\1>", it, re.S)})
        total = int((re.search(r"<totalCount>(\d+)", t) or [0, 0])[1])
        if page * 1000 >= total: return out, None
        page += 1

def months_back(n):
    d = dt.date.today().replace(day=1); r = []
    for _ in range(n): r.append(d.strftime("%Y%m")); d = (d - dt.timedelta(days=1)).replace(day=1)
    return r

def num(s):
    try: return float(str(s).replace(",", ""))
    except: return None

def collect(key, codes, nmonths):
    yms = months_back(nmonths)
    jobs = [(ep, g, y) for g in codes for y in yms for ep in (SALE, RENT)]
    with ThreadPoolExecutor(10) as ex: res = list(ex.map(lambda j: (j, fetch(key, *j)), jobs))
    S = collections.defaultdict(list); R = collections.defaultdict(list); meta = {}; errs = 0
    for (ep, g, y), (rows, err) in res:
        if err: errs += 1; continue
        for r in rows:
            ar = num(r.get("excluUseAr"))
            if not ar or ar < 40: continue
            k = (g, html.unescape(r.get("aptNm", "")), int(round(ar)), r.get("umdNm"))
            if ep == SALE:
                if r.get("cdealType", "").strip(): continue
                d = f"{r.get('dealYear')}-{int(r.get('dealMonth',0)):02d}-{int(r.get('dealDay',0)):02d}"
                S[k].append((d, num(r.get("dealAmount")), r.get("floor"))); meta[k] = int(num(r.get("buildYear")) or 0)
            elif (num(r.get("monthlyRent")) or 0) == 0 and num(r.get("deposit")):
                R[k].append(num(r.get("deposit")))
    return S, R, meta, yms, errs

def rows_from(S, R, meta, minn, namefn):
    out = []
    for k, v in S.items():
        if len(v) < minn: continue
        m = st.median([x[1] for x in v])
        if m <= MIN: continue
        g, apt, ar, dong = k; last = max(v); rd = R.get(k, []); rm = st.median(rd) if len(rd) >= 2 else None
        out.append(dict(area=namefn(g), commute=AREAS[g][1], dong=dong, apt=apt, sq=ar, built=meta[k], med=round(m / 1e4, 2), n=len(v),
                        last=last[0], lastAmt=round(last[1] / 1e4, 2), lastFloor=last[2], rent=round(rm / 1e4, 2) if rm else None,
                        ratio=round(rm / m * 100) if rm else None))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--key", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    S, R, meta, yms, e1 = collect(a.key, AREAS, 7)
    cands = rows_from(S, R, meta, 3, lambda g: AREAS[g][0])
    # 지역 요약: 15억 초과 거래 비중, 15억 초과 거래 중위
    summ = []
    for g, (nm, cm) in AREAS.items():
        allv = [x[1] for k, v in S.items() if k[0] == g for x in v]
        hi = [x for x in allv if x > MIN]
        if not allv: continue
        summ.append(dict(area=nm, commute=cm, n=len(allv), hi=len(hi), share=round(len(hi) / len(allv) * 100), himed=round(st.median(hi) / 1e4, 1) if hi else None))
    S2, R2, meta2, yms2, e2 = collect(a.key, POPULAR, 12)
    pop = rows_from(S2, R2, meta2, 2, lambda g: POPULAR[g])
    kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
    data = dict(updated=kst.strftime("%Y-%m-%d %H:%M"), asof=f"최근 6개월 계약분 ({yms[-1][:4]}.{yms[-1][4:]}~{yms[0][:4]}.{yms[0][4:]})",
                popAsof=f"최근 12개월 계약분 ({yms2[-1][:4]}.{yms2[-1][4:]}~{yms2[0][:4]}.{yms2[0][4:]})", summary=summ, cands=cands, popular=pop, errors=e1 + e2)
    json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"cands={len(cands)} popular={len(pop)} errors={e1+e2}")

if __name__ == "__main__": main()
