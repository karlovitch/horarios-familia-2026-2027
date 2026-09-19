from __future__ import annotations

import argparse
import calendar
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import local
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"history-info.json"
HEADERS={"User-Agent":"HorariosFamilia/2.0 (efemerides historicas; GitHub Pages)"}
_THREAD=local()
MONTHS=["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
PORTUGAL_WORDS=(
    "portugal","português","portuguesa","portugueses","lisboa","porto","coimbra","braga","évora",
    "funchal","madeira","açores","camões","fernando pessoa","saramago","eça de queirós","bocage",
    "afonso henriques","d. joão","d. manuel","d. pedro","marquês de pombal","tap","rtp"
)

def http_session():
    session=getattr(_THREAD,"session",None)
    if session is None:
        retry=Retry(
            total=3,connect=3,read=3,backoff_factor=.5,
            status_forcelist=(429,500,502,503,504),
            allowed_methods=frozenset({"GET"})
        )
        session=requests.Session()
        session.headers.update(HEADERS)
        session.mount("https://",HTTPAdapter(max_retries=retry))
        session.mount("http://",HTTPAdapter(max_retries=retry))
        _THREAD.session=session
    return session

def get(url):
    r=http_session().get(url,timeout=25)
    r.raise_for_status()
    return r.text

def parse_year_text(text):
    text=re.sub(r"\s+"," ",text).strip()
    m=re.match(r"^([0-9]{1,4}(?:\s*a\.?\s*C\.?)?)\s*[—–-]\s*(.+)$",text,re.I)
    if not m:
        return None
    return {"year":m.group(1).strip(),"text":m.group(2).strip()}

def wikipedia_article_from_li(li,wiki_url):
    for a in li.find_all("a",href=True):
        href=a.get("href","")
        if not href.startswith("/wiki/"):continue
        if any(x in href for x in (":","Ficheiro:","Categoria:","Wikip%C3%A9dia:")):continue
        return urljoin("https://pt.wikipedia.org",href)
    return ""

def wikipedia_best_match(year,text):
    q=f"{year} {text[:220]}".strip()
    try:
        r=http_session().get(
            "https://pt.wikipedia.org/w/api.php",
            params={"action":"query","list":"search","srsearch":q,"srlimit":1,"format":"json","utf8":1},
            timeout=25
        )
        r.raise_for_status()
        hits=r.json().get("query",{}).get("search",[])
        if hits:
            title=hits[0].get("title","").strip()
            if title:
                return "https://pt.wikipedia.org/wiki/"+quote(title.replace(" ","_"))
    except Exception:
        pass
    return ""

def world_for(day,month):
    month_name=MONTHS[month-1]
    title=f"{day}_de_{month_name}"
    wiki_url=f"https://pt.wikipedia.org/wiki/{quote(title)}"
    out=[]

    # A página diária da Wikipédia em português tem uma secção própria
    # "Eventos históricos", seguida de "Nascimentos". Extraímos apenas esse intervalo.
    try:
        html=get(wiki_url)
        start_match=re.search(
            r'<h2[^>]*id=["\\\']Eventos[^"\\\']*hist[^"\\\']*["\\\'][^>]*>|<h2[^>]*>\\s*Eventos\\s+hist[oó]ricos\\s*</h2>',
            html,re.I
        )
        if start_match:
            tail=html[start_match.start():]
            end_match=re.search(
                r'<h2[^>]*id=["\\\']Nascimentos["\\\'][^>]*>|<h2[^>]*>\\s*Nascimentos\\s*</h2>',
                tail,re.I
            )
            fragment=tail[:end_match.start()] if end_match else tail
            soup=BeautifulSoup(fragment,"html.parser")
            for li in soup.find_all("li"):
                item=parse_year_text(li.get_text(" ",strip=True))
                if item and 20<=len(item["text"])<=500:
                    item["source_url"]=wikipedia_article_from_li(li,wiki_url) or wikipedia_best_match(item["year"],item["text"])
                    if not any(x["year"]==item["year"] and x["text"]==item["text"] for x in out):
                        out.append(item)
            if out:
                return out[:24]
    except Exception:
        pass

    # Fallback: API "On this day" da Wikimedia.
    try:
        feed=f"https://api.wikimedia.org/feed/v1/wikipedia/pt/onthisday/events/{month:02d}/{day:02d}"
        r=http_session().get(feed,timeout=25)
        r.raise_for_status()
        for ev in r.json().get("events",[]):
            year=str(ev.get("year","")).strip()
            text=re.sub(r"\\s+"," ",str(ev.get("text",""))).strip()
            if year and 20<=len(text)<=500:
                source_url=wiki_url
                pages=ev.get("pages") or []
                if pages:
                    title=str(pages[0].get("title","")).strip()
                    if title:
                        source_url="https://pt.wikipedia.org/wiki/"+quote(title.replace(" ","_"))
                item={"year":year,"text":text,"source_url":source_url}
                if not any(x["year"]==year and x["text"]==text for x in out):
                    out.append(item)
    except Exception:
        pass
    return out[:24]

def portugal_for(day,month):
    url=f"https://www.e-cultura.pt/efemeridesDia/{day}-{month}"
    soup=BeautifulSoup(get(url),"html.parser")
    out=[]
    for h in soup.find_all("h2"):
        title=" ".join(h.stripped_strings).strip()
        if not title or len(title)>160:continue
        parent=h.parent
        text=" ".join(parent.stripped_strings) if parent else title
        low=text.lower()
        if not any(w in low for w in PORTUGAL_WORDS):continue
        year=""
        m=re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b",text)
        if m:year=m.group(1)
        desc=text
        if title and desc.startswith(title):desc=desc[len(title):].strip(" -–—")
        # O site inclui frequentemente o texto do botão "Ler mais" na extração.
        # Guardamos o respetivo URL, mas removemos esse rótulo do texto da efeméride.
        desc=re.sub(r"\s*Ler\s+mais\s*\.?\s*$","",desc,flags=re.I)
        desc=re.sub(r"\s+"," ",desc).strip()
        if not desc or len(desc)>600:continue
        source_url=wikipedia_best_match(year or "",desc)
        item={"year":year or "s/d","text":desc,"source_url":source_url}
        if not any(x["text"]==item["text"] for x in out):out.append(item)
    return out[:12]

def one(mmdd):
    month,day=map(int,mmdd.split("-"))
    result={"world":[],"portugal":[]}
    try:result["world"]=world_for(day,month)
    except Exception:pass
    try:result["portugal"]=portugal_for(day,month)
    except Exception:pass
    return mmdd,result

def merge_unique(primary,extra):
    seen={(x.get("year"),x.get("text")) for x in primary}
    for x in extra:
        k=(x.get("year"),x.get("text"))
        if k not in seen:
            primary.append(x);seen.add(k)
    return primary

def all_mmdd():
    out=[]
    for month in range(1,13):
        for day in range(1,calendar.monthrange(2026,month)[1]+1):
            out.append(f"{month:02d}-{day:02d}")
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--all",action="store_true")
    args=ap.parse_args()
    try:data=json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:data={"dates":{}}
    original_data=json.loads(json.dumps(data))
    data.setdefault("dates",{})
    targets=all_mmdd() if args.all else [datetime.now().strftime("%m-%d")]
    workers=8 if args.all else 2
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(one,x):x for x in targets}
        for fut in as_completed(futs):
            mmdd,result=fut.result()
            cur=data["dates"].setdefault(mmdd,{"world":[],"portugal":[]})
            cur["world"]=merge_unique(cur.get("world",[]),result["world"])
            cur["portugal"]=merge_unique(cur.get("portugal",[]),result["portugal"])
    data["dates"]={k:data["dates"][k] for k in sorted(data["dates"])}
    sources={
        "world":"Wikipédia em português — secção Eventos históricos das páginas de cada data",
        "portugal":"e-Cultura / Centro Nacional de Cultura — Efemérides"
    }
    previous_payload={
        "dates": original_data.get("dates", {}),
        "sources": original_data.get("sources", {}),
    }
    payload={"dates":data["dates"],"sources":sources}
    generated_at=original_data.get("generated_at") if previous_payload==payload else datetime.now(timezone.utc).isoformat()
    data={"generated_at":generated_at or datetime.now(timezone.utc).isoformat(),**payload}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Efemérides atualizadas: {len(targets)} datas; total guardado: {len(data['dates'])}")

if __name__=="__main__":
    main()
