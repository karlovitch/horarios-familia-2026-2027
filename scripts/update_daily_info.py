from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "daily-info.json"
TZ = ZoneInfo("Europe/Lisbon")

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

HEADERS = {
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
}

def fetch(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "HorariosFamilia/1.0"})
    r.raise_for_status()
    return r.text

def clean_un_title(value: str) -> str:
    value = re.sub(r"\s*\([^)]*(?:A/RES|Resolution|WHA|WMO|C/|Res\.)[^)]*\)\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip()

def get_un_days(today) -> list[str]:
    target = f"{today.day:02d} {MONTHS[today.month]}"
    try:
        soup = BeautifulSoup(fetch(UN_URL), "html.parser")
        lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
        found = []
        for i, line in enumerate(lines):
            if line != target:
                continue
            j = i - 1
            while j >= 0:
                candidate = lines[j]
                if candidate in HEADERS or re.fullmatch(r"\d{2} [A-Z][a-z]{2}", candidate):
                    j -= 1
                    continue
                if candidate.lower().startswith(("view calendar", "list of international", "international days and weeks")):
                    j -= 1
                    continue
                title = clean_un_title(candidate)
                if title and title not in found:
                    found.append(title)
                break
        return found
    except Exception:
        return []

def get_liturgy(today):
    url = f"{LITURGIA_BASE}?data={today.year}-{today.month}-{today.day}"
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

        iso = today.isoformat()
        idx = next((i for i, line in enumerate(lines) if line == iso), None)
        if idx is not None:
            following = lines[idx + 1:]
            if following:
                result["liturgical_day"] = following[0]

            saints = []
            for line in following[1:]:
                if line.startswith(("Verde", "Branco", "Vermelho", "Roxo", "L 1:", "L 2:", "Ev:", "Missa")):
                    break
                if re.search(r"(^|\s)(S\.|São|Santa|Santo|Nossa Senhora)", line):
                    if line not in saints:
                        saints.append(line)
            result["saints"] = saints
    except Exception:
        pass
    return result

def main():
    today = datetime.now(TZ).date()
    mmdd = today.strftime("%m-%d")
    lit = get_liturgy(today)

    data = {
        "date": today.isoformat(),
        "un_days": get_un_days(today),
        "european_days": EUROPEAN_DAYS.get(mmdd, []),
        "portugal_days": PORTUGAL_DAYS.get(mmdd, []),
        "local_days": LOCAL_DAYS.get(mmdd, []),
        **lit,
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "sources": {
            "un": UN_URL,
            "europe": COE_URL,
            "liturgy": "https://liturgia.pt/liturgiadiaria/",
        },
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
