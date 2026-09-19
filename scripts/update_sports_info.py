from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
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
    {"entity":"Real Madrid","sport":"Futebol","url":"https://www.laliga.com/en-ES/clubs/real-madrid/next-matches","kind":"realmadrid"},
    {"entity":"Real Madrid","sport":"Futebol","url":"https://www.realmadrid.com/es-ES/futbol/primer-equipo-masculino","kind":"realmadrid_official"},
    {"entity":"Seleção Nacional de Portugal · Hóquei em Patins","sport":"Hóquei em Patins","url":"https://www.zerozero.pt/competicao/mundial-hoquei-patins","kind":"portugal_hockey"},
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

FLASHSCORE_DAILY_CACHE={}
ZEROZERO_PAGE_CACHE={}
FLASHSCORE_HEADERS={
    **HEADERS,
    "Accept":"*/*",
    "Accept-Language":"en-US,en;q=0.8",
    "Referer":"https://www.flashscore.com/",
    "Origin":"https://www.flashscore.com",
    "x-fsign":"SW9D1eZo",
    "Cache-Control":"no-cache",
    "Pragma":"no-cache",
}

def _norm_name(value):
    text=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii").lower()
    replacements={
      "sub-21":"u21","sub 21":"u21","under 21":"u21","pais de gales":"wales","republica checa":"czech republic",
      "dinamarca":"denmark","noruega":"norway","bulgaria":"bulgaria","maritimo":"maritimo",
      "selecao nacional a":"portugal","selecao nacional":"portugal"
    }
    for old,new in replacements.items(): text=text.replace(old,new)
    text=re.sub(r"\b(fc|cf|sc|cd|club|clube|futebol|football)\b"," ",text)
    return re.sub(r"[^a-z0-9]+"," ",text).strip()

def _team_similarity(a,b):
    a=_norm_name(a);b=_norm_name(b)
    if not a or not b:return 0.0
    if a==b:return 1.0
    if a in b or b in a:return .92
    at=set(a.split());bt=set(b.split())
    token=(2*len(at&bt)/(len(at)+len(bt))) if at and bt else 0
    seq=SequenceMatcher(None,a,b).ratio()
    return max(token,seq)

def _parse_flashscore_feed(raw):
    rows=[]
    for item in raw.split("~"):
        if not item.strip():continue
        data={}
        for param in item.split("¬"):
            if not param:continue
            sep="÷" if "÷" in param else ("·" if "·" in param else None)
            if not sep:continue
            key,val=param.split(sep,1)
            if key and key not in data:data[key]=val
        if data.get("AA") and data.get("AE") and data.get("AF"):
            rows.append(data)
    return rows

def _football_candidate_score(event,cand):
    ch=cand.get("AE","");ca=cand.get("AF","")
    eh=event.get("home","");ea=event.get("away","")
    direct=_team_similarity(eh,ch)+_team_similarity(ea,ca)
    reverse=_team_similarity(eh,ca)+_team_similarity(ea,ch)
    score=max(direct,reverse)
    ent=(event.get("entity") or "").lower()
    joined=" "+_norm_name(ch)+" "+_norm_name(ca)+" "
    if "sub-21" in ent or "u21" in ent:
        if "u21" not in joined:score-=.8
    elif "seleção nacional a" in ent or "selecao nacional a" in ent:
        if "u21" in joined:score-=.8
    return score

