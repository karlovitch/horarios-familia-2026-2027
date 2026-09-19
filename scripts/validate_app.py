from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def read_text(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        fail(f"Ficheiro em falta: {path}")
        return ""
    return p.read_text(encoding="utf-8")


def read_json(path: str):
    raw = read_text(path)
    try:
        return json.loads(raw)
    except Exception as exc:
        fail(f"JSON inválido em {path}: {exc}")
        return {}


index = read_text("index.html")
service_worker = read_text("sw.js")
manifest = read_json("manifest.webmanifest")
calendar = read_json("calendar-info.json")
daily = read_json("daily-info.json")
sports = read_json("sports-info.json")
history = read_json("history-info.json")
daily_script = read_text("scripts/update_daily_info.py")
sports_script = read_text("scripts/update_sports_info.py")

m_app = re.search(r"const APP_BUILD=(\d+);", index)
m_sw = re.search(r"const BUILD=(\d+);", service_worker)
if not m_app:
    fail("APP_BUILD não encontrado em index.html")
if not m_sw:
    fail("BUILD não encontrado em sw.js")
if m_app and m_sw and m_app.group(1) != m_sw.group(1):
    fail(f"Versões desencontradas: index v{m_app.group(1)} / sw v{m_sw.group(1)}")

if manifest.get("start_url") != "./":
    fail("manifest.webmanifest deve usar start_url './' sem versão fixa")
if manifest.get("scope") != "./":
    fail("manifest.webmanifest deve manter scope './'")

manifest_icons = manifest.get("icons") or []
manifest_icon_sources = {str(item.get("src") or "").split("?")[0] for item in manifest_icons if isinstance(item, dict)}
for required_icon in {"icon-192.png", "icon-512.png", "icon-maskable-512.png"}:
    if required_icon not in manifest_icon_sources:
        fail(f"Ícone PWA em falta no manifesto: {required_icon}")
    if not (ROOT / required_icon).exists():
        fail(f"Ficheiro de ícone em falta: {required_icon}")
for required_icon in ("apple-touch-icon.png", "favicon-64.png"):
    if not (ROOT / required_icon).exists():
        fail(f"Ficheiro de ícone em falta: {required_icon}")

required_index_tokens = {
    "ocultação da agenda desportiva": 'id="sportsTabRow" class="sports-tab-row hidden"',
    "regra dinâmica da agenda desportiva": "function updateSportsTabVisibility",
    "relógio pelo início real da parte": "const total=base*60+elapsed",
    "proteção contra 1.ª parte obsoleta": "ev.period===\"1H\"&&total>=55*60",
    "estado visual do intervalo": "⏸️ INTERVALO",
    "dados de áudio direto do Passo-a-Rezar": "passo_audio_url",
    "leitor nativo Passo-a-Rezar": '<audio class="passo-player"',
    "hagiografias": "saint_hagiographies",
    "links de santos": "function saintsHTML",
    "História em carregamento diferido": "function dateNeedsRemoteHistory",
    "fontes históricas autorizadas": "TRUSTED_HISTORY_DOMAINS",
    "preferência por ligações históricas PT-PT": "preferredPortugueseHistoryUrl",
    "ligações específicas de astronomia": "function astronomyReadMoreUrl",
    "fonte astronómica portuguesa": "https://oal.ul.pt/",
    "botões táteis de navegação": "min-width:50px;min-height:50px",
    "setas principais ampliadas": ".today-page-arrow{width:82px;height:66px",
    "seletor de data compacto": ".stats-date-input{width:100%;min-width:0;max-width:132px",
    "frases com normalização linguística": "function normalizeReflectionText",
    "horários prolongados até às 20h00": "START=480,END=1200",
    "linha vermelha do momento atual": "background:#D71920",
    "linha do agora na vista semanal individual": 'class="now-line contained"',
    "linha do agora na vista semanal de conjunto": "overview-week-now-line",
    "rótulo final das 20h visível": "m===END?\' end-label\'",
    "controlos de data sempre centrados": ".stats-controls{display:grid;grid-template-columns:50px minmax(118px,132px) 50px auto;align-items:center;justify-content:center",
    "rótulo Consultar data centrado": ".stats-controls strong{grid-column:1/-1;width:100%;margin:0 0 2px;text-align:center",
    "linha do agora a cada 10 segundos": "UI_REFRESH={nowLine:10000",
    "atualização leve da linha": "setInterval(updateNowLines,UI_REFRESH.nowLine)",
    "estado completo apenas por minuto": "setInterval(refreshScheduleState,UI_REFRESH.scheduleState)",
    "cronómetro desportivo sem rerender total": "function updateSportsLiveClocks",
    "resize agrupado por animation frame": "requestAnimationFrame(()=>",
    "sincronização global do seletor de data": "function renderActiveView(){\n syncStatsControls();",
    "faixa meteorológica disponível": 'data-weather-strip',
    "meteorologia imediatamente sob navegação Hoje": '<div class="today-page-nav" aria-label="Navegação diária">',
    "título Horários Família": '<h1>Horários Família</h1>',
    "meteorologia Open-Meteo": "https://api.open-meteo.com/v1/forecast",
    "classificação visual da nebulosidade": "function weatherSky(cloud)",
    "força do vento Beaufort": "function beaufortFromKmh(kmh)",
    "cache meteorológica de 10 minutos": 'ttl:10*60*1000',
    "texto dos blocos a 1,5x no móvel": ".block{font-size:.72rem;line-height:1;padding:2px 2px}",
    "texto dos blocos a 1,5x no desktop/TV": ".block{font-size:1.08rem;line-height:1.04;padding:4px 4px}",
    "horas laterais a 1,5x no desktop/TV": ".time-label{font-size:1.05rem",
    "cabeçalhos a 1,5x no desktop/TV": ".lane-head{height:52px;padding:8px 3px;font-size:1.29rem",
    "horas laterais a 1,5x no smartphone": ".time-label{left:2px;font-size:.72rem}",
    "cabeçalhos a 1,5x no smartphone": ".lane-head{height:46px;padding:5px 1px;font-size:.885rem",
    "mensagens abaixo do cabeçalho sem sobreposição": ".lane-message{top:58px;font-size:1.02rem",
    "escala vertical ajustada ao texto 1,5x": "timelineHeight=()=>isMobileTimeline()?700:800",
    "geolocalização atual do dispositivo": "navigator.geolocation.getCurrentPosition",
    "fallback de localização pela rede": "https://ipwho.is/",
    "nome da localização por reverse geocoding": "https://api.bigdatacloud.net/data/reverse-geocode-client",
    "timezone meteorológica da localização atual": 'u.searchParams.set("timezone","auto")',
    "cache de localização deduplicada": "locationPromise:null",
    "media query reutilizada": 'const MOBILE_TIMELINE_QUERY=window.matchMedia("(max-width:700px)")',
    "NodeList sem cópia intermédia": "qsa=s=>document.querySelectorAll(s)",
}
if index.count('data-weather-strip') < 4:
    fail("Devem existir faixas meteorológicas nos quatro contextos com seletor de data")

for label, token in required_index_tokens.items():
    if token not in index:
        fail(f"Funcionalidade em falta: {label}")

for forbidden in (
    "},30000);",
    'if(view==="sports"&&sportsEventsFor(statsIso()).some(e=>e.status==="live"))renderSportsAgenda(statsIso());',
    "Fonte de inspiração:",
    "pt.wikipedia.org/w/index.php?search=",
    "google.com/search",
    "bing.com/search",
    'stream=stream||"https://www.dazn.com/pt-PT/home"',
    'stream=stream||"https://tv.fpp.pt/"',
    '<iframe class="passo-player"',
    "passo-player-fallback",
    "www.timeanddate.com",
    "weatherBarcelos",
    "font-size:1.44rem;line-height:1.04",
    "font-size:1.40rem",
    "height:68px;padding:10px 4px;font-size:1.72rem",
    'WEATHER_CONFIG={lat:41.5388',
    "en.wikipedia.org",
):
    if forbidden in index:
        fail(f"Padrão obsoleto/genérico ainda presente em index.html: {forbidden}")

if "def get_passo_metadata(" not in daily_script:
    fail("O atualizador diário deve extrair o áudio direto do Passo-a-Rezar")
if "PASSO_REZAR_BASE" not in daily_script:
    fail("Fonte Passo-a-Rezar não configurada no atualizador diário")

if 'result = {"passo_page_url": page_url}' in daily_script:
    fail("O atualizador diário não deve expor a página externa do Passo-a-Rezar")

if "VERIFIED_FLASHSCORE_MATCH_URLS" not in sports_script:
    fail("O atualizador desportivo deve manter fichas Flashscore verificadas")
if 'if event.get("entity") in {"FC Porto","Real Madrid"}' not in sports_script:
    fail("FC Porto e Real Madrid devem rejeitar fichas Flashscore não verificadas")
if 'hid=best.get("JA");aid=best.get("JB")' not in sports_script:
    fail("As restantes fichas Flashscore devem usar os identificadores codificados do feed")

versioned_refs = {int(x) for x in re.findall(r"[?&]v=(\d+)", index)}
if m_app and versioned_refs and versioned_refs != {int(m_app.group(1))}:
    fail(f"Referências de versão inconsistentes em index.html: {sorted(versioned_refs)}")

if "url.origin!==self.location.origin" not in service_worker:
    fail("O service worker deve ignorar recursos externos")
if "ignoreSearch:true" not in service_worker:
    fail("O fallback offline deve ignorar query strings")
if "canonicalCacheKey" not in service_worker:
    fail("O service worker deve normalizar chaves de cache")

if not isinstance(calendar.get("dates"), dict):
    fail("calendar-info.json não contém o mapa dates")
if not isinstance(history.get("dates"), dict):
    fail("history-info.json não contém o mapa dates")
if not isinstance(sports.get("events"), list):
    fail("sports-info.json não contém a lista events")
if not daily.get("date"):
    fail("daily-info.json não contém date")

for idx, event in enumerate(sports.get("events", [])):
    stream = str(event.get("stream_url") or "").lower().rstrip("/")
    if stream in {
        "https://www.dazn.com/pt-pt/home",
        "https://tv.fpp.pt",
        "https://play.realmadrid.com",
    }:
        fail(f"Evento desportivo {idx} contém uma ligação de transmissão genérica: {stream}")

if errors:
    print("VALIDAÇÃO: FALHOU")
    for error in errors:
        print(f" - {error}")
    sys.exit(1)

print("VALIDAÇÃO: OK")
print(f"Build: v{m_app.group(1) if m_app else '?'}")
print(f"Calendário: {len(calendar.get('dates', {}))} datas")
print(f"História: {len(history.get('dates', {}))} datas")
print(f"Desporto: {len(sports.get('events', []))} eventos")
