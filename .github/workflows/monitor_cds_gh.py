import requests
import json
import os
import re
import base64
from datetime import datetime, timezone, timedelta
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# CONFIGURAZIONE
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GH_TOKEN  = os.environ.get("GH_TOKEN", "")
GH_REPO   = os.environ.get("GH_REPO", "")
STATO_FILE     = "cds_ricorsi_stato.json"
DASHBOARD_FILE = "dashboard_data.json"

# Ricorsi CdS da monitorare (anno, numero)
RICORSI_DA_MONITORARE = [
    (2025, 1750),
    (2026, 1897),
    (2026, 2039),
    (2026, 2696),
]

# ============================================================
# URL e portlet CdS
# ============================================================
PORTLET  = "it_indra_ga_institutional_area_JurisdictionalActivityAppealsWebPortlet_INSTANCE_P4XO16kCEH4o"
URL_HOME = "https://www.giustizia-amministrativa.it/web/guest/ricorsi-cds"

sessione = requests.Session()
sessione.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.7",
})
p_auth_token = ""


def ora_locale():
    return datetime.now(timezone.utc) + timedelta(hours=2)


# ============================================================
# Funzioni base (identiche al TAR, adattate per CdS)
# ============================================================

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
        print("[CdS] p_auth: " + (p_auth_token or "non trovato"))
        print("[CdS] Cookie: " + str(list(sessione.cookies.keys())))
        return True
    except Exception as e:
        print("[CdS ERRORE] Sessione: " + str(e))
        return False


def fetch_ricorso(anno, numero):
    url = (
        URL_HOME + "?p_p_id=" + PORTLET
        + "&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view"
        + "&_" + PORTLET + "_javax.portlet.action=/appeals/detail"
        + "&p_auth=" + p_auth_token
    )
    form_data = {
        "_" + PORTLET + "_formDate": (None, str(int(ora_locale().timestamp() * 1000))),
        "_" + PORTLET + "_year":     (None, str(anno)),
        "_" + PORTLET + "_number":   (None, str(numero)),
        "_" + PORTLET + "_search":   (None, ""),
    }
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": URL_HOME,
        "Origin": "https://www.giustizia-amministrativa.it",
        "X-Requested-With": "XMLHttpRequest",
        "X-PJAX": "true",
    }
    try:
        resp = sessione.post(url, headers=headers, files=form_data, timeout=30, verify=False)
        resp.raise_for_status()
        html = resp.text
        ha_dati = (
            "Elenco parti del fascicolo" in html and
            "[ERROR - detailException]" not in html
        )
        if ha_dati:
            return html
        return None
    except Exception as e:
        print("[CdS ERRORE] fetch_ricorso " + str(anno) + "/" + str(numero) + ": " + str(e))
        return None


def estrai_dettagli(html, anno, numero):
    dettagli = {
        "nrg":   str(anno) + str(numero).zfill(6),
        "anno":  anno,
        "numero": numero,
        "fonte": "CdS",
        "sezione": "",
        "data_deposito": "",
        "tipo_ricorso": "",
        "oggetto": "",
        "parti": [],
        "atti": [],
        "discussioni": [],
        "provvedimenti_collegiali": [],
        "provvedimenti_monocratici": [],
    }

    m = re.search(r'id="valoreSezione"[^>]*>([^<]+)<', html)
    if m: dettagli["sezione"] = m.group(1).strip()

    m = re.search(r'id="valoreDataDeposito"[^>]*>([^<]+)<', html)
    if m: dettagli["data_deposito"] = m.group(1).strip()

    m = re.search(r'id="valoreTipologiaRicorso"[^>]*>([^<]+)<', html)
    if m: dettagli["tipo_ricorso"] = m.group(1).strip()

    m = re.search(r'id="valoreOggetto"[^>]*>([^<]+)<', html)
    if m: dettagli["oggetto"] = m.group(1).strip()[:200]

    def estrai_righe_tabella(html, titolo_sezione, titolo_fine):
        pattern = titolo_sezione + r'.*?<tbody>(.*?)</tbody>.*?' + titolo_fine
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if not m: return []
        tbody = m.group(1)
        righe = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody, re.DOTALL)
        risultato = []
        for riga in righe:
            celle = re.findall(r'<td[^>]*>(.*?)</td>', riga, re.DOTALL)
            celle = [re.sub(r'<[^>]+>', '', c).strip() for c in celle]
            celle = [re.sub(r'\s+', ' ', c) for c in celle]
            if any(c for c in celle):
                risultato.append(' | '.join(celle))
        return risultato

    dettagli["parti"]                    = estrai_righe_tabella(html, "Elenco parti del fascicolo", "Atti depositati")
    dettagli["atti"]                     = estrai_righe_tabella(html, "Atti depositati", "Discussioni")
    dettagli["discussioni"]              = estrai_righe_tabella(html, "Discussioni", "Provvedimenti collegiali")
    dettagli["provvedimenti_collegiali"] = estrai_righe_tabella(html, "Provvedimenti collegiali", "Provvedimenti monocratici")
    dettagli["provvedimenti_monocratici"]= estrai_righe_tabella(html, "Provvedimenti monocratici", "INDIETRO")

    return dettagli