def flashscore_match_url(event):
    date_iso=event.get("date")
    if not date_iso:return None
    if date_iso not in FLASHSCORE_DAILY_CACHE:
        try:
            target=datetime.fromisoformat(date_iso).date()
            today=datetime.now(timezone.utc).date()
            offset=(target-today).days
            url=f"https://local-global.flashscore.ninja/2/x/feed/f_1_{offset}_3_en_1"
            r=requests.get(url,headers=FLASHSCORE_HEADERS,timeout=25)
            r.raise_for_status()
            FLASHSCORE_DAILY_CACHE[date_iso]=_parse_flashscore_feed(r.text)
        except Exception:
            FLASHSCORE_DAILY_CACHE[date_iso]=[]
    best=None;best_score=0
    for cand in FLASHSCORE_DAILY_CACHE[date_iso]:
        score=_football_candidate_score(event,cand)
        if score>best_score:
            best,best_score=cand,score
    if not best or best_score<1.35:return None
    mid=best.get("AA")
    hs=best.get("WU");aws=best.get("WV")
    hid=best.get("AU") or best.get("JA")
    aid=best.get("AV") or best.get("JB")
    if not all([mid,hs,aws,hid,aid]):return None
    return f"https://www.flashscore.pt/jogo/futebol/{hs}-{hid}/{aws}-{aid}/?mid={mid}"

def _zerozero_links(page_url):
    if not page_url:return []
    if page_url in ZEROZERO_PAGE_CACHE:return ZEROZERO_PAGE_CACHE[page_url]
    links=[]
    try:
        html=get(page_url)
        soup=BeautifulSoup(html,"html.parser")
        for a in soup.find_all("a",href=True):
            href=urljoin(page_url,a["href"])
            if re.search(r"zerozero\.pt/jogo/\d{4}-\d{2}-\d{2}-",href):
                links.append(href.split("?")[0].split("#")[0])
        for href in re.findall(r"""https?://(?:www\.)?zerozero\.pt/jogo/[^\s)\]"']+""",html):
            links.append(href.split("?")[0].split("#")[0])
    except Exception:
        pass
    ZEROZERO_PAGE_CACHE[page_url]=list(dict.fromkeys(links))
    return ZEROZERO_PAGE_CACHE[page_url]

def zerozero_hockey_match_url(event):
    date_iso=event.get("date","")
    pages=[
      event.get("source_url"),event.get("match_url"),
      "https://www.zerozero.pt/equipa/oc-barcelos/agenda",
      "https://www.zerozero.pt/competicao/mundial-hoquei-patins"
    ]
    candidates=[]
    for page in dict.fromkeys(p for p in pages if p):
        candidates.extend(_zerozero_links(page))
    home=_norm_name(event.get("home",""));away=_norm_name(event.get("away",""))
    best=None;best_score=-1
    for url in dict.fromkeys(candidates):
        low=unicodedata.normalize("NFKD",url).encode("ascii","ignore").decode("ascii").lower()
        if date_iso and date_iso not in low:continue
        score=0
        for token in [t for t in home.split() if len(t)>2]:
            if token in low:score+=1
        for token in [t for t in away.split() if len(t)>2]:
            if token in low:score+=1
        if score>best_score:
            best,best_score=url,score
    return best if best_score>=2 else None

def is_direct_match_url(event,url):
    u=(url or "").lower()
    sport=(event.get("sport") or "").lower()
    if "futebol" in sport:return "flashscore.pt/jogo/futebol/" in u and ("?mid=" in u or "&mid=" in u)
    if "hoquei" in sport or "hóquei" in sport:return "zerozero.pt/jogo/" in u
    return bool(url)

def enforce_direct_match_urls(events):
    resolved=0
    for event in events:
        sport=(event.get("sport") or "").lower()
        direct=None
        if "futebol" in sport:
            direct=flashscore_match_url(event)
        elif "hoquei" in sport or "hóquei" in sport:
            direct=zerozero_hockey_match_url(event)
        if direct:
            event["match_url"]=direct;resolved+=1
        elif sport and ("futebol" in sport or "hoquei" in sport or "hóquei" in sport):
            if not is_direct_match_url(event,event.get("match_url")):
                event["match_url"]=None
    return resolved

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
      ("atlético de madrid","Riyadh Air Metropolitano, Madrid, Espanha"),
      ("atletico de madrid","Riyadh Air Metropolitano, Madrid, Espanha"),
      ("real madrid","Estádio Santiago Bernabéu, Madrid, Espanha"),
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

