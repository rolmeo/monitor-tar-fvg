import requests
import json
import os
import re
import base64
from datetime import datetime, timedelta, timezone
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# CONFIGURAZIONE
# ============================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "")
STATO_FILE = "tar_stato.json"
DASHBOARD_FILE = "dashboard_data.json"

# ============================================================
# URL
# ============================================================
BASE = "https://www.giustizia-amministrativa.it/web/guest/provvedimenti-tar-friuli-venezia-giulia"
PORTLET = "it_indra_ga_institutional_area_JurisdictionalActivityAdministrativeActsWebPortlet_INSTANCE_pCcjFrTc2Yfg"
URL_HOME = BASE
URL_SEARCH = (
    BASE + "?p_p_id=" + PORTLET
    + "&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
    + "&p_p_resource_id=/administrative-acts/search/results"
    + "&p_p_cacheability=cacheLevelPage"
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


def ora_locale():
    return datetime.now(timezone.utc) + timedelta(hours=1)


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
        print("[INFO] p_auth: " + (p_auth_token or "non trovato"))
        print("[INFO] Cookie: " + str(list(sessione.cookies.keys())))
        return True
    except Exception as e:
        print("[ERRORE] Sessione: " + str(e))
        return False


def get_dates():
    oggi = ora_locale()
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
        url += "&p_auth=" + p_auth_token
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
        if not resp.text.strip():
            print("[WARN] Risposta vuota per " + tipo)
            return []
        data = resp.json()
        risultati = data.get("data", [])
        print("[INFO] " + tipo + ": " + str(len(risultati)) + " provvedimenti trovati")
        return risultati
    except Exception as e:
        print("[ERRORE] " + tipo + ": " + str(e))
        return []


def carica_stato():
    # Prima prova il file locale (cache)
    if os.path.exists(STATO_FILE):
        with open(STATO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback: legge da GitHub (evita messaggi duplicati se la cache è persa)
    if GH_TOKEN and GH_REPO:
        try:
            api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + STATO_FILE
            headers = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github.v3+json"}
            resp = requests.get(api_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                import base64 as b64
                contenuto = b64.b64decode(resp.json()["content"]).decode("utf-8")
                stato = json.loads(contenuto)
                # Salva localmente per questa esecuzione
                with open(STATO_FILE, "w", encoding="utf-8") as f:
                    json.dump(stato, f, ensure_ascii=False, indent=2)
                print("[INFO] tar_stato.json caricato da GitHub")
                return stato
        except Exception as e:
            print("[WARN] Impossibile caricare stato da GitHub: " + str(e))
    return {"collegiale": [], "monocratico": []}


def salva_stato(stato):
    with open(STATO_FILE, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)
    # Pubblica su GitHub così lo stato è persistente anche senza cache
    pubblica_su_github(STATO_FILE)


def invia_telegram(messaggio):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "HTML"}, timeout=10)
        resp.raise_for_status()
        print("[OK] Notifica Telegram inviata")
    except Exception as e:
        print("[ERRORE] Telegram: " + str(e))


def estrai_ids(provvedimenti):
    return [p.get("nrgFascicolo", "") for p in provvedimenti if p.get("nrgFascicolo")]


def controlla_nuovi(nuovi, visti):
    ids_visti = set(visti)
    return [p for p in nuovi if p.get("nrgFascicolo") not in ids_visti]


def formatta_messaggio(tipo, provvedimenti):
    ora = ora_locale().strftime("%d/%m/%Y %H:%M")
    msg = "🔔 TAR Friuli - Nuovi provvedimenti " + tipo + "\n"
    msg += "Rilevati il " + ora + "\n\n"
    for p in provvedimenti:
        nrg = p.get("nrgFascicolo", "N/D")
        sezione = p.get("sezione", "N/D")
        parte = p.get("parte") or "N/D"
        tipo_prov = p.get("tipoProvvedimento") or "N/D"
        data_pub = p.get("dataPubblicazione") or "N/D"
        num_prov = p.get("numProvvedimento") or "N/D"
        msg += "NRG: " + nrg + "\n"
        msg += "Sezione: " + str(sezione) + " | N.Provv: " + str(num_prov) + "\n"
        msg += "Tipo: " + str(tipo_prov) + " | Pubblicato: " + str(data_pub) + "\n"
        msg += "Parte: " + str(parte) + "\n\n"
    return msg


def aggiorna_dashboard(prov_collegiali, prov_monocratici, ha_variazioni=False):
    """Legge dashboard_data.json esistente, aggiorna la sezione provvedimenti e salva."""
    # Carica dati esistenti (potrebbero esserci dati ricorsi scritti da monitor_ricorsi_gh.py)
    dati = {}
    if os.path.exists(DASHBOARD_FILE):
        try:
            with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
                dati = json.load(f)
        except Exception:
            dati = {}

    ora_str = ora_locale().strftime("%d/%m/%Y %H:%M")
    dati["ultimo_aggiornamento"] = ora_str
    dati["ultimo_controllo"] = ora_str
    if ha_variazioni:
        dati["ultima_variazione"] = ora_str
    dati["provvedimenti_collegiali"] = prov_collegiali[:20]
    dati["provvedimenti_monocratici"] = prov_monocratici[:20]

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)

    # Pubblica su GitHub
    pubblica_su_github(DASHBOARD_FILE)


def pubblica_su_github(filepath):
    """Commit del file su GitHub tramite API."""
    if not GH_TOKEN or not GH_REPO:
        print("[WARN] GH_TOKEN o GH_REPO non configurati, skip pubblicazione")
        return
    try:
        with open(filepath, "rb") as f:
            contenuto = base64.b64encode(f.read()).decode("utf-8")

        api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + filepath
        headers = {
            "Authorization": "token " + GH_TOKEN,
            "Accept": "application/vnd.github.v3+json",
        }
        # Recupera SHA attuale (necessario per aggiornare file esistente)
        sha = None
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")

        payload = {
            "message": "Aggiorna " + filepath,
            "content": contenuto,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            print("[OK] " + filepath + " pubblicato su GitHub")
        else:
            print("[ERRORE] GitHub API: " + str(resp.status_code) + " " + resp.text[:200])
    except Exception as e:
        print("[ERRORE] pubblica_su_github: " + str(e))


def main():
    print("[INFO] Avvio controllo provvedimenti: " + ora_locale().strftime("%d/%m/%Y %H:%M"))
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

    # Aggiorna dashboard
    ha_variazioni = bool(nuovi_collegiali or nuovi_monocratici)
    aggiorna_dashboard(prov_collegiali, prov_monocratici, ha_variazioni)

    print("[INFO] Fine. Nuovi: " + str(len(nuovi_collegiali)) + " collegiali, " + str(len(nuovi_monocratici)) + " monocratici")


if __name__ == "__main__":
    main()
