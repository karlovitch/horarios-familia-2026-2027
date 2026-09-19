from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import local
from urllib.parse import unquote, urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
DAILY_OUT = ROOT / "daily-info.json"
CALENDAR_OUT = ROOT / "calendar-info.json"
TZ = ZoneInfo("Europe/Lisbon")

START_DATE = date(2026, 1, 1)
END_DATE = date(2027, 12, 31)

UN_URL = "https://unric.org/pt/pesquisa-interativa-de-dias-internacionais/"
COE_URL = "https://eurocid.mne.gov.pt/artigos/efemerides"
LITURGIA_BASE = "https://liturgia.pt/liturgiadiaria/dia.php"
VATICAN_SAINT_BASE = "https://www.vaticannews.va/pt/santo-do-dia"

EUROPEAN_DAYS = {
    "01-28": ["Dia da Proteção de Dados"],
    "05-05": ["Dia da Europa — Conselho da Europa"],
    "05-09": ["Dia da Europa — União Europeia"],
    "09-26": ["Dia Europeu das Línguas"],
    "10-10": ["Dia Europeu contra a Pena de Morte"],
    "10-18": ["Dia Europeu contra o Tráfico de Seres Humanos"],
    "10-25": ["Dia Europeu da Justiça"],
    "11-18": ["Dia Europeu para a Proteção das Crianças contra a Exploração Sexual e o Abuso Sexual"],
}

PORTUGAL_DAYS = {
    "01-01": ["Ano Novo (Feriado Nacional)"],
    "03-27": ["Dia Nacional do Dador de Sangue"],
    "03-31": ["Dia Nacional do Doente com AVC"],
    "04-25": ["Dia da Liberdade (Feriado Nacional)"],
    "05-01": ["Dia do Trabalhador (Feriado Nacional)"],
    "05-06": ["Dia Nacional do Azulejo"],
    "05-10": ["Dia Nacional do Seguro"],
    "06-10": ["Dia de Portugal, de Camões e das Comunidades Portuguesas (Feriado Nacional)"],
    "06-22": ["Dia Nacional da Liberdade Religiosa e do Diálogo Inter-Religioso"],
    "07-22": ["Dia Nacional do Calceteiro e da Calçada Portuguesa"],
    "07-28": ["Dia Nacional da Conservação da Natureza"],
    "08-15": ["Assunção de Nossa Senhora (Feriado Nacional)"],
    "10-01": ["Dia Nacional da Água"],
    "10-05": ["Implantação da República (Feriado Nacional)"],
    "10-18": ["Dia Nacional da Banda Desenhada Portuguesa"],
    "10-30": ["Dia Nacional de Prevenção do Cancro da Mama"],
    "11-01": ["Dia de Todos os Santos (Feriado Nacional)"],
    "11-11": ["Dia Nacional das Raças Autóctones"],
    "11-15": ["Dia Nacional da Língua Gestual Portuguesa"],
    "11-16": ["Dia Nacional do Mar"],
    "11-17": ["Dia Nacional do Não Fumador"],
    "11-24": ["Dia Nacional da Cultura Científica"],
    "12-01": ["Restauração da Independência (Feriado Nacional)"],
    "12-08": ["Imaculada Conceição (Feriado Nacional)"],
    "12-09": ["Dia Nacional da Pessoa com Deficiência"],
    "12-10": ["Dia Nacional dos Direitos Humanos"],
    "12-22": ["Dia Nacional do Técnico Auxiliar de Saúde"],
    "12-25": ["Natal (Feriado Nacional)"],
}

PORTUGAL_MOVABLE_HOLIDAYS = {
    "2026-04-03": ["Sexta-Feira Santa (Feriado Nacional)"],
    "2026-04-05": ["Domingo de Páscoa (Feriado Nacional)"],
    "2026-06-04": ["Corpo de Deus (Feriado Nacional)"],
    "2027-03-26": ["Sexta-Feira Santa (Feriado Nacional)"],
    "2027-03-28": ["Domingo de Páscoa (Feriado Nacional)"],
    "2027-05-27": ["Corpo de Deus (Feriado Nacional)"],
}

LOCAL_DAYS = {
    "05-03": ["Festa das Cruzes — Feriado Municipal de Barcelos"],
}

MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
MONTH_BY_ABBR = {v: k for k, v in MONTHS.items()}
HEADERS = {
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
}

HTTP_HEADERS = {"User-Agent": "HorariosFamilia/3.0 (+GitHub Pages school calendar)"}
_THREAD = local()