def make_event(src,date_iso,time_text,home,away,comp,text,link=None):
    explicit=next((ch for ch in CHANNELS if ch.lower() in text.lower()),"")
    competition=comp.strip() or "Competição a confirmar"
    channel=explicit or portugal_channel(src["entity"],competition,text)
    stream=portugal_stream(src["entity"],competition,channel)
    out={
      "date":date_iso,"start":normalize_time(date_iso,time_text),
      "entity":src["entity"],"sport":src["sport"],"home":home.strip(),"away":away.strip(),
      "competition":competition,"location":infer_location(home),
      "channel":channel,"match_url":link or src["url"],"source_url":src["url"]
    }
    if stream: out["stream_url"]=stream
    return out

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
        link=None
        for a in row.find_all("a",href=True):
            if "/jogo/" in a["href"] or "/live-ao-minuto/" in a["href"]:
                link=urljoin(src["url"],a["href"]);break
        found.append(make_event(src,date_iso,tm.group(1) if tm else None,home,away,comp,text,link))

    if not found:
        for raw in html.splitlines():
            line=re.sub(r"^[#>*\-\s]+","",raw).strip()
            if not line:continue

            if "|" in line and re.search(r"20\d{2}-\d{2}-\d{2}",line):
                parts=[re.sub(r"Image:\s*","",p).strip() for p in line.split("|")]
                date_i=next((n for n,p in enumerate(parts) if re.fullmatch(r"20\d{2}-\d{2}-\d{2}",p)),None)
                if date_i is not None:
                    date_iso=parts[date_i]
                    time_text=next((p for p in parts[date_i+1:] if re.fullmatch(r"\d{2}:\d{2}|-:-",p)),None)
                    side=next((p for p in parts if p in ("(C)","(F)")),None)
                    comp=next((p for p in parts if any(m.lower() in p.lower() for m in COMP_MARKERS)),"")
                    candidates=[p for p in parts if p and p not in ("h2h","-","(C)","(F)") and not re.fullmatch(r"20\d{2}-\d{2}-\d{2}|\d{2}:\d{2}|-:-|J\d+",p) and p!=comp and not p.lower().startswith("image:")]
                    opponent=""
                    for p in candidates:
                        if p not in (src["entity"],"Gil Vicente","FC Porto","OC Barcelos") and len(p)<70:
                            opponent=p;break
                    if opponent and side:
                        team={"Gil Vicente FC":"Gil Vicente","FC Porto":"FC Porto","Óquei Clube de Barcelos":"OC Barcelos"}.get(src["entity"],src["entity"])
                        home,away=(team,opponent) if side=="(C)" else (opponent,team)
                        found.append(make_event(src,date_iso,time_text,home,away,comp,line))

            dm=re.search(r"\b(\d{2}/\d{2})\b",line)
            tm=re.search(r"\b(\d{2}:\d{2}|-:-)\b",line)
            if dm and " vs " in line:
                date_iso=season_date(dm.group(1))
                after=line[tm.end():].strip() if tm else line[dm.end():].strip()
                positions=[after.lower().find(x.lower()) for x in COMP_MARKERS if after.lower().find(x.lower())>0]
                marker_pos=min(positions or [len(after)])
                match_text=after[:marker_pos].strip()
                comp=after[marker_pos:].strip() if marker_pos<len(after) else ""
                mm=re.search(r"(.+?)\s+vs\s+(.+)",match_text,re.I)
                if mm and date_iso:
                    home=re.sub(r"\s+"," ",mm.group(1)).strip(" -")
                    away=re.sub(r"\s+"," ",mm.group(2)).strip(" -")
                    if home and away and len(home)<80 and len(away)<80:
                        found.append(make_event(src,date_iso,tm.group(1) if tm else None,home,away,comp,line))

    out={}
    for e in found:out[key(e)]=e
    return list(out.values())

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
          "location":infer_location(home),"channel":portugal_channel(src["entity"],"Seleção Nacional",text),
          "stream_url":portugal_stream(src["entity"],"Seleção Nacional"),
          "match_url":src["url"],"source_url":src["url"]
        })
    return found

