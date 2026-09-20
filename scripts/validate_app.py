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
version_meta = read_json("version.json")
calendar = read_json("calendar-info.json")
daily = read_json("daily-info.json")
sports = read_json("sports-info.json")
sports_js = read_text("sports-info.js")
sports_script = read_text("scripts/update_sports_info.py")
history = read_json("history-info.json")
daily_script = read_text("scripts/update_daily_info.py")
tv_activity = read_text("android-tv/app/src/main/java/pt/horariosfamilia/tv/MainActivity.java")
tv_manifest = read_text("android-tv/app/src/main/AndroidManifest.xml")
tv_installer = read_text("scripts/Instalar_Horarios_Familia_Android_TV.ps1")
sports_script = read_text("scripts/update_sports_info.py")

m_app = re.search(r"const APP_BUILD=(\d+);", index)
m_sw = re.search(r"const BUILD=(\d+);", service_worker)
if not m_app:
    fail("APP_BUILD não encontrado em index.html")
if not m_sw:
    fail("BUILD não encontrado em sw.js")
if m_app and m_sw and m_app.group(1) != m_sw.group(1):
    fail(f"Versões desencontradas: index v{m_app.group(1)} / sw v{m_sw.group(1)}")
if m_app and int(version_meta.get("build", -1)) != int(m_app.group(1)):
    fail(f"version.json desencontrado: {version_meta.get('build')} / index v{m_app.group(1)}")