def confronta_dettagli(vecchio, nuovo):
    differenze = []
    sezioni = ["parti", "atti", "discussioni", "provvedimenti_collegiali", "provvedimenti_monocratici"]
    nomi = {
        "parti": "Elenco parti",
        "atti": "Atti depositati",
        "discussioni": "Discussioni",
        "provvedimenti_collegiali": "Provvedimenti collegiali",
        "provvedimenti_monocratici": "Provvedimenti monocratici",
    }
    for sezione in sezioni:
        vecchi = set(vecchio.get(sezione, []))
        nuovi  = set(nuovo.get(sezione, []))
        aggiunti = nuovi - vecchi
        rimossi  = vecchi - nuovi
        if aggiunti:
            differenze.append("➕ " + nomi[sezione] + " - Aggiunto:\n" + "\n".join("  • " + r for r in aggiunti))
        if rimossi:
            differenze.append("➖ " + nomi[sezione] + " - Rimosso:\n" + "\n".join("  • " + r for r in rimossi))
    return differenze


def invia_telegram(messaggio):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    if len(messaggio) > 4000:
        messaggio = messaggio[:4000] + "\n...(troncato)"
    try:
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": messaggio}, timeout=10)
        resp.raise_for_status()
        print("[CdS OK] Notifica Telegram inviata")
    except Exception as e:
        print("[CdS ERRORE] Telegram: " + str(e))