MADRID_TZ=ZoneInfo("Europe/Madrid")

def iso_madrid_to_utc(date_iso,time_text):
    if not time_text or "--" in time_text:return None
    hh,mm=map(int,re.findall(r"\d+",time_text)[:2])
    y,m,d=map(int,date_iso.split("-"))
    dt=datetime(y,m,d,hh,mm,tzinfo=MADRID_TZ).astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00","Z")

def portugal_channel(entity,competition,text=""):
    low=(competition+" "+text).lower()
    detected=next((ch for ch in CHANNELS if ch.lower() in low),"")
    if detected:return detected
    if entity=="Seleção Nacional A":return "RTP 1 / SPORT TV Portugal"
    if entity=="Seleção Nacional Sub-21":return "Canal 11"
    if entity=="Real Madrid":
        if "laliga" in low or "la liga" in low:return "DAZN Portugal"
        if "champions" in low:return "SPORT TV / DAZN / LiveMode (Portugal; operador do jogo a confirmar)"
    if entity in ("FC Porto","Gil Vicente FC","FC Porto / Gil Vicente FC"):
        if "champions" in low:return "SPORT TV / DAZN / LiveMode (Portugal; operador do jogo a confirmar)"
        if any(x in low for x in ("liga portugal","allianz","taça da liga")):
            return "SPORT TV (canal específico a confirmar)"
    if entity=="Óquei Clube de Barcelos":
        if "champions" in low:return "FPP TV / WSE TV (emissão específica a confirmar)"
        return "FPP TV (emissão específica a confirmar)"
    if "Hóquei em Patins" in entity or "hóquei em patins" in low:
        return "FPP TV (emissão específica a confirmar)"
    return "Transmissão em Portugal a confirmar"

def portugal_stream(entity,competition,channel=""):
    low=(competition+" "+channel).lower()
    if "rtp 1" in low or "rtp1" in low:return "https://www.rtp.pt/play/direto/rtp1"
    if "fpp tv" in low:return "https://tv.fpp.pt/"
    if "dazn" in low:return "https://www.dazn.com/pt-PT/home"
    if "realmadrid tv" in low or "rm play" in low:return "https://play.realmadrid.com/"
    return None

def parse_realmadrid(src,html):
    found=[]
    # A página LaLiga é facilmente legível em tabela, tanto em HTML como no fallback Markdown.
    soup=BeautifulSoup(html,"html.parser")
    rows=[]
    for tr in soup.find_all("tr"):
        vals=[" ".join(x.stripped_strings) for x in tr.find_all(["td","th"])]
        if vals:rows.append(vals)
    if not rows:
        for raw in html.splitlines():
            if "|" not in raw or " VS " not in raw:continue
            vals=[re.sub(r"\s+"," ",p).strip() for p in raw.strip("| ").split("|")]
            rows.append(vals)
    months={}
    for vals in rows:
        joined=" | ".join(vals)
        dm=re.search(r"(\d{2})[./](\d{2})[./](20\d{2})",joined)
        tm=re.search(r"\b(\d{2}:\d{2}|--\s*:\s*--)\b",joined)
        mm=re.search(r"([^|]{1,70}?)\s+VS\s+([^|]{1,70})",joined,re.I)
        if not (dm and mm):continue
        date_iso=f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
        home=re.sub(r"\s+"," ",mm.group(1)).strip()
        away=re.sub(r"\s+"," ",mm.group(2)).strip()
        if "Real Madrid" not in home and "Real Madrid" not in away:continue
        comp=next((v for v in vals if "LALIGA" in v.upper() or "CHAMPIONS" in v.upper()),"Competição a confirmar")
        found.append({
          "date":date_iso,"start":iso_madrid_to_utc(date_iso,tm.group(1) if tm else None),
          "entity":"Real Madrid","sport":"Futebol","home":home,"away":away,
          "competition":comp,"location":infer_location(home),
          "channel":portugal_channel("Real Madrid",comp,joined),
          "stream_url":portugal_stream("Real Madrid",comp,portugal_channel("Real Madrid",comp,joined)),
          "match_url":src["url"],"source_url":src["url"]
        })
    return found

