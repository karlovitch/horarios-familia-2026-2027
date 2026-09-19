from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DAILY_OUT = ROOT / "daily-info.json"
CALENDAR_OUT = ROOT / "calendar-info.json"
TZ = ZoneInfo("Europe/Lisbon")

START_DATE = date(2026, 9, 14)
END_DATE = date(2027, 6, 30)

UN_URL = "https://www.un.org/en/observances/list-days-weeks"
COE_URL = "https://www.coe.int/en/web/portal/international-and-european-days"
LITURGIA_BASE = "https://liturgia.pt/liturgiadiaria/dia.php"

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
    "04-25": ["Dia da Liberdade"],
    "05-06": ["Dia Nacional do Azulejo"],
    "05-10": ["Dia Nacional do Seguro"],
    "05-25": ["Dia Nacional dos Jardins"],
    "06-10": ["Dia de Portugal, de Camões e das Comunidades Portuguesas"],
    "06-22": ["Dia Nacional da Liberdade Religiosa e do Diálogo Inter-Religioso"],
    "10-05": ["Implantação da República"],
    "11-11": ["Dia Nacional das Raças Autóctones"],
    "12-01": ["Restauração da Independência"],
    "12-10": ["Dia Nacional dos Direitos Humanos"],
    "12-22": ["Dia Nacional do Técnico Auxiliar de Saúde"],
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

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HorariosFamilia/2.0 (+GitHub Pages school calendar)"})

def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=30)
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
    return {
        "date": day.isoformat(),
        "un_days": un_map.get(mmdd, []),
        "european_days": EUROPEAN_DAYS.get(mmdd, []),
        "portugal_days": PORTUGAL_DAYS.get(mmdd, []),
        "local_days": LOCAL_DAYS.get(mmdd, []),
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
    for idx, day in enumerate(targets, 1):
        print(f"[{idx}/{total}] {day.isoformat()}")
        calendar["dates"][day.isoformat()] = build_day(day, un_map)
        if args.all:
            time.sleep(0.04)

    calendar["generated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    calendar["sources"] = {
        "un": UN_URL,
        "europe": COE_URL,
        "liturgy": "https://liturgia.pt/liturgiadiaria/",
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