if re.search(r'<span[^>]*style="opacity:\\.65;font-size:\\.72rem">· v\\d+</span>', index):
    fail("O número de versão visual não pode ficar hard-coded no cabeçalho")

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
    "regra de visibilidade condicional da agenda desportiva": "function updateSportsTabVisibility(iso=statsIso()){",
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
    "horários das 07h30 às 20h30": "START=450,END=1230",
    "rótulos horários com minutos reais": "minToTime(m)",
    "versão visual ligada à build real": 'id="appVersion"',
    "número visual atualizado por APP_BUILD": 'document.getElementById("appVersion").textContent="· v"+APP_BUILD;',
    "linha vermelha do momento atual": "background:#D71920",
    "linha do agora na vista semanal individual": 'class="now-line contained"',
    "linha Desporto condicional por data": 'row.classList.toggle("hidden",!hasEvents)',
    "linha Família condicional por data": 'if(!events.length){el.classList.add("hidden");el.innerHTML="";return}',
    "linha do agora na vista semanal de conjunto": "overview-week-now-line",
    "rótulo final das 20h30 visível": "m===END?\' end-label\'",
    "controlos de data sempre centrados": ".stats-controls{display:grid;grid-template-columns:50px minmax(118px,132px) 50px auto;align-items:center;justify-content:center",
    "rótulo Consultar data centrado": ".stats-controls strong{grid-column:1/-1;width:100%;margin:0 0 2px;text-align:center",
    "linha do agora a cada 10 segundos": "UI_REFRESH={nowLine:10000",
    "atualização leve da linha": "setInterval(updateNowLines,UI_REFRESH.nowLine)",
    "estado completo apenas por minuto": "setInterval(refreshScheduleState,UI_REFRESH.scheduleState)",
    "cronómetro desportivo sem rerender total": "function updateSportsLiveClocks",
    "resize apenas ao mudar de breakpoint": 'MOBILE_TIMELINE_QUERY.addEventListener("change",handleTimelineBreakpointChange)',
    "sincronização global do seletor de data": "function renderActiveView(){\n const iso=statsIso();\n syncStatsControls();",
    "faixa meteorológica disponível": 'data-weather-strip',
    "meteorologia global entre Desporto e Família": 'id="globalWeatherStrip"',
    "título Horários Família": '<h1>Horários Família</h1>',
    "meteorologia Open-Meteo": "https://api.open-meteo.com/v1/forecast",
    "classificação visual dia/noite e nebulosidade": "function weatherSky(cloud,isDay=true)",
    "estado dia/noite Open-Meteo": 'wind_speed_10m,is_day"',
    "nascer e pôr do sol Open-Meteo": "wind_speed_10m_max,sunrise,sunset",
    "fase dia/noite pela hora solar local": "function dayPhaseFromForecast(data,nowMs=Date.now())",
    "sincronização cromática da fase": "function syncDayPhaseFromWeather(data)",
    "transformação noturna de qualquer paleta": "function nightPalette(colors)",
    "transformação noturna das micro-paletas pessoais": "function adaptPersonPalettesForNight()",
    "estado cromático noturno no DOM": 'root.dataset.dayphase=CURRENT_DAY_PHASE',
    "reavaliação automática dia/noite": 'setInterval(()=>{if(WEATHER_STATE.data)syncDayPhaseFromWeather(WEATHER_STATE.data)},60000)',
    "CSS noturno global": 'html[data-dayphase="night"] body',
    "força do vento Beaufort": "function beaufortFromKmh(kmh)",
    "cache meteorológica de 10 minutos": 'ttl:10*60*1000',
    "texto dos blocos a 1,5x no móvel": ".block{font-size:.72rem;line-height:1;padding:2px 2px}",
    "texto dos blocos a 1,5x no desktop/TV": ".block{font-size:1.08rem;line-height:1.04;padding:4px 4px}",
    "horas laterais a 1,5x no desktop/TV": ".time-label{font-size:1.05rem",
    "cabeçalhos a 1,5x no desktop/TV": ".lane-head{height:52px;padding:8px 3px;font-size:1.29rem",
    "horas laterais a 1,5x no smartphone": ".time-label{left:2px;font-size:.72rem}",
    "cabeçalhos a 1,5x no smartphone": ".lane-head{height:46px;padding:5px 1px;font-size:.885rem",
    "mensagens abaixo do cabeçalho sem sobreposição": ".lane-message{top:58px;font-size:1.02rem",
    "escala vertical adaptativa universal": "timelineHeight=()=>adaptiveScheduleHeight()",
    "geolocalização atual do dispositivo": "navigator.geolocation.watchPosition",
    "fallback de localização pela rede": "https://ipwho.is/",
    "nome da localização por reverse geocoding": "https://api.bigdatacloud.net/data/reverse-geocode-client",
    "timezone meteorológica da localização atual": 'u.searchParams.set("timezone","auto")',
    "cache de localização deduplicada": "locationPromise:null",
    "media query reutilizada": 'const MOBILE_TIMELINE_QUERY=window.matchMedia("(max-width:700px)")',
    "NodeList sem cópia intermédia": "qsa=s=>document.querySelectorAll(s)",
    "modo Android TV explícito": 'TV_PARAMS.get("tv")==="1"',
    "calendário próprio Android TV": 'id="tvDateDialog"',
    "botão de data focável Android TV": 'data-tv-date-open="1"',
    "navegação horizontal por grupos": "function tvHorizontalTarget(current,key)",
    "navegação vertical semanal no calendário TV": "ArrowDown:7",
    "paleta Verão exata": 'summer:{name:"Verão",colors:["#6EC6F0","#2F8FCE","#F2D16B","#F49B3F"]}',
    "micro-paletas pessoais específicas de Verão": 'if(themeName==="Verão"){',
    "paleta Natal v107": 'christmas:{name:"Natal",colors:["#1F5A47","#B33A3A","#D8B45A","#FFF8E7"]}',
    "paleta Ano Novo v107": 'newyear:{name:"Ano Novo",colors:["#18243A","#D7B56D","#C9CED6","#F7F8FA"]}',
    "paleta Carnaval v107": 'carnival:{name:"Carnaval",colors:["#D94FA3","#3D7BFF","#FFD447","#3CCBC0"]}',
    "paleta Tríduo Pascal v107": 'triduum:{name:"Tríduo Pascal",colors:["#7048A8","#FFFFFF","#C9A35A","#B8CEE8"]}',
    "paleta Equinócio Primavera v107": 'springEquinox:{name:"Equinócio da Primavera",colors:["#8FD19E","#F2DC75","#A6D8F0","#F2A18A"]}',
    "paleta Solstício Verão v107": 'summerSolstice:{name:"Solstício de Verão",colors:["#50B9EC","#247CC0","#FFD447","#F59B3D"]}',
    "paleta Equinócio Outono v107": 'autumnEquinox:{name:"Equinócio do Outono",colors:["#C96F3D","#D2A24A","#80915A","#7A3A42"]}',
    "paleta Solstício Inverno v107": 'winterSolstice:{name:"Solstício de Inverno",colors:["#20314C","#B9D4E8","#CBD0D6","#F6F7F8"]}',
    "datas de Carnaval": 'const CARNIVAL_DATES=new Set(["2026-02-17","2027-02-09"])',
    "ativação temática do Carnaval": 'if(CARNIVAL_DATES.has(iso))return FESTIVE_THEMES.carnival;',
    "micro-paletas especiais por pessoa": 'const SPECIAL_PERSON_ROLES={',
    "micro-paleta especial antes da sazonal": 'const special=specialPersonMicroPalette(profile,colors,themeName);if(special)return special;',
    "perfil Leonor 9": 'Leonor:{age:9,style:"sweet"',
    "perfil Margarida 15": 'Margarida:{age:15,style:"indie"',
    "perfil Sandrinha 48": 'Sandra:{age:48,style:"serene"',
    "perfil Carlos 44": 'Carlos:{age:44,style:"editorial"',
    "base sazonal explícita": "function themeContextForIso(iso)",
    "sobreposição temática diária": "document.body.dataset.specialTheme=ctx.special?ctx.special.name",
    "confettis persistidos por evento": 'familyConfetti:"+iso+":"+e.label',

    "perfil TV persistente na URL": 'TV_PARAMS.get("profile")||"auto"',
    "navegação D-pad": "function moveTvFocus(key,root=document)",
    "foco TV visível": 'outline:5px solid #FFD54A',
    "altura TV adaptativa": "function tvTimelineHeight()",


    "check de versão leve": 'fetch("version.json?__version_check="+stamp',
    "atualização automática universal a cada minuto": "const BUILD_POLL_MS=60*1000",
    "fallback oficial do podcast": 'class="passo-fallback"',
    "tratamento de erro do áudio": 'function bindPassoPlayerFallback()',

    "mensagem de ativação do service worker": 'type==="BUILD_ACTIVATED"',
    "snapshot JS da agenda": 'sports-info.js?v=',
    "merge resiliente de agenda": "function mergeSportsInfo(...sources)",
    "ambiente adaptativo universal": "function applyAdaptiveEnvironment()",
    "primeira seleção de data no estilo v114": "today-page-nav top-date-nav",
    "cabeçalho Hoje após primeira seleção": 'class="screen-head today-screen-head"',
    "título Hoje dinâmico": 'id="todayHeading"',
    "dia da semana quando não é hoje": 'isToday?"Hoje":weekday.charAt(0).toUpperCase()+weekday.slice(1)',
    "subtítulo sem duplicar dia da semana": 'qs("#todayDay").textContent=isToday?pretty:fullDate',

    "geolocalização de alta precisão sem cache": "maximumAge:0",
    "melhor fix GPS por accuracy": "candidate.accuracy<=WEATHER_CONFIG.goodAccuracy",
    "cache de localização v98": 'weatherCurrentLocationV98',
    "meteorologia móvel sem scroll horizontal": ".weather-source{flex:1 0 100%;justify-content:center}",

    "altura adaptativa de horários": "function adaptiveScheduleHeight()",

    "cronómetro desportivo sob demanda": "function syncSportsClockTimer()",
    "data canónica dos eventos desportivos": "function sportsEventDate(e)",
    "event.date prioritário": 'if(/^20\\d{2}-\\d{2}-\\d{2}$/.test(explicit))return explicit;',
    "separador Desporto condicional": 'row.classList.toggle("hidden",!hasEvents)',
    "eventos terminados não são filtrados": "// Não filtra pelo estado: scheduled, live, halftime e finished permanecem visíveis.",
    "resultado final pendente explicitado": 'ev.status==="awaiting_final"',

    "refresh ao abrir Desporto": 'loadSportsInfo({force:true}).then(()=>{if(view==="sports")renderActiveView()})',


    "cronómetro suspenso fora do desporto": 'if(view!=="sports")return;',
    "fila de foreground": "if(foregroundRefreshRunning){",
    "refresh de dados forçado ao regressar": "loadDailyInfo({force}),",
    "refresh desportivo forçado ao regressar": "loadSportsInfo({force}),",
    "histórico apenas quando necessário": 'const historyTask=(view==="today"&&dateNeedsRemoteHistory(statsIso()))?loadHistoryInfo({force}):Promise.resolve(HISTORY_INFO);',
    "refresh no arranque consolidado": 'window.addEventListener("load",initializeApp,{once:true});',
    "refresh no pageshow": 'window.addEventListener("pageshow",()=>{',
    "refresh no focus": 'window.addEventListener("focus",()=>{',
    "cache desportiva hidratada uma vez": "let SPORTS_CACHE_HYDRATED=false;",
    "polling desportivo apenas na vista": 'if(view!=="sports")return;',
}
if index.count('data-weather-strip aria-live="polite"') != 1:
    fail("Deve existir uma única faixa meteorológica global, comum a todos os separadores")

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
    'fetch("index.html?__version_check="',
    "setInterval(updateSportsLiveClocks",
    "let resizeFrame=0;",
    "font-size:1.44rem;line-height:1.04",
    "font-size:1.40rem",
    "height:68px;padding:10px 4px;font-size:1.72rem",
    'WEATHER_CONFIG={lat:41.5388',
    "en.wikipedia.org",
):
    if forbidden in index:
        fail(f"Padrão obsoleto/genérico ainda presente em index.html: {forbidden}")