def parse_realmadrid_official(src,html):
    soup=BeautifulSoup(html,"html.parser")
    lines=[re.sub(r"\s+"," ",x).strip() for x in soup.stripped_strings if re.sub(r"\s+"," ",x).strip()]
    if len(lines)<20:
        # fallback Markdown/Jina: remove sintaxe de links/imagens e bullets
        lines=[]
        for raw in html.splitlines():
            x=re.sub(r"!?\[[^\]]*\]\([^)]*\)","",raw)
            x=re.sub(r"^#+\s*","",x)
            x=re.sub(r"^[*\-]\s*","",x)
            x=re.sub(r"\s+"," ",x).strip()
            if x:lines.append(x)
    months={"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sept":9,"sep":9,"oct":10,"nov":11,"dic":12}
    found=[]
    exclude={"Fútbol · Primer Equipo","Primer equipo","La Liga","Champions League","Amistoso","Más","Calendario","Suscribirse"}
    for i,line in enumerate(lines):
        if line!="Fútbol · Primer Equipo":continue
        # nomes das equipas imediatamente antes do marcador
        prev=[]
        j=i-1
        while j>=0 and len(prev)<2 and i-j<=10:
            x=lines[j].strip()
            if x not in exclude and not x.lower().startswith(("image","jornada","trofeo")) and len(x)<70:
                if x not in prev:prev.append(x)
            j-=1
        if len(prev)<2:continue
        away_or_second=prev[0]; home_or_first=prev[1]
        home,away=home_or_first,away_or_second
        if "Real Madrid" not in home and "Real Madrid" not in away:continue
        block=lines[i+1:i+18]
        comp=next((x for x in block if x in ("La Liga","Champions League","Amistoso") or "Copa" in x or "Supercopa" in x),"Competição a confirmar")
        date_iso=None;time_text=None;venue="Local a confirmar";date_pos=None
        for n,x in enumerate(block):
            m=re.search(r"(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sept|sep|oct|nov|dic)(?:[^0-9]+(\d{2}:\d{2}))?",x,re.I)
            if m:
                day=int(m.group(1));mon=months[m.group(2).lower()];year=2026 if mon>=7 else 2027
                date_iso=f"{year:04d}-{mon:02d}-{day:02d}";time_text=m.group(3);date_pos=n;break
        if not date_iso:continue
        if date_pos is not None:
            for x in block[date_pos+1:date_pos+5]:
                if x and not x.lower().startswith(("rueda de prensa","orange tv","movistar","dazn","realmadrid tv","más")):
                    venue=x;break
        if re.search(r"metropolitano",venue,re.I):
            venue="Riyadh Air Metropolitano, Madrid, Espanha"
        elif re.search(r"santiago bernab[eé]u",venue,re.I) and "Madrid" not in venue:
            venue=venue+", Madrid, Espanha"
        channel=portugal_channel("Real Madrid",comp," ".join(block))
        stream=None
        if comp=="La Liga":stream="https://www.dazn.com/pt-PT/home"
        elif comp=="Amistoso" and any("Realmadrid TV" in x for x in block):
            channel="Realmadrid TV / RM Play";stream="https://play.realmadrid.com/"
        found.append({
          "date":date_iso,"start":iso_madrid_to_utc(date_iso,time_text),
          "entity":"Real Madrid","sport":"Futebol","home":home,"away":away,
          "competition":comp,"location":venue,"channel":channel,
          **({"stream_url":stream} if stream else {}),
          "match_url":src["url"],"source_url":src["url"]
        })
    return found

