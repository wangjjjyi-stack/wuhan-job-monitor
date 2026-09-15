#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
武汉央国企求职监控 V2
- 检查招聘官网是否变化
- 从招聘页面提取可能的校招/岗位链接
- 对岗位标题/页面文本做规则化简历匹配
- 标记武汉、外派/全国调配风险、技术专业硬门槛
- 更新 data/*.js，供 GitHub Pages 直接显示
"""
from __future__ import annotations
import json, re, time, random, hashlib, os, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG = ROOT / "config"
SNAP = DATA / "snapshots"
SNAP.mkdir(parents=True, exist_ok=True)

TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
UA = "Mozilla/5.0 (compatible; WuhanSOEJobMonitor/2.0; personal job search monitor)"
TIMEOUT = 22

PROFILE = json.loads((CONFIG/"resume_profile.json").read_text(encoding="utf-8"))
TARGETS = json.loads((CONFIG/"targets.json").read_text(encoding="utf-8"))
JOBS = json.loads((DATA/"jobs.json").read_text(encoding="utf-8"))

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
})

RECRUIT_WORDS = [
    "2027","校园招聘","校招","应届生","毕业生","秋季招聘","秋招","招聘职位","加入我们","人才招聘",
    "管培生","管理培训生","报名","投递","网申"
]
CANDIDATE_WORDS = [
    "财务","税务","审计","经营","运营","数字","数据","战略","产业","规划","研究","投资","风控","合规",
    "管理","管培","项目","解决方案","产品","资产","资金","预算","金融"
]
EXCLUDE_LINK_WORDS = ["登录","注册","隐私","免责声明","联系我们","首页","新闻","采购","供应商"]

def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s

def same_domain(a,b):
    try:
        return urlparse(a).netloc.lower().split(":")[0] == urlparse(b).netloc.lower().split(":")[0]
    except Exception:
        return False

def text_hash(text):
    return hashlib.sha256(clean_text(text).encode("utf-8","ignore")).hexdigest()

def requests_fetch(url: str):
    r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.url, r.text

def playwright_fetch(url: str):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise RuntimeError("Playwright unavailable")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, locale="zh-CN")
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(1200)
        html = page.content()
        final = page.url
        browser.close()
        return final, html

def fetch(url: str):
    err1 = None
    try:
        final, html = requests_fetch(url)
        # A small SPA shell or script-only page is better rendered by browser.
        visible = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        if len(visible) >= 500:
            return final, html, "requests"
    except Exception as e:
        err1 = repr(e)
    try:
        final, html = playwright_fetch(url)
        return final, html, "playwright"
    except Exception as e:
        raise RuntimeError(f"requests={err1}; playwright={repr(e)}")

def extract(html: str, base_url: str):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script","style","noscript","svg"]):
        tag.decompose()
    text = clean_text(soup.get_text(" ", strip=True))
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        label = clean_text(a.get_text(" ", strip=True))
        href = urldefrag(urljoin(base_url, a.get("href")))[0]
        if not href.startswith(("http://","https://")):
            continue
        key=(label,href)
        if key in seen:
            continue
        seen.add(key)
        links.append({"title":label[:180], "url":href})
    return title, text, links

def relevant_link(x, base_url):
    label = x["title"]
    u = x["url"]
    blob = (label + " " + u).lower()
    if not label and not same_domain(u, base_url):
        return False
    if any(w in label for w in EXCLUDE_LINK_WORDS):
        return False
    if any(w.lower() in blob for w in RECRUIT_WORDS + CANDIDATE_WORDS):
        return True
    return False

def mobility_risk(text):
    hits=[w for w in PROFILE["avoid_keywords"] if w in text]
    if any(x in text for x in ["长期外派","长期驻外","海外常驻","服从全国调配","全国调配","海外派驻"]):
        level="高"
    elif any(x in text for x in ["项目一线","驻外","海外","长期出差","服从调配"]):
        level="中"
    else:
        level="低"
    return level, hits

def match_score(title, text, company_base=80):
    blob = clean_text((title or "") + " " + (text or ""))[:45000]
    score = 52
    hit_groups={}
    group_weights={"财税审计":18,"经营运营":15,"数字化":16,"研究规划":15,"投资辅助":7}
    for group, words in PROFILE["strong_keywords"].items():
        hits=[w for w in words if w in blob]
        if hits:
            hit_groups[group]=hits[:8]
            score += min(group_weights.get(group,8), 4 + 3*len(hits))
    skill_hits=[w for w in PROFILE["skills"] if w.lower() in blob.lower()]
    score += min(8, len(skill_hits)*2)
    if "武汉" in blob:
        score += 8
    if any(w in blob for w in ["硕士及以上","硕士研究生","研究生及以上"]):
        score += 3
    tech_hits=[w for w in PROFILE["technical_gate_keywords"] if w in blob]
    major_hits=[w for w in PROFILE["technical_major_requirements"] if w in blob]
    if tech_hits:
        score -= 22
    if major_hits and not any(w in blob for w in ["经济","管理","财务","会计","税务","工商"]):
        score -= 12
    risk, risk_hits = mobility_risk(blob)
    if risk=="高": score -= 18
    elif risk=="中": score -= 8

    # Blend a small amount of company-level prior to avoid title-only noise.
    score = round(score*0.82 + company_base*0.18)
    score = max(35, min(98, score))
    return {
        "score":score,
        "hit_groups":hit_groups,
        "skill_hits":skill_hits[:8],
        "technical_hits":tech_hits[:6] + major_hits[:6],
        "mobility_risk":risk,
        "mobility_hits":risk_hits[:6]
    }

def page_signal(text):
    found_2027 = "2027" in text
    recruit_hits=[w for w in RECRUIT_WORDS if w in text]
    if found_2027 and len(recruit_hits)>=2:
        return "发现2027校招/招聘信号", found_2027, recruit_hits[:8]
    if len(recruit_hits)>=3:
        return "招聘页面有活跃信号", found_2027, recruit_hits[:8]
    return "页面可访问，未识别到明确2027信号", found_2027, recruit_hits[:8]

def parse_detail(url, company_base):
    try:
        final, html, engine = fetch(url)
        title, text, links = extract(html, final)
        if len(text)<80:
            return None
        ms=match_score(title, text, company_base)
        return {
            "title": title or "招聘详情",
            "url": final,
            "snippet": text[:700],
            "match":ms,
            "engine":engine
        }
    except Exception:
        return None

discovered=[]
changes=[]
job_by_id={j["id"]:j for j in JOBS}

for idx, t in enumerate(TARGETS,1):
    jid=t["id"]
    j=job_by_id[jid]
    url=t["url"]
    if not url:
        continue
    print(f"[{idx}/{len(TARGETS)}] {t['company']} -> {url}")
    try:
        final, html, engine = fetch(url)
        title, text, links = extract(html, final)
        h=text_hash(text[:120000])
        snap_file=SNAP/f"{jid}.json"
        old={}
        if snap_file.exists():
            try: old=json.loads(snap_file.read_text(encoding="utf-8"))
            except: old={}
        changed = bool(old.get("hash") and old.get("hash") != h)
        signal, found_2027, recruit_hits=page_signal(text)
        j["monitor"]={
            "last_checked":NOW.isoformat(timespec="seconds"),
            "check_status":"ok",
            "signal":signal,
            "page_changed":changed,
            "found_2027":found_2027,
            "engine":engine,
            "error":None
        }
        if changed:
            changes.append({
                "time":NOW.isoformat(timespec="seconds"),
                "company":t["company"],
                "type":"page_changed",
                "message":"招聘入口页面内容发生变化",
                "url":final
            })
        candidates=[x for x in links if relevant_link(x, final)]
        # prioritize same domain + 2027 + job keywords
        def rank(x):
            b=(x["title"]+" "+x["url"]).lower()
            s=0
            if "2027" in b: s+=30
            s+=sum(5 for w in CANDIDATE_WORDS if w.lower() in b)
            if same_domain(x["url"],final): s+=8
            if any(w in x["title"] for w in ["校园招聘","校招","招聘","职位","岗位","管培"]): s+=15
            return s
        candidates=sorted(candidates,key=rank,reverse=True)
        uniq=[]
        urls=set()
        for x in candidates:
            if x["url"] in urls: continue
            urls.add(x["url"]); uniq.append(x)
        candidates=uniq[:int(t.get("max_detail_links",5))]

        old_urls=set(old.get("candidate_urls",[]))
        for x in candidates:
            if x["url"]==final:
                continue
            detail=parse_detail(x["url"], t["manual_match"])
            if not detail:
                continue
            title2 = x["title"] or detail["title"]
            # Only surface plausible recruitment/job details.
            blob=title2+" "+detail["snippet"]
            if not any(w in blob for w in RECRUIT_WORDS+CANDIDATE_WORDS):
                continue
            # For the Fortune 500 Wuhan pool, suppress links with no Wuhan/Hubei location signal.
            if t.get("require_wuhan") and not any(w.lower() in blob.lower() for w in ["武汉","wuhan","湖北","hubei"]):
                continue
            item={
                "id":hashlib.md5((jid+"|"+x["url"]).encode()).hexdigest()[:14],
                "company_id":jid,
                "company":t["company"],
                "pool":t.get("pool","央国企"),
                "fortune_rank_2026":t.get("fortune_rank_2026"),
                "title":title2[:160],
                "url":detail["url"],
                "match":detail["match"]["score"],
                "mobility_risk":detail["match"]["mobility_risk"],
                "mobility_hits":detail["match"]["mobility_hits"],
                "technical_hits":detail["match"]["technical_hits"],
                "hit_groups":detail["match"]["hit_groups"],
                "skill_hits":detail["match"]["skill_hits"],
                "snippet":detail["snippet"][:650],
                "first_seen": old.get("first_seen_by_url",{}).get(x["url"], NOW.date().isoformat()),
                "last_seen": NOW.isoformat(timespec="seconds"),
                "is_new": x["url"] not in old_urls
            }
            discovered.append(item)
            if item["is_new"] and item["match"]>=80:
                changes.append({
                    "time":NOW.isoformat(timespec="seconds"),
                    "company":t["company"],
                    "type":"new_job",
                    "message":f"新发现可能适合的岗位/招聘入口：{title2[:80]}（匹配{item['match']}）",
                    "url":detail["url"]
                })
        first_seen_by_url=dict(old.get("first_seen_by_url",{}))
        for x in candidates:
            first_seen_by_url.setdefault(x["url"], NOW.date().isoformat())
        snap_file.write_text(json.dumps({
            "checked_at":NOW.isoformat(timespec="seconds"),
            "final_url":final,
            "title":title,
            "hash":h,
            "candidate_urls":[x["url"] for x in candidates],
            "first_seen_by_url":first_seen_by_url
        },ensure_ascii=False,indent=2),encoding="utf-8")
    except Exception as e:
        j["monitor"]={
            "last_checked":NOW.isoformat(timespec="seconds"),
            "check_status":"error",
            "signal":"本次检查失败",
            "page_changed":False,
            "found_2027":None,
            "error":str(e)[:500]
        }
        changes.append({
            "time":NOW.isoformat(timespec="seconds"),
            "company":t["company"],
            "type":"error",
            "message":"自动检查失败（官网可能有反爬、登录或页面结构变化）",
            "url":url
        })
    time.sleep(random.uniform(0.8,1.6))

# De-duplicate discovered jobs by normalized URL/title.
seen=set(); clean=[]
for x in sorted(discovered, key=lambda z:(-z["match"],z["company"],z["title"])):
    key=(x["company"],x["url"])
    if key in seen: continue
    seen.add(key); clean.append(x)
discovered=clean

# Preserve a rolling 120-event log.
old_changes=[]
changes_js=DATA/"changes.js"
if changes_js.exists():
    txt=changes_js.read_text(encoding="utf-8")
    m=re.search(r'window\.MONITOR_CHANGES\s*=\s*(\[.*\]);?\s*$',txt,re.S)
    if m:
        try: old_changes=json.loads(m.group(1))
        except: pass
all_changes=(changes+old_changes)[:120]

(DATA/"jobs.json").write_text(json.dumps(JOBS,ensure_ascii=False,indent=2),encoding="utf-8")
(DATA/"jobs.js").write_text("window.JOBS_DATA = "+json.dumps(JOBS,ensure_ascii=False)+";\n",encoding="utf-8")
(DATA/"discovered_jobs.js").write_text("window.DISCOVERED_JOBS = "+json.dumps(discovered,ensure_ascii=False)+";\n",encoding="utf-8")
(DATA/"changes.js").write_text("window.MONITOR_CHANGES = "+json.dumps(all_changes,ensure_ascii=False)+";\n",encoding="utf-8")
(DATA/"monitor_meta.js").write_text(
    "window.MONITOR_META = "+json.dumps({
        "last_run":NOW.isoformat(timespec="seconds"),
        "status":"ok",
        "targets":len(TARGETS),
        "discovered_jobs":len(discovered),
        "changes_this_run":len(changes),
        "message":"自动监控已完成"
    },ensure_ascii=False)+";\n",
    encoding="utf-8"
)
print(f"Done. targets={len(TARGETS)}, discovered={len(discovered)}, changes={len(changes)}")