if "HorariosFamiliaTV/1.0" not in tv_activity or "?tv=1&shell=1&profile=" not in tv_activity:
    fail("Invólucro Android TV não está configurado para abrir o modo TV")
if "LEANBACK_LAUNCHER" not in tv_manifest or "android.hardware.touchscreen" not in tv_manifest:
    fail("Manifesto Android TV incompleto")
if "adb -s" not in tv_installer or "HorariosFamilia-TV.apk" not in tv_installer:
    fail("Instalador PowerShell Android TV incompleto")

if "def _probe_audio_url(url: str) -> bool:" not in daily_script:
    fail("O podcast não valida o ficheiro de áudio antes de o publicar")
if '"passo_page_url": page_url' not in daily_script:
    fail("O podcast não guarda a ligação oficial de fallback")
if "def get_passo_metadata(" not in daily_script:
    fail("O atualizador diário deve extrair o áudio direto do Passo-a-Rezar")
if "PASSO_REZAR_BASE" not in daily_script:
    fail("Fonte Passo-a-Rezar não configurada no atualizador diário")

if 'result = {"passo_page_url": page_url}' in daily_script:
    fail("O atualizador diário não deve expor a página externa do Passo-a-Rezar")

if "VERIFIED_FOOTBALL_MATCH_URLS" not in sports_script:
    fail("O atualizador desportivo deve manter um mapa de fichas de futebol verificadas")
