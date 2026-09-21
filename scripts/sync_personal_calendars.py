#!/usr/bin/env python3
import base64
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from icalendar import Calendar
import recurring_ical_events

TZ = ZoneInfo("Europe/Lisbon")
START = datetime(2026, 1, 1, tzinfo=TZ)
END = datetime(2028, 1, 1, tzinfo=TZ)
OUTPUT = Path("personal-calendar.enc.json")
ITERATIONS = 210000

SPORT_RE = re.compile(
    r"(?:\bfutebol\b|\bfootball\b|\bsoccer\b|\bfutsal\b|"
    r"\bh[oó]quei\b|\bhockey\b|\bf[oó]rmula\s*1\b|\bformula\s*1\b|\bf1\b|"
    r"\bgrand\s+prix\b|\bmotogp\b|\bmotociclismo\b|\bautomobilismo\b|"
    r"\bbasquetebol\b|\bbasketball\b|\bnba\b|\bandebol\b|\bhandball\b|"
    r"\bvoleibol\b|\bvolleyball\b|\bt[eé]nis\b|\btennis\b|\bpadel\b|"
    r"\bciclismo\b|\bcycling\b|\brugby\b|\batletismo\b|\bmaratona\b|"
    r"\btriatlo\b|\btriathlon\b|\bnata[cç][aã]o\b|\bswimming\b|"
    r"\bgolfe\b|\bgolf\b|\buefa\b|\bfifa\b|\bchampions\s+league\b|"
    r"\beuropa\s+league\b|\bconference\s+league\b|\bpremier\s+league\b|"
    r"\bla\s+liga\b|\bprimeira\s+liga\b|\bworld\s+cup\b|\bmundial\b|"
    r"\breal\s+madrid\b|\bgil\s+vicente\b|\bbenfica\b|\bsporting\b|"
    r"\bfc\s+porto\b|\bsc\s+braga\b|\bbarcelona\b|\bsofascore\b|"
    r"\bzerozero\b|\bflashscore\b)",
    re.IGNORECASE,
)

def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta o secret obrigatório {name}")
    return value

def text_value(component, name):
    value = component.get(name)
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return ""

def is_sport_event(component):
    text = " ".join(
        [
            text_value(component, "summary"),
            text_value(component, "description"),
            text_value(component, "location"),
            text_value(component, "categories"),
        ]
    )
    return bool(SPORT_RE.search(text))

def localize_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=TZ)
        return value.astimezone(TZ)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=TZ)
    raise TypeError(f"Data iCal não suportada: {value!r}")

def component_times(component):
    raw_start = component.decoded("dtstart")
    raw_end = component.decoded("dtend") if component.get("dtend") else None
    all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
    start = localize_value(raw_start)
    if raw_end is None:
        end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    else:
        end = localize_value(raw_end)
    if end <= start:
        end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    return start, end, all_day

def day_rows(owner, component):
    if str(component.get("status", "")).upper() == "CANCELLED":
        return []
    if is_sport_event(component):
        return []

    title = text_value(component, "summary").strip() or "(Sem título)"
    location = text_value(component, "location").strip()
    start, end, all_day = component_times(component)

    first = max(start.date(), START.date())
    last_exclusive = min(end.date() + (timedelta(days=1) if not all_day and end.time() != time.min else timedelta()), END.date())
    if all_day:
        last_exclusive = min(end.date(), END.date())
    if last_exclusive <= first:
        last_exclusive = first + timedelta(days=1)

    rows = []
    d = first
    while d < last_exclusive:
        if all_day:
            label = "Todo o dia"
            sort_key = "00:00"
        elif start.date() == end.date():
            label = f"{start:%H:%M}–{end:%H:%M}"
            sort_key = f"{start:%H:%M}"
        elif d == start.date():
            label = f"{start:%H:%M}–…"
            sort_key = f"{start:%H:%M}"
        elif d == end.date():
            label = f"…–{end:%H:%M}"
            sort_key = "00:00"
        else:
            label = "Em curso"
            sort_key = "00:00"
        rows.append(
            {
                "date": d.isoformat(),
                "owner": owner,
                "title": title,
                "time": label,
                "sort": sort_key,
                "location": location,
                "all_day": all_day,
            }
        )
        d += timedelta(days=1)
    return rows

def fetch_calendar(url, owner):
    response = requests.get(url, timeout=30, headers={"User-Agent": "HorariosFamiliaCalendarSync/1.0"})
    response.raise_for_status()
    cal = Calendar.from_ical(response.content)
    occurrences = recurring_ical_events.of(cal).between(START, END)
    rows = []
    for component in occurrences:
        try:
            rows.extend(day_rows(owner, component))
        except Exception as exc:
            uid = text_value(component, "uid")
            print(f"Aviso: evento ignorado ({owner}, {uid}): {exc}", file=sys.stderr)
    return rows

def canonical_payload(rows):
    days = {}
    for row in rows:
        day = row.pop("date")
        days.setdefault(day, []).append(row)
    for items in days.values():
        items.sort(key=lambda x: (x["sort"], x["owner"], x["title"].casefold()))
        for item in items:
            item.pop("sort", None)
    return {
        "schema": 1,
        "timezone": "Europe/Lisbon",
        "days": dict(sorted(days.items())),
    }

def b64(data):
    return base64.b64encode(data).decode("ascii")

def derive_key(passphrase, salt):
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, ITERATIONS, dklen=32)

def decrypt_existing(passphrase):
    if not OUTPUT.exists():
        return None
    try:
        envelope = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if not envelope.get("configured"):
            return None
        salt = base64.b64decode(envelope["kdf"]["salt"])
        nonce = base64.b64decode(envelope["cipher"]["nonce"])
        data = base64.b64decode(envelope["cipher"]["data"])
        key = derive_key(passphrase, salt)
        plain = AESGCM(key).decrypt(nonce, data, b"horarios-familia-calendar-v1")
        return json.loads(plain.decode("utf-8"))
    except Exception:
        return None

def encrypt_payload(payload, passphrase):
    plain = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plain, b"horarios-familia-calendar-v1")
    return {
        "version": 1,
        "configured": True,
        "kdf": {
            "name": "PBKDF2",
            "hash": "SHA-256",
            "iterations": ITERATIONS,
            "salt": b64(salt),
        },
        "cipher": {
            "name": "AES-GCM",
            "nonce": b64(nonce),
            "data": b64(ciphertext),
        },
    }

def main():
    carlos_url = required_env("CARLOS_CALENDAR_ICS_URL")
    sandrinha_url = required_env("SANDRINHA_CALENDAR_ICS_URL")
    passphrase = required_env("PERSONAL_CALENDAR_PASSPHRASE")

    rows = fetch_calendar(carlos_url, "Carlos")
    rows.extend(fetch_calendar(sandrinha_url, "Sandrinha"))
    payload = canonical_payload(rows)

    previous = decrypt_existing(passphrase)
    if previous == payload:
        print("Sem alterações nas agendas pessoais.")
        return

    envelope = encrypt_payload(payload, passphrase)
    OUTPUT.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Agendas atualizadas: {sum(len(v) for v in payload['days'].values())} ocorrências não desportivas.")

if __name__ == "__main__":
    main()
