import requests
import json
import os
import re
from datetime import datetime, timedelta
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# Carica variabili dal file .env (C:\TAR\.env)
# ============================================================
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ============================================================
# CONFIGURAZIONE
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATO_FILE = "C:\\TAR\\tar_stato.json"

# ============================================================
# URL
# ============================================================
BASE = "https://www.giustizia-amministrativa.it/web/guest/provvedimenti-tar-friuli-venezia-giulia"
PORTLET = "it_indra_ga_institutional_area_JurisdictionalActivityAdministrativeActsWebPortlet_INSTANCE_pCcjFrTc2Yfg"
URL_HOME = BASE
URL_SEARCH = (
    f"{BASE}?p_p_id={PORTLET}"
    "&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
    "&p_p_resource_id=/administrative-acts/search/results"
    "&p_p_cacheability=cacheLevelPage"
)

sessione = requests.Session()
sessione.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.7",
})
p_auth_token = ""

COLUMNS = [
    {"data": "nrgFascicolo",     "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "sezione",          "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "parte",            "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "tipoUdienza",      "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "dataUdienza",      "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "numProvvedimento", "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "dataPubblicazione","name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "tipoProvvedimento","name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "relatore",         "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "presidente",       "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    {"data": "esito",            "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
]

def inizializza_sessione():
    global p_auth_token
    try:
        resp = sessione.get(URL_HOME, timeout=30, verify=False)
        resp.raise_for_status()
        html = resp.text
        p_auth_token = ""
        for pattern in [
            r'"p_auth"\s*:\s*"([^"]+)"',
            r"'p_auth'\s*:\s*'([^']+)'",
            r'Liferay\.authToken\s*=\s*["\']([^"\']+)["\']',
            r'p_auth["\s]*[:=]["\s]*([A-Za-z0-9_-]{6,20})',
        ]:
            match = re.search(pattern, html)
            if match:
                p_auth_token = match.group(1)
                break
        print(f"[INFO] p_auth: {p_auth_token or 'non trovato'}")
        print(f"[INFO] Cookie: {list(sessione.cookies.keys())}")
        return True
    except Exception as e:
        print(f"[ERRORE] Sessione: {e}")
        return False


def get_dates():
    oggi = datetime.now()
    ieri = oggi - timedelta(days=1)
    return ieri.strftime("%Y-%m-%d"), oggi.strftime("%Y-%m-%d")


def fetch_provvedimenti(tipo):
    date_from, date_to = get_dates()

    additional_info = json.dumps({
        "schema": "TAR_TRIESTE",
        "type": tipo,
        "year": "",
        "number": "",
        "hearingDateFrom": None,
        "hearingDateTo": None,
        "publishDateFrom": date_from,
        "publishDateTo": date_to,
        "hearingType": None,
        "nrg": None,
        "section": "",
        "provisionSpecification": "",
        "president": "",
        "draftingJudge": "",
        "subjectMatter": None,
        "page": None,
        "size": None,
        "orderBy": None,
        "orderStrategy": None,
        "queryString": None
    })

    payload = {
        "draw": 1,
        "columns": COLUMNS,
        "order": [{"column": 6, "dir": "desc"}, {"column": 5, "dir": "desc"}],
        "start": 0,
        "length": 100,
        "search": {"value": "", "regex": False},
        "additionalInfo": additional_info,
    }

    url = URL_SEARCH
    if p_auth_token:
        url += f"&p_auth={p_auth_token}"

    headers_post = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-PJAX": "true",
        "Referer": URL_HOME,
        "Origin": "https://www.giustizia-amministrativa.it",
    }

    try:
        resp = sessione.post(url, headers=headers_post, json=payload, timeout=30, verify=False)
        resp.raise_for_status()
        raw = resp.text[:300]
        print(f"[DEBUG] {tipo} status={resp.status_code} risposta: {repr(raw)}")
        if not resp.text.strip():
            print(f"[WARN] Risposta vuota per {tipo}")
            return []
        data = resp.json()
        risultati = data.get("data", [])
        print(f"[INFO] {tipo}: {len(risultati)} provvedimenti trovati")
        return risultati
    except Exception as e:
        print(f"[ERRORE] {tipo}: {e}")
        return []


def carica_stato():
    if os.path.exists(STATO_FILE):
        with open(STATO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"collegiale": [], "monocratico": []}


def salva_stato(stato):
    os.makedirs(os.path.dirname(STATO_FILE), exist_ok=True)
    with open(STATO_FILE, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)


def invia_telegram(messaggio):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "HTML"}, timeout=10)
        resp.raise_for_status()
        print("[OK] Notifica Telegram inviata")
    except Exception as e:
        print(f"[ERRORE] Telegram: {e}")


def estrai_ids(provvedimenti):
    return [p.get("nrgFascicolo", "") for p in provvedimenti if p.get("nrgFascicolo")]


def controlla_nuovi(nuovi, visti):
    ids_visti = set(visti)
    return [p for p in nuovi if p.get("nrgFascicolo") not in ids_visti]


def formatta_messaggio(tipo, provvedimenti):
    ora = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg = f"🔔 TAR Friuli - Nuovi provvedimenti {tipo}\n"
    msg += f"Rilevati il {ora}\n\n"
    for p in provvedimenti:
        nrg = p.get("nrgFascicolo", "N/D")
        sezione = p.get("sezione", "N/D")
        parte = p.get("parte", "N/D")
        tipo_prov = p.get("tipoProvvedimento", "N/D")
        data_pub = p.get("dataPubblicazione", "N/D")
        num_prov = p.get("numProvvedimento", "N/D")
        msg += f"NRG: {nrg}\n"
        msg += f"Sezione: {sezione} | N.Provv: {num_prov}\n"
        msg += f"Tipo: {tipo_prov} | Pubblicato: {data_pub}\n"
        msg += f"Parte: {parte}\n\n"
    return msg


def main():

    print(f"[INFO] Avvio controllo: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    stato = carica_stato()

    if not inizializza_sessione():
        print("[ERRORE] Impossibile connettersi al sito")
        return

    prov_collegiali = fetch_provvedimenti("COLLEGIALE")
    nuovi_collegiali = controlla_nuovi(prov_collegiali, stato["collegiale"])
    if nuovi_collegiali:
        invia_telegram(formatta_messaggio("COLLEGIALI", nuovi_collegiali))

    prov_monocratici = fetch_provvedimenti("MONOCRATICO")
    nuovi_monocratici = controlla_nuovi(prov_monocratici, stato["monocratico"])
    if nuovi_monocratici:
        invia_telegram(formatta_messaggio("MONOCRATICI", nuovi_monocratici))

    if prov_collegiali:
        stato["collegiale"] = estrai_ids(prov_collegiali)
    if prov_monocratici:
        stato["monocratico"] = estrai_ids(prov_monocratici)

    salva_stato(stato)
    print(f"[INFO] Fine. Nuovi: {len(nuovi_collegiali)} collegiali, {len(nuovi_monocratici)} monocratici")


if __name__ == "__main__":
    main()