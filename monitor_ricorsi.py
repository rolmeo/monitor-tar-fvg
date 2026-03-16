import requests
import json
import os
import re
from datetime import datetime
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
STATO_FILE = "C:\\TAR\\tar_ricorsi_stato.json"

# Anno usato per la ricerca di NUOVI ricorsi
ANNO_NUOVI = 2026

# Ricorsi specifici da monitorare per variazioni.
# Formato: (anno, numero)
# Esempi:
#   (2026, 99)   -> ricorso 99 del 2026
#   (2025, 150)  -> ricorso 150 del 2025
RICORSI_DA_MONITORARE = [
    (2026, 99),
    (2026, 100),
    (2026, 80),
    (2026, 74),
    (2026, 51),
    (2025, 689),
    (2025, 686),
    (2025, 479),
    (2026, 120),
    (2026, 121)
    (2026, 126]

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
    """Recupera la pagina HTML di un ricorso. Restituisce l'HTML o None se non trovato."""
    url = (
        URL_HOME + "?p_p_id=" + PORTLET
        + "&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view"
        + "&_" + PORTLET + "_javax.portlet.action=/appeals/detail"
        + "&p_auth=" + p_auth_token
    )
    form_data = {
        "_" + PORTLET + "_formDate": (None, str(int(datetime.now().timestamp() * 1000))),
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
    """Estrae i dettagli principali del ricorso dall'HTML."""
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

    # Estrai campi base usando gli id HTML specifici della pagina
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

    # Estrai tabelle usando regex sulle righe <tr>
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
    """Confronta due versioni dei dettagli e restituisce le differenze."""
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
    return {
        "ultimo_numero": 109,
        "ricorsi_monitorati": {}
    }


def salva_stato(stato):
    os.makedirs(os.path.dirname(STATO_FILE), exist_ok=True)
    with open(STATO_FILE, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=2)


# ============================================================
# Logica principale
# ============================================================

def controlla_nuovi_ricorsi(stato):
    """Cerca nuovi ricorsi partendo dall'ultimo numero noto."""
    ultimo = stato.get("ultimo_numero", 109)
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
        ora = datetime.now().strftime("%d/%m/%Y %H:%M")
        for d in trovati:
            msg = "🆕 TAR Friuli - Nuovo ricorso\nRilevato il " + ora + "\n\n"
            msg += "NRG: " + d["nrg"] + " | Sezione: " + d["sezione"] + "\n"
            msg += "Data deposito: " + d["data_deposito"] + "\n"
            msg += "Tipo: " + d["tipo_ricorso"] + "\n"
            msg += "Oggetto: " + d["oggetto"] + "\n"
            invia_telegram(msg)

    return stato


def controlla_variazioni_ricorso(stato, anno, numero):
    """Controlla se ci sono variazioni in un ricorso specifico."""
    print("[INFO] Controllo variazioni ricorso " + str(anno) + "/" + str(numero) + "...")
    html = fetch_ricorso(anno, numero)
    if html is None:
        print("[WARN] Impossibile recuperare ricorso " + str(anno) + "/" + str(numero))
        return stato

    dettagli_nuovi = estrai_dettagli(html, anno, numero)

    # La chiave include l'anno per distinguere ricorsi di anni diversi
    chiave = str(anno) + "_" + str(numero)

    if chiave not in stato["ricorsi_monitorati"]:
        stato["ricorsi_monitorati"][chiave] = dettagli_nuovi
        print("[INFO] Ricorso " + str(anno) + "/" + str(numero) + ": stato iniziale salvato")
        return stato

    dettagli_vecchi = stato["ricorsi_monitorati"][chiave]
    differenze = confronta_dettagli(dettagli_vecchi, dettagli_nuovi)

    if differenze:
        ora = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg = "🔔 TAR Friuli - Variazione ricorso " + str(anno) + "/" + str(numero) + "\nRilevata il " + ora + "\n\n"
        msg += "\n\n".join(differenze)
        invia_telegram(msg)
        stato["ricorsi_monitorati"][chiave] = dettagli_nuovi
        print("[INFO] Ricorso " + str(anno) + "/" + str(numero) + ": " + str(len(differenze)) + " variazioni trovate")
    else:
        print("[INFO] Ricorso " + str(anno) + "/" + str(numero) + ": nessuna variazione")

    return stato


def main():
    
    print("[INFO] Avvio controllo ricorsi: " + datetime.now().strftime("%d/%m/%Y %H:%M"))

    if not inizializza_sessione():
        print("[ERRORE] Impossibile connettersi al sito")
        return

    stato = carica_stato()

    # 1. Controlla nuovi ricorsi
    stato = controlla_nuovi_ricorsi(stato)

    # 2. Controlla variazioni nei ricorsi monitorati
    for anno, numero in RICORSI_DA_MONITORARE:
        stato = controlla_variazioni_ricorso(stato, anno, numero)

    salva_stato(stato)
    print("[INFO] Fine controllo ricorsi")


if __name__ == "__main__":
    main()
