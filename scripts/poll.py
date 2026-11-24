#!/usr/bin/env python3
"""위험물 법령·소방청 공지 일일 폴링.
- law.go.kr 현행 법령/행정규칙 버전(공포번호·시행일) 확인 → 바뀌면 본문 전체를 받아 조문 단위 diff
- nfa.go.kr 공지사항·보도자료('위험물' 검색), 행정예고 목록에서 신규 게시물(cntId/제목) 감지
결과: monitor/out/report_YYYY-MM-DD.json  (state는 monitor/state/)
사용: python3 poll.py [--init]   (--init: 기준선만 저장, 전부 '변경 없음' 처리)
"""
import re, json, os, sys, html, difflib, datetime, subprocess, urllib.parse, time

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "state"); OUT = os.path.join(BASE, "out")
os.makedirs(STATE, exist_ok=True); os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0"
INIT = "--init" in sys.argv

LAWS = [  # key, 표시명, 종류(law/adm), law.go.kr 이름
    ("act", "위험물안전관리법", "law", "위험물안전관리법"),
    ("decree", "위험물안전관리법 시행령", "law", "위험물안전관리법시행령"),
    ("rule", "위험물안전관리법 시행규칙", "law", "위험물안전관리법시행규칙"),
    ("detail", "위험물안전관리에 관한 세부기준(소방청 고시)", "adm", "위험물안전관리에관한세부기준"),
    ("prevadmin", "위험물 예방행정 처리규정(소방청 훈령)", "adm", "위험물예방행정처리규정"),
]
NFA = [  # key, 게시판명, url, 필터(제목에 포함되어야 할 키워드 or None)
    ("notice", "소방청 공지사항", "https://www.nfa.go.kr/nfa/news/notice/?mode=list&boardId=bbs_0000000000000009&searchCondition=all&searchKeyword=%EC%9C%84%ED%97%98%EB%AC%BC&pageIdx=1", None),
    ("press", "소방청 보도자료", "https://www.nfa.go.kr/nfa/news/pressrelease/press/?mode=list&boardId=bbs_0000000000000010&searchCondition=all&searchKeyword=%EC%9C%84%ED%97%98%EB%AC%BC&pageIdx=1", None),
    ("adminnotice", "소방청 행정예고", "https://www.nfa.go.kr/nfa/publicrelations/legalinformation/administration/", "위험물"),
]

def get(url):
    r = subprocess.run(["curl", "-sL", "-m", "40", "-A", UA, url], capture_output=True)
    return r.stdout.decode("utf-8", "ignore")

def strip(h):
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", h)
    t = html.unescape(re.sub(r"<[^>]+>", "", h))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())

def law_version(kind, name):
    path = ("법령/" if kind == "law" else "행정규칙/") + name
    p = get("https://www.law.go.kr/" + urllib.parse.quote(path))
    if kind == "law":
        seq = re.search(r"lsiSeq\s*[:=]\s*'?\"?(\d+)", p)
        ef = re.search(r"시행 (\d{4})\. ?(\d{1,2})\. ?(\d{1,2})\.\]", p)
        anc = re.search(r"((?:법률|대통령령|[가-힣]+부령|총리령) 제\d+호, [\d. ]+\.,? ?[가-힣]*)", p)
        if not seq: return None
        efYd = "%s%02d%02d" % tuple(map(int, ef.groups())) if ef else ""
        ver = (anc.group(1).strip() if anc else "") + f" [시행 {efYd}]"
        body_url = f"https://www.law.go.kr/LSW/lsInfoR.do?lsiSeq={seq.group(1)}&efYd={efYd}&chrClsCd=010202&ancYnChk=0&nwJoYnInfo=Y&efGubun=Y"
        page_url = f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={seq.group(1)}&efYd={efYd}"
    else:
        seq = re.search(r"admRulSeq\s*[:=]\s*'?\"?(\d+)", p)
        anc = re.search(r"([가-힣]+(?:고시|훈령|예규) 제[\d-]+호, [\d. ]+\.,? ?[가-힣]*)", p)
        if not seq: return None
        ver = anc.group(1).strip() if anc else seq.group(1)
        body_url = f"https://www.law.go.kr/LSW/admRulInfoR.do?admRulSeq={seq.group(1)}"
        page_url = f"https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq={seq.group(1)}"
    return {"version": ver, "seq": seq.group(1), "body_url": body_url, "page_url": page_url}