def carica_stato():
    if os.path.exists(STATO_FILE):
        with open(STATO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    if GH_TOKEN and GH_REPO:
        try:
            api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + STATO_FILE
            headers = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github.v3+json"}
            resp = requests.get(api_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                import base64 as b64
                contenuto = b64.b64decode(resp.json()["content"]).decode("utf-8")
                stato = json.loads(contenuto)
                with open(STATO_FILE, "w", encoding="utf-8") as f:
                    json.dump(stato, f, ensure_ascii=False, indent=2)
                print("[CdS INFO] " + STATO_FILE + " caricato da GitHub")
                return stato
        except Exception as e:
            print("[CdS WARN] Impossibile caricare stato da GitHub: " + str(e))
    return {"ricorsi_monitorati": {}}


def salva_stato(stato):
    with open(STATO_FILE, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)
    pubblica_su_github(STATO_FILE)


def pubblica_su_github(filepath):
    if not GH_TOKEN or not GH_REPO:
        print("[CdS WARN] GH_TOKEN o GH_REPO non configurati, skip")
        return
    try:
        with open(filepath, "rb") as f:
            contenuto = base64.b64encode(f.read()).decode("utf-8")
        api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + filepath
        headers = {
            "Authorization": "token " + GH_TOKEN,
            "Accept": "application/vnd.github.v3+json",
        }
        sha = None
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        payload = {"message": "Aggiorna " + filepath, "content": contenuto}
        if sha:
            payload["sha"] = sha
        resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            print("[CdS OK] " + filepath + " pubblicato su GitHub")
        elif resp.status_code in (409, 422):
            # SHA conflict: ri-scarica SHA aggiornato e riprova una volta
            print("[CdS WARN] SHA conflict, retry...")
            resp2 = requests.get(api_url, headers=headers, timeout=10)
            if resp2.status_code == 200:
                payload["sha"] = resp2.json().get("sha")
                resp3 = requests.put(api_url, headers=headers, json=payload, timeout=15)
                if resp3.status_code in (200, 201):
                    print("[CdS OK] " + filepath + " pubblicato su GitHub (retry OK)")
                else:
                    print("[CdS ERRORE] GitHub API retry: " + str(resp3.status_code) + " " + resp3.text[:200])
            else:
                print("[CdS ERRORE] SHA retry GET: " + str(resp2.status_code))
        else:
            print("[CdS ERRORE] GitHub API: " + str(resp.status_code) + " " + resp.text[:200])
    except Exception as e:
        print("[CdS ERRORE] pubblica_su_github: " + str(e))


def scarica_dashboard_da_github():
    """Scarica dashboard_data.json da GitHub per avere sempre la versione più aggiornata."""
    if not GH_TOKEN or not GH_REPO:
        return {}
    try:
        api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + DASHBOARD_FILE
        headers = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github.v3+json"}
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            contenuto = base64.b64decode(resp.json()["content"]).decode("utf-8")
            dati = json.loads(contenuto)
            print("[CdS INFO] dashboard scaricato da GitHub: " +
                  str(len(dati.get("provvedimenti_collegiali",[]))) + " coll, " +
                  str(len(dati.get("provvedimenti_monocratici",[]))) + " mono")
            return dati
    except Exception as e:
        print("[CdS WARN] Impossibile scaricare dashboard: " + str(e))
    return {}

def pubblica_dashboard_diretto(contenuto_str):
    """Pubblica dashboard_data.json direttamente dal contenuto in memoria."""
    if not GH_TOKEN or not GH_REPO:
        print("[CdS WARN] GH_TOKEN o GH_REPO non configurati, skip")
        return
    try:
        import base64 as _b64
        contenuto_b64 = _b64.b64encode(contenuto_str.encode("utf-8")).decode("utf-8")
        api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/" + DASHBOARD_FILE
        headers = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github.v3+json"}
        sha = None
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
        payload = {"message": "Aggiorna " + DASHBOARD_FILE, "content": contenuto_b64}
        if sha:
            payload["sha"] = sha
        resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            print("[CdS OK] dashboard_data.json pubblicato su GitHub")
        elif resp.status_code in (409, 422):
            print("[CdS WARN] SHA conflict, retry...")
            resp2 = requests.get(api_url, headers=headers, timeout=10)
            if resp2.status_code == 200:
                payload["sha"] = resp2.json().get("sha")
                resp3 = requests.put(api_url, headers=headers, json=payload, timeout=15)
                if resp3.status_code in (200, 201):
                    print("[CdS OK] dashboard_data.json pubblicato su GitHub (retry OK)")
                else:
                    print("[CdS ERRORE] retry: " + str(resp3.status_code) + " " + resp3.text[:200])
        else:
            print("[CdS ERRORE] GitHub API: " + str(resp.status_code) + " " + resp.text[:200])
    except Exception as e:
        print("[CdS ERRORE] pubblica_dashboard_diretto: " + str(e))


def aggiorna_dashboard(stato, ha_variazioni=False):
    """Scarica da GitHub, aggiunge i dati CdS, risalva."""
    # Scarica sempre da GitHub per non perdere i provvedimenti scritti da monitor_tar_gh.py
    dati = scarica_dashboard_da_github()
    # Fallback: legge il file locale se GitHub non risponde
    if not dati and os.path.exists(DASHBOARD_FILE):
        try:
            with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
                dati = json.load(f)
        except Exception:
            dati = {}

    # Se provvedimenti mancano (ritardo API GitHub), li recupera da tar_stato.json
    if not dati.get("provvedimenti_collegiali") and not dati.get("provvedimenti_monocratici"):
        try:
            api_url = "https://api.github.com/repos/" + GH_REPO + "/contents/tar_stato.json"
            headers = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github.v3+json"}
            resp = requests.get(api_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                import base64 as _b64
                stato_tar = json.loads(_b64.b64decode(resp.json()["content"]).decode("utf-8"))
                coll = stato_tar.get("provvedimenti_collegiali", [])
                mono = stato_tar.get("provvedimenti_monocratici", [])
                if coll or mono:
                    dati["provvedimenti_collegiali"] = coll
                    dati["provvedimenti_monocratici"] = mono
                    print("[CdS INFO] Provvedimenti recuperati da tar_stato.json (" +
                          str(len(coll)) + " coll, " + str(len(mono)) + " mono)")
        except Exception as e:
            print("[CdS WARN] Impossibile recuperare tar_stato.json: " + str(e))

    ora_str = ora_locale().strftime("%d/%m/%Y %H:%M")
    dati["ultimo_aggiornamento"] = ora_str
    dati["ultimo_controllo"]     = ora_str
    if ha_variazioni:
        dati["ultima_variazione"] = ora_str

    # Sezione CdS separata nel JSON
    ricorsi_cds = []
    for chiave, dettagli in stato.get("ricorsi_monitorati", {}).items():
        ricorsi_cds.append(dettagli)
    dati["cds_ricorsi_monitorati"] = ricorsi_cds

    # Serializza e pubblica direttamente dai dati in memoria
    # (evita di rileggere il file locale che potrebbe essere vecchio)
    contenuto_str = json.dumps(dati, ensure_ascii=False, indent=2)
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(contenuto_str)

    pubblica_dashboard_diretto(contenuto_str)


# ============================================================
# Logica principale
# ============================================================

def controlla_variazioni_ricorso(stato, anno, numero):
    print("[CdS] Controllo variazioni ricorso " + str(anno) + "/" + str(numero) + "...")
    html = fetch_ricorso(anno, numero)
    if html is None:
        print("[CdS WARN] Impossibile recuperare ricorso " + str(anno) + "/" + str(numero))
        return stato, False

    dettagli_nuovi = estrai_dettagli(html, anno, numero)
    chiave = str(anno) + "_" + str(numero)

    if chiave not in stato["ricorsi_monitorati"]:
        stato["ricorsi_monitorati"][chiave] = dettagli_nuovi
        print("[CdS] Ricorso " + str(anno) + "/" + str(numero) + ": stato iniziale salvato")
        return stato, False

    dettagli_vecchi = stato["ricorsi_monitorati"][chiave]
    differenze = confronta_dettagli(dettagli_vecchi, dettagli_nuovi)

    if differenze:
        ora = ora_locale().strftime("%d/%m/%Y %H:%M")
        msg = "🔔 CdS - Variazione ricorso " + str(anno) + "/" + str(numero) + "\nRilevata il " + ora + "\n\n"
        msg += "\n\n".join(differenze)
        invia_telegram(msg)
        dettagli_nuovi["data_rilevazione"] = ora
        # Salva timestamp per ogni singolo evento nuovo (per ordinamento preciso nel feed)
        ts_eventi = dict(dettagli_vecchi.get("ts_eventi", {}))
        for sezione in ["atti", "discussioni", "provvedimenti_collegiali", "provvedimenti_monocratici"]:
            vecchi_set = set(dettagli_vecchi.get(sezione, []))
            for item in dettagli_nuovi.get(sezione, []):
                if item not in vecchi_set:
                    ts_eventi[item] = ora
        dettagli_nuovi["ts_eventi"] = ts_eventi
        stato["ricorsi_monitorati"][chiave] = dettagli_nuovi
        print("[CdS] Ricorso " + str(anno) + "/" + str(numero) + ": " + str(len(differenze)) + " variazioni trovate")
        return stato, True
    else:
        print("[CdS] Ricorso " + str(anno) + "/" + str(numero) + ": nessuna variazione")

    return stato, False


def main():
    print("[CdS] Avvio controllo ricorsi: " + ora_locale().strftime("%d/%m/%Y %H:%M"))

    if not inizializza_sessione():
        print("[CdS ERRORE] Impossibile connettersi al sito")
        return

    stato = carica_stato()

    ha_variazioni = False
    for anno, numero in RICORSI_DA_MONITORARE:
        stato, variato = controlla_variazioni_ricorso(stato, anno, numero)
        if variato:
            ha_variazioni = True

    salva_stato(stato)
    aggiorna_dashboard(stato, ha_variazioni)

    print("[CdS] Fine controllo ricorsi CdS")


if __name__ == "__main__":
    main()