def http_session() -> requests.Session:
    session = getattr(_THREAD, "session", None)
    if session is None:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session = requests.Session()
        session.headers.update(HTTP_HEADERS)
        session.mount("https://", HTTPAdapter(max_retries=retry))
        session.mount("http://", HTTPAdapter(max_retries=retry))
        _THREAD.session = session
    return session

def fetch(url: str) -> str:
    r = http_session().get(url, timeout=30)
    r.raise_for_status()
    return r.text

def clean_un_title(value: str) -> str:
    value = re.sub(r"\s*\([^)]*(?:A/RES|Resolution|WHA|WMO|C/|Res\.)[^)]*\)\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip()

def get_un_map() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    try:
        soup = BeautifulSoup(fetch(UN_URL), "html.parser")
        lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
        for i, line in enumerate(lines):
            m = re.fullmatch(r"(\d{2}) ([A-Z][a-z]{2})", line)
            if not m:
                continue
            day = int(m.group(1))
            month = MONTH_BY_ABBR.get(m.group(2))
            if not month:
                continue
            j = i - 1
            while j >= 0:
                candidate = lines[j]
                if candidate in HEADERS or re.fullmatch(r"\d{2} [A-Z][a-z]{2}", candidate):
                    j -= 1
                    continue
                if candidate.lower().startswith((
                    "view calendar", "list of international", "international days and weeks",
                    "download", "resources"
                )):
                    j -= 1
                    continue
                title = clean_un_title(candidate)
                if title:
                    key = f"{month:02d}-{day:02d}"
                    out.setdefault(key, [])
                    if title not in out[key]:
                        out[key].append(title)
                break
    except Exception as exc:
        print("Aviso: não foi possível atualizar a ONU:", exc)
    return out

_VATICAN_SAINT_CACHE: dict[str, list[dict[str, str]]] = {}

def _saint_name_from_slug(url: str) -> str:
    slug = unquote(url.rstrip("/").split("/")[-1])
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip(" .")
    return slug

def _dedupe_hagiographies(items: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url", "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out

def get_vatican_hagiographies(day: date) -> list[dict[str, str]]:
    key = day.strftime("%m-%d")
    if key in _VATICAN_SAINT_CACHE:
        return _VATICAN_SAINT_CACHE[key]

    day_url = f"{VATICAN_SAINT_BASE}/{day.month:02d}/{day.day:02d}.html"
    path_prefix = f"/pt/santo-do-dia/{day.month:02d}/{day.day:02d}/"
    out: list[dict[str, str]] = []
    try:
        html = fetch(day_url)
        soup = BeautifulSoup(html, "html.parser")

        # 1) Estrutura editorial normal: título do santo + ligação "Leia tudo".
        for heading in soup.find_all(["h2", "h3"]):
            name = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip()
            if not name or not re.match(r"^(S\.|SS\.|São|Santa|Santo|Santos|Santas)\b", name, re.I):
                continue

            link = None
            node = heading
            for _ in range(14):
                node = node.find_next()
                if node is None:
                    break
                if getattr(node, "name", None) in ("h2", "h3"):
                    break
                if getattr(node, "name", None) == "a":
                    label = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
                    href = node.get("href")
                    if href and re.search(r"(Leia\s+tudo|Ler\s+mais)", label, re.I):
                        link = urljoin(day_url, href)
                        break

            if link:
                out.append({"name": name, "url": link})

        # 2) Fallback robusto: recolhe diretamente todos os artigos individuais
        #    do dia, mesmo quando o HTML recebido não traz os cartões já renderizados.
        for a in soup.find_all("a", href=True):
            href = urljoin(day_url, a.get("href", ""))
            if path_prefix not in href or href.rstrip("/") == day_url.rstrip("/"):
                continue
            label = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            name = label if re.match(r"^(S\.|SS\.|São|Santa|Santo|Santos|Santas)\b", label, re.I) else _saint_name_from_slug(href)
            out.append({"name": name, "url": href})

        # 3) Último recurso: versão textual renderizada via Jina, útil quando
        #    o portal entrega o conteúdo dos cartões apenas após JavaScript.
        if not out:
            clean = re.sub(r"^https?://", "", day_url)
            rendered = fetch("https://r.jina.ai/http://" + clean)
            current_name = ""
            for line in rendered.splitlines():
                heading = re.match(r"^#{1,4}\s+(S\.|SS\.|São|Santa|Santo|Santos|Santas)\s+(.+)$", line.strip(), re.I)
                if heading:
                    current_name = re.sub(r"^#{1,4}\s+", "", line.strip()).strip()
                    continue
                link = re.search(r"\[(?:Leia\s+tudo|Ler\s+mais)[^\]]*\]\((https?://[^)]+)\)", line, re.I)
                if link:
                    href = link.group(1)
                    out.append({"name": current_name or _saint_name_from_slug(href), "url": href})

    except Exception as exc:
        print(f"Aviso Vatican News {day.isoformat()}: {exc}")

    out = _dedupe_hagiographies(out)
    _VATICAN_SAINT_CACHE[key] = out
    return out

def get_liturgy(day: date) -> dict:
    url = f"{LITURGIA_BASE}?data={day.year}-{day.month}-{day.day}"
    result = {
        "liturgical_day": "",
        "saints": [],
        "gospel": "",
        "liturgy_url": url,
    }
    try:
        html = fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
        text = "\n".join(lines)

        m = re.search(r"\bEv:\s*([^\n]+)", text)
        if m:
            result["gospel"] = m.group(1).strip()

        iso = day.isoformat()
        idx = next((i for i, line in enumerate(lines) if line == iso), None)
        if idx is not None:
            following = lines[idx + 1:]
            if following:
                result["liturgical_day"] = following[0]

            saints = []
            for line in following[1:]:
                if line.startswith((
                    "Verde", "Branco", "Vermelho", "Roxo", "Rosa",
                    "L 1:", "L 2:", "Ev:", "Missa", "Ofício"
                )):
                    break
                if re.search(r"(^|\s)(S\.|São|Santa|Santo|Nossa Senhora|Santos|Santas)", line):
                    if line not in saints:
                        saints.append(line)
            result["saints"] = saints
    except Exception as exc:
        print(f"Aviso liturgia {day.isoformat()}: {exc}")
    return result

def load_calendar() -> dict:
    if CALENDAR_OUT.exists():
        try:
            data = json.loads(CALENDAR_OUT.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("dates"), dict):
                return data
        except Exception:
            pass
    return {"generated_at": None, "dates": {}, "sources": {}}

def build_day(day: date, un_map: dict[str, list[str]]) -> dict:
    mmdd = day.strftime("%m-%d")
    lit = get_liturgy(day)
    hagiographies = get_vatican_hagiographies(day) if lit.get("saints") else []
    return {
        "date": day.isoformat(),
        "un_days": un_map.get(mmdd, []),
        "european_days": EUROPEAN_DAYS.get(mmdd, []),
        "portugal_days": [*PORTUGAL_DAYS.get(mmdd, []), *PORTUGAL_MOVABLE_HOLIDAYS.get(day.isoformat(), [])],
        "local_days": LOCAL_DAYS.get(mmdd, []),
        "saint_hagiographies": hagiographies,
        **lit,
    }

def date_range(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Gerar todo o calendário do ano letivo")
    args = parser.parse_args()

    today = datetime.now(TZ).date()
    un_map = get_un_map()
    calendar = load_calendar()

    if args.all:
        targets = list(date_range(START_DATE, END_DATE))
    else:
        targets = [today]

    total = len(targets)
    if args.all:
        # As páginas de liturgia e hagiografia são independentes por data.
        # Um pequeno pool reduz drasticamente o tempo de regeneração integral
        # sem criar uma carga agressiva sobre as fontes.
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(build_day, day, un_map): day for day in targets}
            for idx, future in enumerate(as_completed(futures), 1):
                day = futures[future]
                try:
                    calendar["dates"][day.isoformat()] = future.result()
                    print(f"[{idx}/{total}] {day.isoformat()} · OK")
                except Exception as exc:
                    print(f"[{idx}/{total}] {day.isoformat()} · erro: {exc}")
    else:
        day = targets[0]
        calendar["dates"][day.isoformat()] = build_day(day, un_map)
        print(f"[1/1] {day.isoformat()} · OK")

    calendar["dates"] = {k: calendar["dates"][k] for k in sorted(calendar["dates"])}
    calendar["generated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    calendar["sources"] = {
        "un": UN_URL,
        "europe": COE_URL,
        "liturgy": "https://liturgia.pt/liturgiadiaria/",
        "saints": VATICAN_SAINT_BASE,
    }
    CALENDAR_OUT.write_text(
        json.dumps(calendar, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    today_info = calendar["dates"].get(today.isoformat())
    if today_info:
        daily = {
            **today_info,
            "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "sources": calendar["sources"],
        }
        DAILY_OUT.write_text(
            json.dumps(daily, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

if __name__ == "__main__":
    main()