if "def flashscore_match_candidate(event):" not in sports_script or "def flashscore_match_id(event):" not in sports_script:
    fail("O atualizador desportivo deve separar a identificação live do URL público")
if "def verified_football_match_url(event):" not in sports_script:
    fail("Falta resolução de ficha pública verificada para futebol")
if "def zerozero_football_match_url(event):" not in sports_script:
    fail("Falta fallback de ficha ZeroZero verificada para futebol")
if 'event["flashscore_mid"]=mid' not in sports_script:
    fail("O ID Flashscore live deve ficar separado da ficha pública")
if 'return f"https://www.flashscore.pt/jogo/futebol/' in sports_script:
    fail("Não é permitido fabricar URLs públicos Flashscore a partir de IDs internos")
if '"sofascore.com/" in low' not in sports_script:
    fail("As fichas verificadas de futebol devem aceitar SofaScore")

if "function adaptiveOrientationClass(w,h)" not in index:
    fail("Falta deteção explícita da orientação do ecrã")
if "root.dataset.uiOrientation=adaptiveOrientationClass(w,h);" not in index:
    fail("A orientação não está exposta ao CSS adaptativo")
if 'window.addEventListener("orientationchange"' not in index:
    fail("A aplicação não reage explicitamente à rotação do ecrã")
if "@media (orientation:landscape) and (max-height:900px)" not in index:
    fail("Falta o perfil CSS específico para modo paisagem")
if "html:not(.tv-mode) .main-tabs{grid-template-columns:repeat(6,minmax(0,1fr))" not in index:
    fail("Em paisagem, as seis abas principais devem caber numa só linha")