def f1_fallback():
    source="https://www.formula1.com/en/racing/2026"
    weekends=[
      ("GP do Azerbaijão","Baku City Circuit, Baku, Azerbaijão","https://www.formula1.com/en/racing/2026/azerbaijan",[
        ("2026-09-24","08:30","Treino Livre 1"),("2026-09-24","12:00","Treino Livre 2"),("2026-09-25","08:30","Treino Livre 3"),("2026-09-25","12:00","Qualificação"),("2026-09-26","11:00","Corrida")]),
      ("GP do Barém na Malásia","Sepang International Circuit, Sepang, Malásia","https://www.formula1.com/en/racing/2026/bahrain",[
        ("2026-10-02","04:30","Treino Livre 1"),("2026-10-02","08:00","Treino Livre 2"),("2026-10-03","04:30","Treino Livre 3"),("2026-10-03","08:00","Qualificação"),("2026-10-04","07:00","Corrida")]),
      ("GP de Singapura","Marina Bay Street Circuit, Singapura","https://www.formula1.com/en/racing/2026/singapore",[
        ("2026-10-09","08:30","Treino Livre 1"),("2026-10-09","12:30","Qualificação Sprint"),("2026-10-10","09:00","Sprint"),("2026-10-10","13:00","Qualificação"),("2026-10-11","12:00","Corrida")]),
      ("GP dos Estados Unidos","Circuit of the Americas, Austin, Estados Unidos","https://www.formula1.com/en/racing/2026/united-states",[
        ("2026-10-23","17:30","Treino Livre 1"),("2026-10-23","21:00","Treino Livre 2"),("2026-10-24","17:30","Treino Livre 3"),("2026-10-24","21:00","Qualificação"),("2026-10-25","20:00","Corrida")]),
      ("GP da Cidade do México","Autódromo Hermanos Rodríguez, Cidade do México, México","https://www.formula1.com/en/racing/2026/mexico",[
        ("2026-10-30","18:30","Treino Livre 1"),("2026-10-30","22:00","Treino Livre 2"),("2026-10-31","17:30","Treino Livre 3"),("2026-10-31","21:00","Qualificação"),("2026-11-01","20:00","Corrida")]),
      ("GP de São Paulo","Autódromo José Carlos Pace, São Paulo, Brasil","https://www.formula1.com/en/racing/2026/brazil",[
        ("2026-11-06","15:30","Treino Livre 1"),("2026-11-06","19:00","Treino Livre 2"),("2026-11-07","14:30","Treino Livre 3"),("2026-11-07","18:00","Qualificação"),("2026-11-08","17:00","Corrida")]),
      ("GP de Las Vegas","Las Vegas Strip Street Circuit, Las Vegas, Estados Unidos","https://www.formula1.com/en/racing/2026/las-vegas",[
        ("2026-11-20","00:30","Treino Livre 1"),("2026-11-20","04:00","Treino Livre 2"),("2026-11-21","00:30","Treino Livre 3"),("2026-11-21","04:00","Qualificação"),("2026-11-22","04:00","Corrida")]),
      ("GP do Qatar","Lusail International Circuit, Lusail, Qatar","https://www.formula1.com/en/racing/2026/qatar",[
        ("2026-11-27","13:30","Treino Livre 1"),("2026-11-27","17:00","Treino Livre 2"),("2026-11-28","14:30","Treino Livre 3"),("2026-11-28","18:00","Qualificação"),("2026-11-29","16:00","Corrida")]),
      ("GP de Abu Dhabi","Yas Marina Circuit, Abu Dhabi, Emirados Árabes Unidos","https://www.formula1.com/en/racing/2026/united-arab-emirates",[
        ("2026-12-04","09:30","Treino Livre 1"),("2026-12-04","13:00","Treino Livre 2"),("2026-12-05","10:30","Treino Livre 3"),("2026-12-05","14:00","Qualificação"),("2026-12-06","13:00","Corrida")]),
    ]
    out=[]
    for gp,location,url,sessions in weekends:
        for date_iso,time_text,label in sessions:
            out.append({
              "date":date_iso,"start":f"{date_iso}T{time_text}:00Z",
              "entity":"Formula 1","sport":"Automobilismo","title":f"{label} · {gp}",
              "competition":"Campeonato do Mundo de Fórmula 1 da FIA 2026",
              "location":location,"channel":"DAZN","stream_url":"https://www.dazn.com/pt-PT/home",
              "match_url":url,"source_url":url
            })
    return out

