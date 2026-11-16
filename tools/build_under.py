#!/usr/bin/env python3
"""내 집 마련 판단 도구 - 후보 데이터(data.json) 생성.
사용: python3 build.py --key <URL인코딩 서비스키> --out data.json
최근 6개월 전용 59㎡대(55~62)·84㎡대(80~86) 매매·전세 실거래로 지역·단지별 중위값, 갭, 전세가율 계산.
매매 중위 15억 이하 단지만 후보로 포함.
"""
import argparse, json, re, html, time, statistics as st, collections, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

BASE = "https://apis.data.go.kr/1613000/"
SALE = "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RENT = "RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
# code: (표시명, 구분, 여의도 대중교통 대략 분)
AREAS = {
 '11110':('서울 종로','seoul',15),'11140':('서울 중구','seoul',12),'11170':('서울 용산','seoul',15),'11200':('서울 성동','seoul',25),
 '11215':('서울 광진','seoul',30),'11230':('서울 동대문','seoul',35),'11260':('서울 중랑','seoul',45),'11290':('서울 성북','seoul',35),
 '11305':('서울 강북','seoul',45),'11320':('서울 도봉','seoul',50),'11350':('서울 노원','seoul',55),'11380':('서울 은평','seoul',35),
 '11410':('서울 서대문','seoul',12),'11440':('서울 마포','seoul',6),'11470':('서울 양천','seoul',15),'11500':('서울 강서','seoul',25),
 '11530':('서울 구로','seoul',15),'11545':('서울 금천','seoul',20),'11560':('서울 영등포','seoul',6),'11590':('서울 동작','seoul',6),
 '11620':('서울 관악','seoul',15),'11650':('서울 서초','seoul',10),'11680':('서울 강남','seoul',15),'11710':('서울 송파','seoul',25),'11740':('서울 강동','seoul',40),
 '41210':('광명','gg_reg',30),'41450':('하남','gg_reg',60),'41290':('과천','gg_reg',30),'41173':('안양 동안','gg_reg',40),
 '41131':('성남 수정','gg_reg',55),'41133':('성남 중원','gg_reg',55),'41135':('성남 분당','gg_reg',35),'41430':('의왕','gg_reg',40),
 '41465':('용인 수지','gg_reg',45),'41463':('용인 기흥','gg_reg',65),'41111':('수원 장안','gg_reg',50),'41117':('수원 영통','gg_reg',70),
 '41115':('수원 팔달','gg_reg',45),'41310':('구리','gg_reg',55),
 '41192':('부천 원미','gg_non',30),'41194':('부천 소사','gg_non',25),'41196':('부천 오정','gg_non',35),'41171':('안양 만안','gg_non',30),
 '41410':('군포','gg_non',35),'41281':('고양 덕양','gg_non',30),'41285':('고양 일산동','gg_non',40),'41287':('고양 일산서','gg_non',40),
 '41570':('김포','gg_non',40),'28237':('인천 부평','gg_non',40),'28245':('인천 계양','gg_non',30),'28260':('인천 서구','gg_non',35),
 '28185':('인천 연수(송도)','gg_non',70),'28177':('인천 미추홀','gg_non',45),'28200':('인천 남동','gg_non',50),'41390':('시흥','gg_non',40),
 '41113':('수원 권선','gg_non',50),'41150':('의정부','gg_non',60),'41360':('남양주','gg_non',55),'41480':('파주','gg_non',45),
}


def fetch(key, ep, lawd, ymd):
    out, page = [], 1
    while True:
        url = f"{BASE}{ep}?serviceKey={key}&LAWD_CD={lawd}&DEAL_YMD={ymd}&numOfRows=1000&pageNo={page}"
        for a in range(3):
            try:
                t = urllib.request.urlopen(url, timeout=40).read().decode("utf-8"); break
            except Exception as e:
                if a == 2: return None, str(e)
                time.sleep(2)
        if "<resultCode>000</resultCode>" not in t:
            m = re.search(r"<(?:errMsg|returnAuthMsg|resultMsg)>(.*?)<", t)
            return None, m.group(1) if m else t[:100]
        for it in re.findall(r"<item>(.*?)</item>", t, re.S):
            out.append({k: v.strip() for k, v in re.findall(r"<(\w+)>(.*?)</\1>", it, re.S)})
        total = int((re.search(r"<totalCount>(\d+)", t) or [0, 0])[1])
        if page * 1000 >= total: return out, None
        page += 1


def months_back(n):
    d = dt.date.today().replace(day=1); res = []
    for _ in range(n):
        res.append(d.strftime("%Y%m")); d = (d - dt.timedelta(days=1)).replace(day=1)
    return res


def num(s):
    try: return float(str(s).replace(",", ""))
    except: return None


def size_of(a):
    if a is None: return None
    if 55 <= a <= 62: return 59
    if 80 <= a <= 86: return 84
    return None


POPULAR = {'11470':'양천','11500':'강서','11410':'서대문','11110':'종로','11560':'영등포','11440':'마포','11170':'용산','11590':'동작','11650':'서초','11680':'강남','11710':'송파'}