if "html:not(.tv-mode) .day-tabs{display:grid;grid-template-columns:repeat(6,minmax(0,1fr))" not in index:
    fail("Em paisagem, os seis seletores de dia devem caber numa só linha")
if "html:not(.tv-mode) .countdown-panel{grid-template-columns:repeat(2,minmax(0,1fr))" not in index:
    fail("O painel de contagens deve aproveitar duas colunas em paisagem")
if "html:not(.tv-mode) .sports-grid{grid-template-columns:repeat(2,minmax(0,1fr))" not in index:
    fail("A agenda desportiva deve aproveitar duas colunas em paisagem")

if "function currentClockLabel(){" not in index:
    fail("Falta formatação HH:MM na linha da hora atual")
if 'clock.className="now-axis-clock"' not in index:
    fail("A hora atual deve ser criada dentro da primeira coluna horária")
if ".now-axis-clock{" not in index:
    fail("Falta estilo da etiqueta HH:MM na primeira coluna")
if "font-size:.76rem!important" not in index:
    fail("A hora atual na primeira coluna deve ter tamanho reforçado")
if ".overview-week-now-line.first:after" not in index or "right:calc(100% + 9px)" not in index or "font-size:.72rem!important" not in index:
    fail("A vista semanal deve deslocar e ampliar a hora atual na primeira coluna")

if 'cache:"no-cache"' not in index or '"Pragma":"no-cache"' not in index:
    fail("Os JSON devem ser revalidados sem forçar transferências no-store")
if '{ts:Date.now(),build:APP_BUILD}' in index or 'history-info.json",{ts:Date.now()}' in index:
    fail("URLs de dados não devem usar timestamps que inutilizam a revalidação HTTP")
if index.count('window.addEventListener("load"') != 1:
    fail("Deve existir apenas um listener de load consolidado")
if 'Promise.allSettled([loadDailyInfo(),loadSportsInfo()]).then(()=>renderActiveView());' in index:
    fail("O arranque não deve duplicar a primeira carga de dados")
if 'if(!SPORTS_CACHE_HYDRATED)' not in index:
    fail("A cache local desportiva deve ser hidratada apenas uma vez por página")

if "grid-template-columns:minmax(0,.84fr) minmax(0,1.16fr) minmax(0,.90fr) minmax(0,1.20fr) minmax(0,1.20fr) minmax(0,.90fr)!important" not in index:
    fail("Os seis separadores principais devem permanecer numa única linha com larguras adaptadas")
if index.count("top-date-nav") < 4 or index.count("bottom-date-controls") < 4:
    fail("Cada separador principal deve ter navegação superior e seleção inferior de data")
if "function pastShadeTimelineHtml(){" not in index or "function pastShadeOverviewHtml(){" not in index:
    fail("Falta indicação visual do período do dia já passado")
if 'data-past-shade="timeline"' not in index or 'data-past-shade="overview"' not in index:
    fail("A zona temporal passada não está ligada às grelhas de horário")

main_sections = [
    ("overview", 'id="timeline"'),
    ("today", 'id="todayTimeline"'),
    ("sports", 'id="sportsPanel"'),
    ("person", 'id="personTimeline"'),
]
for pos, (section_id, schedule_token) in enumerate(main_sections):
    start = index.find(f'<section id="{section_id}"')
    if start < 0:
        fail(f"Separador em falta: {section_id}")
        continue
    if pos + 1 < len(main_sections):
        end = index.find(f'<section id="{main_sections[pos + 1][0]}"', start + 1)
    else:
        end = index.find("</main>", start)
    chunk = index[start:end if end >= 0 else len(index)]
    top = chunk.find("top-date-nav")
    schedule = chunk.find(schedule_token)
    bottom = chunk.find("bottom-date-controls")
    if min(top, schedule, bottom) < 0 or not (top < schedule < bottom):
        fail(f"Ordem de layout inválida no separador {section_id}: data → horário → data")

if index.count('data-top-date') < 4 or index.count('data-top-shift="-1"') < 4 or index.count('data-top-shift="1"') < 4:
    fail("A navegação superior ao estilo v114 deve existir nos quatro separadores")
if 'function topDateLabel(iso){' not in index or 'qsa("[data-top-date]")' not in index:
    fail("As datas superiores devem ser sincronizadas entre separadores")