def f1_events():
    url="https://api.jolpi.ca/ergast/f1/2026.json"
    source="https://www.formula1.com/en/racing/2026"
    country_pt={"Azerbaijan":"Azerbaijão","Malaysia":"Malásia","Singapore":"Singapura","USA":"Estados Unidos",
                "Mexico":"México","Brazil":"Brasil","Qatar":"Qatar","UAE":"Emirados Árabes Unidos",
                "Spain":"Espanha","Italy":"Itália","Netherlands":"Países Baixos","UK":"Reino Unido",
                "Belgium":"Bélgica","Austria":"Áustria","Hungary":"Hungria","Canada":"Canadá","China":"China",
                "Japan":"Japão","Australia":"Austrália","Monaco":"Mónaco"}
    session_names={"FirstPractice":"Treino Livre 1","SecondPractice":"Treino Livre 2","ThirdPractice":"Treino Livre 3",
                   "SprintQualifying":"Qualificação Sprint","Sprint":"Sprint","Qualifying":"Qualificação"}
    out=[]
    data=requests.get(url,headers=HEADERS,timeout=30).json()
    races=data.get("MRData",{}).get("RaceTable",{}).get("Races",[])
    for race in races:
        loc=race.get("Circuit",{}).get("Location",{})
        locality=loc.get("locality","")
        country=country_pt.get(loc.get("country",""),loc.get("country",""))
        place=", ".join(x for x in [race.get("Circuit",{}).get("circuitName",""),locality,country] if x)
        gp=re.sub(r" Grand Prix$","",race.get("raceName","Grande Prémio"))
        if gp=="Azerbaijan":gp="Azerbaijão"
        elif gp=="United States":gp="Estados Unidos"
        elif gp=="Mexico City":gp="Cidade do México"
        elif gp=="Brazilian":gp="São Paulo"
        elif gp=="Abu Dhabi":gp="Abu Dhabi"
        gp_label="GP de "+gp
        if "Bahrain" in gp:gp_label="GP do Barém na Malásia"
        for field,label in session_names.items():
            obj=race.get(field)
            if not obj:continue
            start=f"{obj.get('date')}T{obj.get('time','00:00:00Z')}"
            out.append({
              "date":obj.get("date"),"start":start,"entity":"Formula 1","sport":"Automobilismo",
              "title":f"{label} · {gp_label}","competition":"Campeonato do Mundo de Fórmula 1 da FIA 2026",
              "location":place,"channel":"DAZN","stream_url":"https://www.dazn.com/pt-PT/home",
              "match_url":source,"source_url":source
            })
        out.append({
          "date":race.get("date"),"start":f"{race.get('date')}T{race.get('time','00:00:00Z')}",
          "entity":"Formula 1","sport":"Automobilismo","title":f"Corrida · {gp_label}",
          "competition":"Campeonato do Mundo de Fórmula 1 da FIA 2026","location":place,
          "channel":"DAZN","stream_url":"https://www.dazn.com/pt-PT/home",
          "match_url":source,"source_url":source
        })
    return out