def split_articles(text):
    parts = re.split(r"(?m)^(?=제\d+조(?:의\d+)?\()", text)
    arts = {}
    for p in parts:
        m = re.match(r"(제\d+조(?:의\d+)?)\(([^)]*)\)", p)
        if m:
            k = m.group(1); i = 2
            while k in arts: k = f"{m.group(1)}#{i}"; i += 1   # 부칙 조문 등 중복 번호
            arts[k] = p.strip()
    return arts

def diff_articles(old, new):
    o, n = split_articles(old), split_articles(new)
    ch = []
    for k in n:
        if k not in o: ch.append({"조문": k, "구분": "신설", "신": n[k][:1500]})
        elif o[k] != n[k]:
            d = [l for l in difflib.unified_diff(o[k].splitlines(), n[k].splitlines(), lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]
            ch.append({"조문": k, "구분": "개정", "diff": "\n".join(d)[:2000]})
    for k in o:
        if k not in n: ch.append({"조문": k, "구분": "삭제/이동", "구": o[k][:500]})
    if not o and not n:
        d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0))
        ch.append({"조문": "(전체)", "구분": "변경", "diff": "\n".join(d)[:3000]})
    return ch

def nfa_items(url, flt):
    t = ""
    for _ in range(3):
        t = get(url)
        if "<tr" in t: break
        time.sleep(5)
    items = []; rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
    if not rows: raise RuntimeError("목록 수신 실패")
    for r in rows:
        a = re.search(r'href="([^"]*)"[^>]*>(.*?)</a>', r, re.S)
        if not a: continue
        title = re.sub(r"<[^>]+>|\s+", " ", a.group(2)).strip()
        if not title or (flt and flt not in title): continue
        href = html.unescape(a.group(1)); cid = re.search(r"cntId=(\d+)", href)
        dates = re.findall(r"20\d\d[.-]\d\d[.-]\d\d", r)
        link = urllib.parse.urljoin(url, href) if cid else url
        items.append({"id": cid.group(1) if cid else title, "title": title, "date": dates[-1] if dates else "", "url": link})
    return items

def main():
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d")
    sp = os.path.join(STATE, "state.json")
    st = json.load(open(sp)) if os.path.exists(sp) else {"laws": {}, "nfa": {}}
    rep = {"date": today, "law_changes": [], "law_checked": [], "nfa_new": [], "nfa_latest": [], "errors": []}
    for key, label, kind, name in LAWS:
        try:
            v = law_version(kind, name)
            if not v: rep["errors"].append(f"{label}: 버전 확인 실패"); continue
            rep["law_checked"].append({"법령": label, "현행": v["version"], "url": v["page_url"]})
            prev = st["laws"].get(key); tp = os.path.join(STATE, f"{key}.txt")
            if prev and prev["version"] == v["version"] and os.path.exists(tp): continue
            body = strip(get(v["body_url"]))
            if len(body) < 500: rep["errors"].append(f"{label}: 본문 수신 실패"); continue
            if prev and os.path.exists(tp) and not INIT:
                old = open(tp).read()
                rep["law_changes"].append({"법령": label, "이전": prev["version"], "현행": v["version"], "url": v["page_url"], "조문변경": diff_articles(old, body)})
                os.makedirs(os.path.join(STATE, "history"), exist_ok=True)
                os.replace(tp, os.path.join(STATE, "history", f"{key}_{today}_old.txt"))
            open(tp, "w").write(body)
            st["laws"][key] = {"version": v["version"], "seq": v["seq"], "checked": today}
        except Exception as e:
            rep["errors"].append(f"{label}: {e}")
    for key, label, url, flt in NFA:
        try:
            items = nfa_items(url, flt)
            rep["nfa_latest"] += [{"게시판": label, **i} for i in items[:3]]
            seen = set(st["nfa"].get(key, []))
            new = [i for i in items if i["id"] not in seen]
            if seen and not INIT:
                for i in new: rep["nfa_new"].append({"게시판": label, **i})
            st["nfa"][key] = sorted(seen | {i["id"] for i in items})
        except Exception as e:
            rep["errors"].append(f"{label}: {e}")
    json.dump(st, open(sp, "w"), ensure_ascii=False, indent=1)
    op = os.path.join(OUT, f"report_{today}.json")
    json.dump(rep, open(op, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