for token in [
    '.main-tab[data-view="today"]{font-size:.96rem!important}',
    '.main-tab[data-view="overview"]{font-size:.88rem!important}',
    '.main-tab[data-view="Carlos"]{font-size:.93rem!important}',
    '.main-tab[data-view="Sandra"]{font-size:.86rem!important}',
    '.main-tab[data-view="Margarida"]{font-size:.84rem!important}',
    '.main-tab[data-view="Leonor"]{font-size:.92rem!important}',
]:
    if token not in index:
        fail("Falta dimensionamento individual dos separadores")

if "function connectionBearerLabel(){" not in index:
    fail("Falta identificação da ligação Wi‑Fi/dados móveis")
if 'source:"gps-wifi-mobile"' not in index or 'method:"GPS/Wi‑Fi/dados móveis"' not in index:
    fail("A geolocalização principal deve usar a localização fundida GPS/Wi‑Fi/dados móveis")
if 'source:"network-ip"' not in index or 'method:bearer+" (rede/IP)"' not in index:
    fail("Falta fallback de localização por rede/IP")
if "const networkPromise=ipCurrentPosition().catch(()=>null);" not in index:
    fail("O fallback por rede deve ser preparado em paralelo com a localização do dispositivo")
if 'if(permission!=="denied")' not in index or "if(!loc)loc=await networkPromise;" not in index:
    fail("A resolução de localização deve cair para a rede quando GPS/localização do dispositivo falha")
if "function isDeviceLocation(loc)" not in index:
    fail("Falta distinção entre localização precisa e localização aproximada por rede")

if "VERIFIED_FOOTBALL_LIVE_FEEDS" not in sports_script or "def espn_football_live_info(event):" not in sports_script:
    fail("Falta fallback live alternativo ao Flashscore")
if "info=merge_football_live_sources(primary,sofa,espn_generic,espn)" not in sports_script:
    fail("As fontes live devem ser fundidas por fase de jogo")
if "def football_start_fallback_info(event):" not in sports_script:
    fail("Falta fallback temporal para jogos que já começaram")
if 'const updated=Number(ev.status_updated_at||0)' not in index or 'const extra=updated>0?Math.max(0,now-updated):0;' not in index:
    fail("O relógio live deve avançar continuamente entre atualizações")
if "Math.min(359,now-updated)" in index:
    fail("O relógio live não pode congelar após 359 segundos")

if "SOFASCORE_DAILY_CACHE={}" not in sports_script or "def sofascore_football_live_info(event):" not in sports_script:
    fail("Falta fallback genérico SofaScore para jogos de futebol")
if "ESPN_DAILY_CACHE={}" not in sports_script or "def espn_scoreboard_live_info(event):" not in sports_script:
    fail("Falta fallback genérico ESPN por data e equipas")
if 'scheduled-events/{date_iso}' not in sports_script:
    fail("O fallback genérico deve resolver jogos por data")
if "merge_football_live_sources(primary,sofa,espn_generic,espn)" not in sports_script:
    fail("A cadeia live deve combinar Flashscore, SofaScore e ESPN por prioridade de fase")
if 'const NATIVE_SHELL_HINT=new URLSearchParams(location.search).get("shell")==="1";' not in index:
    fail("A WebView nativa deve ter foreground independente de visibilityState")
if "foregroundRefreshPending=true;" not in index or 'queueMicrotask(()=>refreshWhenVisible("queued",true));' not in index:
    fail("Eventos de foreground ocorridos durante um refresh não podem ser perdidos")
if "const sportsClockInterval=setInterval(()=>sportsClockPulse(Date.now()),250);" not in index:
    fail("O relógio desportivo deve ter pulso persistente de alta frequência")
if "sportsData:60000" not in index:
    fail("A agenda desportiva deve procurar snapshots novos de minuto a minuto enquanto está aberta")
if 'window.addEventListener("appforeground",()=>{' not in index:
    fail("Falta evento explícito de regresso ao primeiro plano")
if 'ts:force?Date.now():undefined' not in index:
    fail("As atualizações forçadas devem contornar caches intermédias")

if "def football_phase_rank(info):" not in sports_script or "def merge_football_live_sources(*sources):" not in sports_script:
    fail("Falta seleção da fase mais avançada entre fontes live")