def portugal_hockey_seed():
    source="https://www.zerozero.pt/competicao/mundial-hoquei-patins"
    return [
      {"date":"2026-09-19","start":"2026-09-19T14:10:00Z","entity":"Seleção Nacional de Portugal · Hóquei em Patins","sport":"Hóquei em Patins","home":"Portugal","away":"França","competition":"GoldenCat 2026 · Seleção AA Masculina","location":"Cerdanyola del Vallès, Catalunha, Espanha","channel":"FPP TV","stream_url":"https://tv.fpp.pt/","match_url":"https://www.zerozero.pt/jogo/2026-09-19-portugal-franca/12609727","source_url":"https://fpp.pt/selecoes-nacionais-em-preparacao-para-os-world-skate-games-no-goldencat-com-transmissao-na-fpp-tv/"},
      {"date":"2026-10-13","start":"2026-10-12T23:00:00Z","entity":"Seleção Nacional de Portugal · Hóquei em Patins","sport":"Hóquei em Patins","home":"Suíça","away":"Portugal","competition":"Campeonato do Mundo de Hóquei em Patins 2026 · Fase de grupos","location":"Assunção, Paraguai","channel":"Transmissão em Portugal a confirmar","match_url":source,"source_url":source},
      {"date":"2026-10-13","start":"2026-10-13T20:45:00Z","entity":"Seleção Nacional de Portugal · Hóquei em Patins","sport":"Hóquei em Patins","home":"Portugal","away":"Espanha","competition":"Campeonato do Mundo de Hóquei em Patins 2026 · Fase de grupos","location":"Assunção, Paraguai","channel":"Transmissão em Portugal a confirmar","match_url":source,"source_url":source},
      {"date":"2026-10-14","start":"2026-10-14T20:45:00Z","entity":"Seleção Nacional de Portugal · Hóquei em Patins","sport":"Hóquei em Patins","home":"Itália","away":"Portugal","competition":"Campeonato do Mundo de Hóquei em Patins 2026 · Fase de grupos","location":"Assunção, Paraguai","channel":"Transmissão em Portugal a confirmar","match_url":source,"source_url":source},
    ]

def key(e):
    if e.get("title"):
        return (
            e.get("date"),
            re.sub(r"\W+","",e.get("entity","").lower()),
            re.sub(r"\W+","",e.get("title","").lower()),
        )
    return (
        e.get("date"),
        re.sub(r"\W+","",e.get("home","").lower()),
        re.sub(r"\W+","",e.get("away","").lower()),
    )

data=load()
existing={key(e):e for e in data.get("events",[])}
checked=[]
for src in SOURCES:
    try:
        html=get(src["url"])
        if src["kind"]=="zerozero": parsed=parse_zerozero(src,html)
        elif src["kind"]=="fpf": parsed=parse_fpf(src,html)
        elif src["kind"]=="realmadrid": parsed=parse_realmadrid(src,html)
        elif src["kind"]=="realmadrid_official": parsed=parse_realmadrid_official(src,html)
        elif src["kind"]=="portugal_hockey": parsed=[]
        else: parsed=[]
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

existing={k:v for k,v in existing.items() if v.get("entity")!="Formula 1"}
try:
    generated_f1=f1_events()
    for e in generated_f1: existing[key(e)]=e
    checked.append({"url":"https://api.jolpi.ca/ergast/f1/2026.json","ok":True,"events_found":len(generated_f1)})
except Exception as exc:
    generated_f1=f1_fallback()
    for e in generated_f1: existing[key(e)]=e
    checked.append({"url":"https://api.jolpi.ca/ergast/f1/2026.json","ok":False,"fallback":"Formula1.com","events_found":len(generated_f1),"error":str(exc)[:180]})
for e in portugal_hockey_seed(): existing[key(e)]=e
events=list(existing.values())
direct_resolved=enforce_direct_match_urls(events)
events=sorted(events,key=lambda e:(e.get("date","9999"),e.get("start") or "9999",e.get("entity","")))
out={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "timezone_note":"Horas apresentadas na app no fuso horário local do dispositivo. Horas por confirmar mantêm-se explicitamente assinaladas.",
 "sources":[s["url"] for s in SOURCES]+["https://api.jolpi.ca/ergast/f1/2026.json","https://www.formula1.com/en/racing/2026","https://tv.fpp.pt/"],
 "source_checks":checked,
 "events":events
}
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"{len(events)} eventos; fontes verificadas: {len(checked)}; fichas diretas resolvidas: {direct_resolved}")
