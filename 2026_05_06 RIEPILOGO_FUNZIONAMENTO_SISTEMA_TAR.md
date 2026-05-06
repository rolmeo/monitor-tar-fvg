# Sistema di Monitoraggio TAR Friuli Venezia Giulia
## Documento di riepilogo per nuove chat

---

## 1. Panoramica generale

Il sistema monitora automaticamente il sito del TAR FVG ([giustizia-amministrativa.it](https://www.giustizia-amministrativa.it)) per:
- Nuovi **provvedimenti collegiali e monocratici**
- Variazioni su **ricorsi specifici** (nuovi atti, discussioni, provvedimenti)
- Nuovi **ricorsi depositati** (a partire dall'ultimo numero noto)

Le notifiche vengono inviate via **Telegram**. I dati sono visualizzabili tramite una **web app** su Cloudflare Pages.

---

## 2. Struttura dei file

### Sul PC (`C:\TAR\`)
| File | Descrizione |
|------|-------------|
| `monitor_tar.py` | Controlla nuovi provvedimenti collegiali/monocratici |
| `monitor_ricorsi.py` | Controlla variazioni su ricorsi specifici e nuovi ricorsi |
| `push_dashboard.py` | Legge i file di stato locali e pusha `dashboard_data.json` su GitHub |
| `avvia_monitor_tar.vbs` | Lancia i tre script Python silenziosamente (senza finestra nera) |
| `tar_stato.json` | Stato locale provvedimenti (aggiornato da `monitor_tar.py`) |
| `tar_ricorsi_stato.json` | Stato locale ricorsi (aggiornato da `monitor_ricorsi.py`) |
| `.env` | File segreti locali (token Telegram) — NON caricare su GitHub |

### Su GitHub (`rolmeo/monitor-tar-fvg`) — repo pubblico
| File/Cartella | Descrizione |
|---------------|-------------|
| `dashboard_data.json` | JSON letto dall'app web, aggiornato dal PC o da GitHub Actions |
| `index.html` | App web (caricata su Cloudflare Pages via Direct Upload) |
| `.github/workflows/monitor.yml` | Workflow GitHub Actions schedulato ogni 5 minuti |
| `.github/workflows/monitor_tar_gh.py` | Versione cloud di `monitor_tar.py` |
| `.github/workflows/monitor_ricorsi_gh.py` | Versione cloud di `monitor_ricorsi.py` |

---

## 3. Logica di funzionamento

### Quando il PC è acceso
Il **Task Scheduler** di Windows esegue `avvia_monitor_tar.vbs` ogni 5 minuti (tutti i giorni, 06:00-18:00). Il VBS lancia in sequenza:
1. `monitor_tar.py` → aggiorna `tar_stato.json`
2. `monitor_ricorsi.py` → aggiorna `tar_ricorsi_stato.json`
3. `push_dashboard.py` → costruisce e pusha `dashboard_data.json` su GitHub

### Quando il PC è spento
**GitHub Actions** esegue `monitor.yml` ogni 5 minuti (in realtà con ritardi variabili di 40-60 minuti su account gratuito). Il workflow usa lo stato salvato tramite `actions/cache`.

### App web
L'app web (`tar-friuli.pages.dev`) legge `dashboard_data.json` direttamente da GitHub raw. Mostra 4 tab: **Ricorsi**, **Provved.**, **Nuovi**, **Agenda**.

---

## 4. Credenziali e token

### File `.env` (C:\TAR\.env) — solo locale
```
TELEGRAM_TOKEN=il_token_del_bot_telegram
TELEGRAM_CHAT_ID=8057616323
```

### File `push_dashboard.py` (C:\TAR\push_dashboard.py)
```python
GH_TOKEN = "il_personal_access_token_github"  # scope: repo
GH_REPO  = "rolmeo/monitor-tar-fvg"
```

### GitHub Secrets (repo → Settings → Secrets and variables → Actions)
| Secret | Valore |
|--------|--------|
| `TELEGRAM_TOKEN` | Token bot Telegram |
| `TELEGRAM_CHAT_ID` | `8057616323` |
| `GH_TOKEN` | Personal Access Token GitHub (scope: repo) |

### Token GitHub
- Creato su: github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)
- Scope richiesto: `repo`
- Va aggiornato in **2 posti** quando scade/rigenera:
  1. `C:\TAR\push_dashboard.py` → riga `GH_TOKEN = "..."`
  2. GitHub → repo → Settings → Secrets → `GH_TOKEN` → Update

### Token Telegram
- Creato/rigenerato tramite `@BotFather` su Telegram
- Va aggiornato in **2 posti** quando cambia:
  1. `C:\TAR\.env` → riga `TELEGRAM_TOKEN=...`
  2. GitHub → repo → Settings → Secrets → `TELEGRAM_TOKEN` → Update

---

## 5. Python sul PC

- Percorso Python: `C:\Users\rolan\AppData\Local\Programs\Python\Python314\python.exe`
- Comando per test manuale da PowerShell:
```powershell
C:\Users\rolan\AppData\Local\Programs\Python\Python314\python.exe C:\TAR\push_dashboard.py
```
- Output atteso:
```
[OK] dashboard_data.json aggiornato localmente
[OK] dashboard_data.json pubblicato su GitHub (200)
```

---

## 6. Task Scheduler Windows

- **Nome task:** TAR Monitor Completo
- **File VBS:** `C:\TAR\avvia_monitor_tar.vbs`
- **Schedulazione:** ogni 5 minuti, tutti i giorni, 06:00-18:00
- **Vecchi task disattivati:** "Monitor TAR Friuli decisioni" e "Monitor TAR ricorsi nuovi e 99"
- **File XML di importazione:** `TAR_Monitor_Completo.xml` (da reimportare se si modifica il task)

Per verificare che il task funzioni: Task Scheduler → seleziona il task → clicca **Esegui** → controlla su GitHub che `dashboard_data.json` abbia timestamp aggiornato con messaggio `"Aggiorna dashboard [GG/MM/YYYY HH:MM]"`.

---

## 7. GitHub Actions

- **Workflow:** `.github/workflows/monitor.yml`
- **Schedule:** `*/5 * * * *` (ogni 5 minuti, 24/7, tutti i giorni)
- **Stato cache:** `tar_stato.json` e `tar_ricorsi_stato.json` salvati tramite `actions/cache`
- **Errori temporanei** ("The job was not acquired by Runner", "Internal server error"): sono problemi lato GitHub, non del codice. Non causano perdita di dati se il PC è acceso.

---

## 8. App web — Cloudflare Pages

- **URL:** https://tar-friuli.pages.dev
- **Piattaforma:** Cloudflare Pages (Direct Upload — NON collegato automaticamente a GitHub)
- **Come aggiornare `index.html`:**
  1. Vai su dash.cloudflare.com → Workers & Pages → tar-friuli
  2. Clicca **Create deployment**
  3. Carica il nuovo `index.html`
  4. Clicca **Save and deploy**

---

## 9. Ricorsi monitorati

Anno di riferimento per nuovi ricorsi: **2026**

### In `monitor_ricorsi.py` e `monitor_ricorsi_gh.py`
```python
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
    (2026, 121),
]
```

### Anagrafica ricorsi (in `index.html` — sezione ANAGRAFICA)
| Nr ricorso | Stabilimento | Ricorrente |
|------------|-------------|------------|
| 51/2026 | Bar Frecce Tricolori | Beach Bar F.T. Sas |
| 74/2026 | Bagno Lignano | Albergo Italia Srl |
| 80/2026 | Bagno Italia | Gest. Spiaggia Italia Snc |
| 99/2026 | Portofino | Meotto Giuseppe Srl |
| 100/2026 | Lido City | Sast degli eredi Sapienza |
| 120/2026 | Ausonia | Matajur 3000 Srl |
| 121/2026 | Portofino | Matajur 3000 Srl |
| 479/2025 | Getur | Tiliaventum ASD |
| 686/2025 | Gabbiano | Gigante Giancarlo |
| 689/2025 | La Sacca | Fenice Srl |

---

## 10. Operazioni comuni

### Aggiungere un nuovo ricorso da monitorare
1. Aprire `C:\TAR\monitor_ricorsi.py` e aggiungere `(anno, numero)` in `RICORSI_DA_MONITORARE`
2. Fare lo stesso in `.github/workflows/monitor_ricorsi_gh.py` su GitHub (modifica diretta online)
3. Aggiungere la riga corrispondente in `index.html` nella variabile `ANAGRAFICA` (poi caricare su Cloudflare)

### Aggiornare il token GitHub scaduto
1. Vai su github.com → Settings → Developer settings → Personal access tokens → Regenerate
2. Aggiorna `C:\TAR\push_dashboard.py` → riga `GH_TOKEN = "..."`
3. Aggiorna GitHub → repo → Settings → Secrets → `GH_TOKEN`

### Aggiornare il token Telegram
1. Vai su Telegram → @BotFather → /mybots → API Token → Revoke
2. Aggiorna `C:\TAR\.env` → riga `TELEGRAM_TOKEN=...`
3. Aggiorna GitHub → repo → Settings → Secrets → `TELEGRAM_TOKEN`

### Verificare che tutto funzioni
```powershell
C:\Users\rolan\AppData\Local\Programs\Python\Python314\python.exe C:\TAR\push_dashboard.py
```
Poi controllare su GitHub che `dashboard_data.json` abbia commit recente.

### Forzare aggiornamento immediato della dashboard
```powershell
C:\Users\rolan\AppData\Local\Programs\Python\Python314\python.exe C:\TAR\monitor_ricorsi.py
C:\Users\rolan\AppData\Local\Programs\Python\Python314\python.exe C:\TAR\push_dashboard.py
```

---

## 11. Note di sicurezza

- Il file `C:\TAR\.env` contiene il token Telegram — **non caricarlo mai su GitHub**
- Il token GitHub è scritto in chiaro in `push_dashboard.py` — **non caricare questo file su GitHub**
- Il repo è **pubblico**: non inserire mai dati sensibili nei file Python caricati sul repo
- I token Telegram e GitHub nei GitHub Secrets sono al sicuro e non visibili pubblicamente
- In caso di token esposto accidentalmente su GitHub: revocarlo immediatamente e rigenerarlo
