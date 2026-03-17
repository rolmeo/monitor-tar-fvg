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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "")
STATO_FILE = "tar_ricorsi_stato.json"
DASHBOARD_FILE = "dashboard_data.json"

# Anno usato per la ricerca di NUOVI ricorsi
ANNO_NUOVI = 2026

# Ricorsi specifici da monitorare per variazioni.
RICORSI_DA_MONITORARE = [
    # 2024
    (2024, 406),
    # 2025
    (2025, 257),
    (2025, 267),
    (2025, 268),
    (2025, 270),
    (2025, 399),
    (2025, 403),
    (2025, 404),
    (2025, 405),
    (2025, 479),
    (2025, 686),
    (2025, 689),
    # 2026
    (2026, 51),
    (2026, 74),
    (2026, 80),
    (2026, 99),
    (2026, 100),
    (2026, 120),
    (2026, 121),
    (2026, 123),
    (2026, 125),
    (2026, 126),
]

# ============================================================
# URL e portlet
# ============================================================
PORTLET = "it_indra_ga_institutional_area_JurisdictionalActivityAppealsWebPortlet_INSTANCE_7cHhL3QMaX4o"
URL_HOME = "https://www.giustizia-amministrativa.it/web/guest/ricorsi-tar-friuli-venezia-giulia"

sessione = requests.Session()
sessione.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.7",
})
p_auth_token = ""


def ora_locale():
    return datetime.now(timezone.utc) + timedelta(hours=1)


# ============================================================
# Funzioni base
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
        print("[INFO] p_auth: " + (p_auth_token or "non trovato"))
        print("[INFO] Cookie: " + str(list(sessione.cookies.keys())))
        return True
    except Exception as e:
        print("[ERRORE] Sessione: " + str(e))
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
        "_" + PORTLET + "_year": (None, str(anno)),
        "_" + PORTLET + "_number": (None, str(numero)),
        "_" + PORTLET + "_search": (None, ""),
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
        print("[ERRORE] fetch_ricorso " + str(anno) + "/" + str(numero) + ": " + str(e))
        return None


def estrai_dettagli(html, anno, numero):
    dettagli = {
        "nrg": str(anno) + str(numero).zfill(6),
        "anno": anno,
        "numero": numero,
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
    if m:
        dettagli["sezione"] = m.group(1).strip()

    m = re.search(r'id="valoreDataDeposito"[^>]*>([^<]+)<', html)
    if m:
        dettagli["data_deposito"] = m.group(1).strip()

    m = re.search(r'id="valoreTipologiaRicorso"[^>]*>([^<]+)<', html)
    if m:
        dettagli["tipo_ricorso"] = m.group(1).strip()

    m = re.search(r'id="valoreOggetto"[^>]*>([^<]+)<', html)
    if m:
        dettagli["oggetto"] = m.group(1).strip()[:200]

    def estrai_righe_tabella(html, titolo_sezione, titolo_fine):
        pattern = titolo_sezione + r'.*?<tbody>(.*?)</tbody>.*?' + titolo_fine
        m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if not m:
            return []
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

    dettagli["parti"] = estrai_righe_tabella(html, "Elenco parti del fascicolo", "Atti depositati")
    dettagli["atti"] = estrai_righe_tabella(html, "Atti depositati", "Discussioni")
    dettagli["discussioni"] = estrai_righe_tabella(html, "Discussioni", "Provvedimenti collegiali")
    dettagli["provvedimenti_collegiali"] = estrai_righe_tabella(html, "Provvedimenti collegiali", "Provvedimenti monocratici")
    dettagli["provvedimenti_monocratici"] = estrai_righe_tabella(html, "Provvedimenti monocratici", "INDIETRO")

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
        nuovi = set(nuovo.get(sezione, []))
        aggiunti = nuovi - vecchi
        rimossi = vecchi - nuovi
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
        print("[OK] Notifica Telegram inviata")
    except Exception as e:
        print("[ERRORE] Telegram: " + str(e))


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
                print("[INFO] " + STATO_FILE + " caricato da GitHub")
                return stato
        except Exception as e:
            print("[WARN] Impossibile caricare stato da GitHub: " + str(e))
    return {"ultimo_numero": 120, "ricorsi_monitorati": {}}


def salva_stato(stato):
    with open(STATO_FILE, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)
    pubblica_su_github(STATO_FILE)


def pubblica_su_github(filepath):
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


def aggiorna_dashboard(stato, ha_variazioni=False):
    """Legge dashboard_data.json esistente, aggiorna la sezione ricorsi e salva."""
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
    dati["ultimo_ricorso"] = stato.get("ultimo_numero", 0)
    dati["anno_nuovi"] = ANNO_NUOVI

    # Lista ricorsi monitorati con dettagli
    ricorsi = []
    for chiave, dettagli in stato.get("ricorsi_monitorati", {}).items():
        ricorsi.append(dettagli)
    dati["ricorsi_monitorati"] = ricorsi

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)

    pubblica_su_github(DASHBOARD_FILE)