if 'if status=="halftime" or period=="HT":return 50' not in sports_script:
    fail("O intervalo deve ter prioridade sobre uma fonte ainda em 1H")
if 'if period=="2H":return 70' not in sports_script:
    fail("A 2.ª parte deve ter prioridade sobre uma fonte ainda em intervalo")
if 'dynamic_mid=flashscore_match_id(event)' not in sports_script or 'mid=dynamic_mid or event.get("flashscore_mid")' not in sports_script:
    fail("O ID live Flashscore deve ser re-resolvido por data/equipas antes de usar o ID guardado")
if 'ev.period==="1H"&&total>=55*60' not in index:
    fail("A 1.ª parte deve impedir a exibição de minutos impossíveis quando a fonte fica presa")
if 'return "Intervalo";' not in index:
    fail("Falta fallback visual de Intervalo")
if index.count('id="globalFamilyBanner"') != 1:
    fail("Deve existir uma única linha global Família")
sports_pos = index.find('id="sportsTabRow"')
weather_pos = index.find('id="globalWeatherStrip"')
family_pos = index.find('id="globalFamilyBanner"')
if min(sports_pos, weather_pos, family_pos) < 0 or not (sports_pos < weather_pos < family_pos):
    fail("A ordem global deve ser Desporto → Meteorologia → Família")
if 'const events=familyEventsFor(iso);' not in index or 'if(!events.length){el.classList.add("hidden");el.innerHTML="";return}' not in index:
    fail("A linha Família deve aparecer apenas nas datas com aniversário/evento familiar")

versioned_refs = {int(x) for x in re.findall(r"[?&]v=(\d+)", index)}
if m_app and versioned_refs and versioned_refs != {int(m_app.group(1))}:
    fail(f"Referências de versão inconsistentes em index.html: {sorted(versioned_refs)}")

if "url.origin!==self.location.origin" not in service_worker:
    fail("O service worker deve ignorar recursos externos")
if "ignoreSearch:true" not in service_worker:
    fail("O fallback offline deve ignorar query strings")
if "canonicalCacheKey" not in service_worker:
    fail("O service worker deve normalizar chaves de cache")
if "'/version.json'" not in service_worker:
    fail("O service worker deve tratar version.json como recurso de atualização")
if "fetch(req,{cache:'no-cache'})" not in service_worker:
    fail("Recursos network-first devem usar revalidação HTTP")
if "if(cached)return cached;" not in service_worker:
    fail("Recursos estáticos versionados devem usar cache-first sem pedido de rede redundante")


if not isinstance(calendar.get("dates"), dict):
    fail("calendar-info.json não contém o mapa dates")
if not isinstance(history.get("dates"), dict):
    fail("history-info.json não contém o mapa dates")
if "def _zerozero_structured_score(html,event):" not in sports_script:
    fail("O parser ZeroZero de hóquei não pesquisa o resultado de forma robusta")
if '"result_source_url"]=url' not in sports_script:
    fail("O resultado de hóquei obtido da ficha direta não guarda a fonte")
if 'urls=["https://www.hoqueipatins.pt/"]' in sports_script:
    fail("O hóquei não pode inferir resultados a partir de uma homepage agregadora genérica")
if "def hockey_result_priority(event):" not in sports_script or "def apply_hockey_result(event,info):" not in sports_script:
    fail("Falta prioridade de fontes para resultados de hóquei")
if "def hockey_fallback_status(event):" not in sports_script:
    fail("O atualizador desportivo não tem fallback multi-fonte para hóquei")
if "def merge_hockey_seed(existing_event,seed_event):" not in sports_script:
    fail("O seed de hóquei pode voltar a apagar resultados já confirmados")
if '"status":"awaiting_final"' not in index and 'ev.status==="awaiting_final"' not in index:
    fail("A interface não apresenta resultados finais ainda por confirmar")
if "window.__SPORTS_INFO__=" not in sports_js:
    fail("sports-info.js não contém o snapshot da agenda")
if 'OUT_JS.write_text("window.__SPORTS_INFO__="' not in sports_script:
    fail("O gerador desportivo não atualiza sports-info.js")
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
# v107: paletas festivas/astronómicas e micro-paletas pessoais auditadas acima.
# v108: fichas públicas de futebol desacopladas dos IDs live; URLs construídos são proibidos.