def build_popular(key):
    yms = months_back(12)
    jobs = [(ep, g, y) for g in POPULAR for y in yms for ep in (SALE, RENT)]
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(lambda j: (j, fetch(key, *j)), jobs))
    S = collections.defaultdict(list); R = collections.defaultdict(list); meta = {}
    for (ep, g, y), (rows, err) in res:
        if err: continue
        for r in rows:
            ar = num(r.get("excluUseAr"))
            if not ar or ar < 20: continue
            k = (g, html.unescape(r.get("aptNm", "")), int(round(ar)), r.get("umdNm"))
            if ep == SALE:
                if r.get("cdealType", "").strip(): continue
                d = f"{r.get('dealYear')}-{int(r.get('dealMonth',0)):02d}-{int(r.get('dealDay',0)):02d}"
                S[k].append((d, num(r.get("dealAmount")), r.get("floor")))
                meta[k] = (r.get("umdNm"), int(num(r.get("buildYear")) or 0))
            elif (num(r.get("monthlyRent")) or 0) == 0 and num(r.get("deposit")):
                R[k].append(num(r.get("deposit")))
    out = []
    for k, v in S.items():
        if len(v) < 2: continue
        amts = [x[1] for x in v]; m = st.median(amts)
        last = max(v)
        if m > 150000 or last[1] > 150000: continue
        g, apt, ar, _d = k; dong, b = meta[k]
        rd = R.get(k, []); rm = st.median(rd) if len(rd) >= 2 else None
        out.append(dict(gu=POPULAR[g], dong=dong, apt=apt, area=ar, py=round(ar / 3.3058 * 1.33), built=b, med=round(m / 1e4, 2), n=len(v),
                        last=last[0], lastAmt=round(last[1] / 1e4, 2), lastFloor=last[2], rent=round(rm / 1e4, 2) if rm else None,
                        gap=round((m - rm) / 1e4, 2) if rm else None))
    out.sort(key=lambda x: -x["n"])
    return out, f"최근 12개월 계약분 ({yms[-1][:4]}.{yms[-1][4:]}~{yms[0][:4]}.{yms[0][4:]})"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--key", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
    yms = months_back(7)
    jobs = [(ep, g, y) for g in AREAS for y in yms for ep in (SALE, RENT)]
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(lambda j: (j, fetch(a.key, *j)), jobs))
    sales, rents, errs = [], [], collections.Counter()
    for (ep, g, y), (rows, err) in res:
        if err: errs["rent" if ep == RENT else "sale"] += 1; continue
        for r in rows:
            sz = size_of(num(r.get("excluUseAr")))
            if not sz: continue
            key = (g, html.unescape(r.get("aptNm", "")), sz, r.get("umdNm"))
            if ep == SALE:
                if r.get("cdealType", "").strip(): continue
                sales.append((key, r.get("umdNm"), int(num(r.get("buildYear")) or 0), num(r.get("dealAmount"))))
            elif (num(r.get("monthlyRent")) or 0) == 0 and num(r.get("deposit")):
                rents.append((key, num(r.get("deposit"))))
    rmap = collections.defaultdict(list)
    for k, d in rents: rmap[k].append(d)
    smap = collections.defaultdict(list); meta = {}
    for k, dong, b, amt in sales: smap[k].append(amt); meta[k] = (dong, b)
    # 지역 요약
    areas = []
    for g, (nm, typ, cm) in AREAS.items():
        row = dict(area=nm, type=typ, commute=cm)
        for sz in (59, 84):
            v = [amt for (k, dong, b, amt) in sales if k[0] == g and k[2] == sz]
            rv = [d for (k, d) in rents if k[0] == g and k[2] == sz]
            row[f"m{sz}"] = round(st.median(v) / 1e4, 1) if v else None
            row[f"r{sz}"] = round(st.median(rv) / 1e4, 1) if rv else None
            row[f"n{sz}"] = len(v)
        areas.append(row)
    # 후보 단지
    cands = []
    for k, v in smap.items():
        if len(v) < 5: continue
        m = st.median(v)
        if m > 150000: continue
        g, apt, sz, _d = k; nm, typ, cm = AREAS[g]; dong, b = meta[k]
        rd = rmap.get(k, [])
        rm = st.median(rd) if len(rd) >= 2 else None
        cands.append(dict(area=nm, type=typ, commute=cm, dong=dong, apt=apt, built=b, size=sz, med=round(m / 1e4, 2), n=len(v),
                          rent=round(rm / 1e4, 2) if rm else None, gap=round((m - rm) / 1e4, 2) if rm else None,
                          ratio=round(rm / m * 100) if rm else None))
    cands.sort(key=lambda x: (-x["n"]))
    kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
    data = dict(updated=kst.strftime("%Y-%m-%d %H:%M"), asof=f"최근 6개월 계약분 ({yms[-1][:4]}.{yms[-1][4:]}~{yms[0][:4]}.{yms[0][4:]})",
                areas=areas, cands=cands, errors=dict(errs))
    data["popular"], data["popAsof"] = build_popular(a.key)
    json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"sales={len(sales)} rents={len(rents)} cands={len(cands)} errs={dict(errs)}")


if __name__ == "__main__":
    main()