# ============================================================
# Logica principale
# ============================================================

def controlla_nuovi_ricorsi(stato):
    ultimo = stato.get("ultimo_numero", 120)
    trovati = []

    while True:
        prossimo = ultimo + 1
        print("[INFO] Provo ricorso " + str(ANNO_NUOVI) + "/" + str(prossimo) + "...")
        html = fetch_ricorso(ANNO_NUOVI, prossimo)
        if html is None:
            print("[INFO] Ricorso " + str(ANNO_NUOVI) + "/" + str(prossimo) + " non trovato - stop")
            break
        dettagli = estrai_dettagli(html, ANNO_NUOVI, prossimo)
        trovati.append(dettagli)
        print("[INFO] Trovato nuovo ricorso " + str(ANNO_NUOVI) + "/" + str(prossimo) + "!")
        ultimo = prossimo

    if trovati:
        stato["ultimo_numero"] = ultimo
        ora = ora_locale().strftime("%d/%m/%Y %H:%M")
        for d in trovati:
            msg = "🆕 TAR Friuli - Nuovo ricorso\nRilevato il " + ora + "\n\n"
            msg += "NRG: " + d["nrg"] + " | Sezione: " + d["sezione"] + "\n"
            msg += "Data deposito: " + d["data_deposito"] + "\n"
            msg += "Tipo: " + d["tipo_ricorso"] + "\n"
            msg += "Oggetto: " + d["oggetto"] + "\n"
            invia_telegram(msg)

    return stato


def controlla_variazioni_ricorso(stato, anno, numero):
    print("[INFO] Controllo variazioni ricorso " + str(anno) + "/" + str(numero) + "...")
    html = fetch_ricorso(anno, numero)
    if html is None:
        print("[WARN] Impossibile recuperare ricorso " + str(anno) + "/" + str(numero))
        return stato, False

    dettagli_nuovi = estrai_dettagli(html, anno, numero)
    chiave = str(anno) + "_" + str(numero)

    if chiave not in stato["ricorsi_monitorati"]:
        stato["ricorsi_monitorati"][chiave] = dettagli_nuovi
        print("[INFO] Ricorso " + str(anno) + "/" + str(numero) + ": stato iniziale salvato")
        return stato, False

    dettagli_vecchi = stato["ricorsi_monitorati"][chiave]
    differenze = confronta_dettagli(dettagli_vecchi, dettagli_nuovi)

    if differenze:
        ora = ora_locale().strftime("%d/%m/%Y %H:%M")
        msg = "🔔 TAR Friuli - Variazione ricorso " + str(anno) + "/" + str(numero) + "\nRilevata il " + ora + "\n\n"
        msg += "\n\n".join(differenze)
        invia_telegram(msg)
        stato["ricorsi_monitorati"][chiave] = dettagli_nuovi
        print("[INFO] Ricorso " + str(anno) + "/" + str(numero) + ": " + str(len(differenze)) + " variazioni trovate")
        return stato, True
    else:
        print("[INFO] Ricorso " + str(anno) + "/" + str(numero) + ": nessuna variazione")

    return stato, False


def main():
    print("[INFO] Avvio controllo ricorsi: " + ora_locale().strftime("%d/%m/%Y %H:%M"))

    if not inizializza_sessione():
        print("[ERRORE] Impossibile connettersi al sito")
        return

    stato = carica_stato()

    stato = controlla_nuovi_ricorsi(stato)

    ha_variazioni = False
    for anno, numero in RICORSI_DA_MONITORARE:
        stato, variato = controlla_variazioni_ricorso(stato, anno, numero)
        if variato:
            ha_variazioni = True

    salva_stato(stato)

    # Aggiorna dashboard
    aggiorna_dashboard(stato, ha_variazioni)

    print("[INFO] Fine controllo ricorsi")


if __name__ == "__main__":
    main()
