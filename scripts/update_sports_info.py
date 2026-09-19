from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sports-info.json"

HEADERS = {"User-Agent":"HorariosFamilia/3.0 (+GitHub Pages; atualização de agendas desportivas)"}
SOURCES = [
    {"entity":"FC Porto","sport":"Futebol","url":"https://www.zerozero.pt/equipa/fc-porto/agenda?agenda_zz=0&date=2026-09-19&grp=&id_compet=0&id_equipa=9&op=std","kind":"zerozero"},
    {"entity":"Gil Vicente FC","sport":"Futebol","url":"https://www.zerozero.pt/equipa/gil-vicente/jogos","kind":"zerozero"},
    {"entity":"Óquei Clube de Barcelos","sport":"Hóquei em Patins","url":"https://www.zerozero.pt/equipa/oc-barcelos/agenda","kind":"zerozero"},
    {"entity":"Seleção Nacional A","sport":"Futebol","url":"https://www.fpf.pt/pt/selecoes/futebol-masculino/selecao-a/jogos","kind":"fpf"},
    {"entity":"Seleção Nacional Sub-21","sport":"Futebol","url":"https://www.fpf.pt/pt/selecoes/futebol-masculino/selecao-sub-21/jogos","kind":"fpf"},
]

CHANNELS = ["Sport TV 1","Sport TV 2","Sport TV 3","Sport TV 4","Sport TV 5","Sport TV","RTP 1","RTP 2","Canal 11","Porto Canal","V+"]
COMP_MARKERS = ["Liga Portugal","UEFA Champions League","UEFA Liga das Nações","Allianz Cup","Amigáveis Clubes","Campeonato Placard","WSE Champions League","Taça do Minho","Taça de Portugal","Qualificação","Campeonato Europa"]

def get(url):
    try:
        r=requests.get(url,headers={**HEADERS,"Accept-Language":"pt-PT,pt;q=0.9,en;q=0.7"},timeout=30)
        r.raise_for_status()
        return r.text
    except Exception:
        # Fallback de leitura pública para fontes que bloqueiam pedidos de datacenter.
        clean=re.sub(r"^https?://","",url)
        jr=requests.get("https://r.jina.ai/http://"+clean,headers=HEADERS,timeout=45)
        jr.raise_for_status()
        return jr.text

def load():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"events":[]}

def season_date(token):
    token=token.strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}",token):
        return token
    m=re.fullmatch(r"(\d{2})/(\d{2})",token)
    if not m:return None
    d,mn=map(int,m.groups())
    y=2026 if mn>=7 else 2027
    return f"{y:04d}-{mn:02d}-{d:02d}"

def infer_location(home):
    h=home.lower()
    known=[
      ("fc porto","Estádio do Dragão, Porto, Portugal"),
      ("gil vicente","Estádio Cidade de Barcelos, Barcelos, Portugal"),
      ("oc barcelos","Pavilhão Municipal de Barcelos, Barcelos, Portugal"),
      ("portugal","Portugal · estádio/localidade a confirmar"),
      ("benfica","Estádio da Luz, Lisboa, Portugal"),
      ("sporting","Lisboa, Portugal"),
      ("marítimo","Funchal, Portugal"),
      ("moreirense","Moreira de Cónegos, Portugal"),
      ("vitória sc","Guimarães, Portugal"),
      ("santa clara","Ponta Delgada, Portugal"),
    ]
    for needle,loc in known:
        if needle in h:return loc
    return "Local a confirmar"

def normalize_time(date_iso,time_text):
    if not time_text or time_text=="-:-":return None
    # As fontes portuguesas apresentam normalmente a hora portuguesa; guardamos com
    # offset de Lisboa aproximado e a app converte depois para o fuso do dispositivo.
    hh,mm=map(int,time_text.split(":"))
    month=int(date_iso[5:7])
    offset="+01:00" if 3<=month<=10 else "+00:00"
    return f"{date_iso}T{hh:02d}:{mm:02d}:00{offset}"

def parse_zerozero(src,html):
    soup=BeautifulSoup(html,"html.parser")
    found=[]
    for row in soup.find_all(["tr","li"]):
        text=" ".join(row.stripped_strings)
        if " vs " not in text:continue
        dm=re.search(r"(20\d{2}-\d{2}-\d{2}|\b\d{2}/\d{2}\b)",text)
        tm=re.search(r"\b(\d{2}:\d{2}|-:-)\b",text)
        if not dm:continue
        date_iso=season_date(dm.group(1))
        if not date_iso:continue
        after=text[dm.end():].strip()
        if tm:
            pos=after.find(tm.group(1))
            if pos>=0:after=after[pos+len(tm.group(1)):].strip()
        marker_pos=min([after.find(x) for x in COMP_MARKERS if after.find(x)>0] or [len(after)])
        match_text=after[:marker_pos].strip()
        comp=after[marker_pos:].strip() if marker_pos<len(after) else ""
        mm=re.search(r"(.+?)\s+vs\s+(.+)",match_text)
        if not mm:continue
        home=re.sub(r"\s+"," ",mm.group(1)).strip(" -")
        away=re.sub(r"\s+"," ",mm.group(2)).strip(" -")
        if len(home)>80 or len(away)>80:continue
        channel=next((ch for ch in CHANNELS if ch.lower() in text.lower()),"Transmissão a confirmar")
        link=None
        for a in row.find_all("a",href=True):
            if "/jogo/" in a["href"] or "/live-ao-minuto/" in a["href"]:
                link=urljoin(src["url"],a["href"]);break
        found.append({
          "date":date_iso,"start":normalize_time(date_iso,tm.group(1) if tm else None),
          "entity":src["entity"],"sport":src["sport"],"home":home,"away":away,
          "competition":comp or "Competição a confirmar","location":infer_location(home),
          "channel":channel,"match_url":link or src["url"],"source_url":src["url"]
        })
    return found

def parse_fpf(src,html):
    soup=BeautifulSoup(html,"html.parser")
    text="\n".join(re.sub(r"\s+"," ",x).strip() for x in soup.stripped_strings)
    found=[]
    # A FPF usa blocos do tipo: equipa - equipa / dd mmm yyyy | hh:mm.
    months={"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,"jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}
    pat=re.compile(r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{1,70}?)\s+-\s+([^\n]{1,70}?)\n(\d{1,2})\s+([a-zç]{3})\s+(20\d{2})(?:\s*\|\s*(\d{2}:\d{2}))?",re.I)
    for m in pat.finditer(text):
        day=int(m.group(3)); mon=months.get(m.group(4).lower()[:3])
        if not mon:continue
        date_iso=f"{int(m.group(5)):04d}-{mon:02d}-{day:02d}"
        home=re.sub(r"\s+"," ",m.group(1)).strip();away=re.sub(r"\s+"," ",m.group(2)).strip()
        if "Portugal" not in home and "Portugal" not in away:continue
        found.append({
          "date":date_iso,"start":normalize_time(date_iso,m.group(6)),
          "entity":src["entity"],"sport":src["sport"],"home":home,"away":away,
          "competition":"Seleção Nacional · competição indicada na ficha FPF",
          "location":infer_location(home),"channel":"Transmissão a confirmar",
          "match_url":src["url"],"source_url":src["url"]
        })
    return found

def key(e):
    return (e.get("date"),re.sub(r"\W+","",e.get("home","").lower()),re.sub(r"\W+","",e.get("away","").lower()))

data=load()
existing={key(e):e for e in data.get("events",[])}
checked=[]
for src in SOURCES:
    try:
        html=get(src["url"])
        parsed=parse_zerozero(src,html) if src["kind"]=="zerozero" else parse_fpf(src,html)
        for e in parsed:
            k=key(e)
            if k in existing:
                old=existing[k]
                # Só substitui campos se a nova fonte trouxer informação útil.
                for field,val in e.items():
                    if val and val not in ("Local a confirmar","Transmissão a confirmar","Competição a confirmar"):
                        old[field]=val
            else:
                existing[k]=e
        checked.append({"url":src["url"],"ok":True,"events_found":len(parsed)})
    except Exception as exc:
        checked.append({"url":src["url"],"ok":False,"error":str(exc)[:180]})

events=sorted(existing.values(),key=lambda e:(e.get("date","9999"),e.get("start") or "9999",e.get("entity","")))
out={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "timezone_note":"Horas apresentadas na app no fuso horário local do dispositivo. Horas por confirmar mantêm-se explicitamente assinaladas.",
 "sources":[s["url"] for s in SOURCES],
 "source_checks":checked,
 "events":events
}
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"{len(events)} eventos; fontes verificadas: {len(checked)}")
