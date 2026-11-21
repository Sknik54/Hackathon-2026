# 🚀 Hackathon – Teamprojekt

Dieses Repository enthält unser Hackathon-Projekt mit **React (Frontend)** und **Python (Backend)**. Für die KI-Funktionen verwenden wir **Google ADK** und die **Gemini API**. **Codex** kann uns beim Programmieren in VS Code unterstützen.

> **Wichtig:** Am Anfang ist möglicherweise nur `backend/` vorhanden. Das React-Frontend und der eigentliche Anwendungscode werden beim Hackathon erstellt.

## 1. Voraussetzungen

Auf jedem Computer benötigen wir:

- [Git](https://git-scm.com/downloads)
- [VS Code](https://code.visualstudio.com/)
- **Python 3.13**
- [Node.js (LTS)](https://nodejs.org/) inkl. npm (für React)
- Optional: **Codex**-Erweiterung von OpenAI für VS Code

Versionen im Terminal prüfen:

```powershell
py -V:3.13 --version
node --version
npm --version
git --version
```

Unter Windows mit dem Python Install Manager lässt sich Python 3.13 bei Bedarf so installieren:

```powershell
py install 3.13
```

## 2. Repository klonen

Im Terminal in den gewünschten Arbeitsordner wechseln und dann:

```powershell
git clone <REPOSITORY-URL>
cd <REPOSITORY-ORDNER>
```

Die Platzhalter durch die URL und den Namen unseres GitHub-Repositories ersetzen. Alternativ: Repository in VS Code mit **Git: Clone** klonen.

## 3. Projektstruktur

```text
hackathon/                 # Repository-Hauptordner
├── README.md
├── .gitignore
├── backend/
│   ├── .venv/             # Nur lokal; NICHT hochladen
│   ├── requirements.txt   # Python-Abhängigkeiten
│   ├── main.py            # Wird bei Projektstart erstellt
│   ├── agent.py           # Optional: ADK-Agent / eigene Agentenstruktur
│   └── .env               # API-Key; nur lokal, NICHT hochladen
└── frontend/              # Wird beim Hackathon mit Vite erstellt
    ├── src/
    ├── package.json
    └── node_modules/      # Nur lokal; NICHT hochladen
```

**Python-Code gehört nach `backend/`, aber niemals in `.venv/`.** React-Code gehört nach `frontend/src/`.

## 4. Python-Backend einrichten (Windows)

Ein Terminal in VS Code öffnen und **vom Repository-Hauptordner** aus ausführen:

```powershell
cd backend
py -V:3.13 -m venv .venv
```

Virtuelle Umgebung aktivieren:

**PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Oder CMD:**

```cmd
.venv\Scripts\activate.bat
```

Wenn PowerShell die Aktivierung blockiert, einfach in VS Code ein **CMD-Terminal** öffnen und den CMD-Befehl verwenden.

Anschließend die vorbereiteten Python-Abhängigkeiten installieren:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Damit werden unter anderem `google-adk`, `google-genai`, `fastapi` und `uvicorn` installiert, sofern sie in `requirements.txt` stehen.

Installation testen:

```powershell
python --version
python -c "import google.adk; import google.genai; import fastapi; print('Backend-Pakete OK')"
```

**In VS Code:** `Strg + Shift + P` → **Python: Select Interpreter** → `backend/.venv/Scripts/python.exe` auswählen.

> Eine virtuelle Umgebung muss **nicht** bei jedem Start neu erstellt werden. In einem neuen Terminal muss sie nur wieder aktiviert werden.

## 5. Gemini API-Key einrichten

1. Einen API-Key in [Google AI Studio](https://aistudio.google.com/app/apikey) erstellen (Zugriff und mögliche Kosten prüfen).
2. Im `backend/`-Ordner eine Datei namens `.env` erstellen.
3. Folgendes eintragen:

```dotenv
GOOGLE_API_KEY=HIER_DEINEN_EIGENEN_KEY_EINTRAGEN
GOOGLE_GENAI_USE_VERTEXAI=FALSE
```

Jedes Teammitglied verwendet einen eigenen berechtigten API-Key bzw. die vom Team vereinbarte sichere Lösung. **Niemals `.env` oder API-Keys committen, in React-Code einbauen oder in den Chat posten.** Der Key wird nur im Backend verwendet.

## 6. React-Frontend einrichten (beim Hackathon)

Falls `frontend/` noch **nicht existiert**, im Repository-Hauptordner:

```powershell
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm run dev
```

Wenn `frontend/` bereits von jemandem erstellt und ins Repository hochgeladen wurde, **nicht erneut Vite ausführen**. Stattdessen:

```powershell
cd frontend
npm install
npm run dev
```

Die im Terminal angezeigte lokale URL im Browser öffnen (oft `http://localhost:5173`).

> `npm install` installiert die JavaScript-Pakete aus `package.json`. Das ist getrennt von den Python-Packages in `backend/.venv`.

## 7. Backend und Frontend starten

Wir nutzen normalerweise **zwei VS-Code-Terminals**:

**Terminal 1 – Backend:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
```

Sobald wir eine FastAPI-Anwendung mit der Variable `app` in `main.py` erstellt haben:

```powershell
uvicorn main:app --reload
```

Standardadresse: `http://127.0.0.1:8000` (API-Dokumentation: `/docs`).

**Terminal 2 – Frontend:**

```powershell
cd frontend
npm run dev
```

Die angezeigte URL öffnen. **Die Startbefehle für Backend und Agenten passen wir an, sobald die Projektidee und die Dateien feststehen.**

## 8. Wenn wir weitere Packages brauchen

**Python (bei aktivierter `.venv` im Ordner `backend/`):**

```powershell
python -m pip install PAKETNAME
python -m pip freeze > requirements.txt
```

Änderungen an `requirements.txt` committen, damit andere sie mit `python -m pip install -r requirements.txt` übernehmen können.

**React (im Ordner `frontend/`):**

```powershell
npm install PAKETNAME
```

Danach `package.json` und `package-lock.json` committen, **nicht** `node_modules/`.

## 9. Git-Zusammenarbeit

Vor Arbeitsbeginn die neuesten Änderungen holen:

```powershell
git pull
```

Am besten arbeitet jede Person in einem eigenen Branch:

```powershell
git switch -c feature/mein-feature
```

Nach einer Änderung:

```powershell
git add .
git commit -m "Beschreibe die Änderung"
git push -u origin feature/mein-feature
```

Danach auf GitHub einen **Pull Request** erstellen, damit Änderungen geprüft und zusammengeführt werden können. Vor dem Commit mit `git status` prüfen, welche Dateien hochgeladen werden.

## 10. Empfohlene Aufgabenaufteilung für morgen

- **Frontend:** React-Seiten, Komponenten, Design, Benutzerinteraktionen
- **Backend:** FastAPI-Endpunkte und Verbindung zum Frontend
- **KI:** Google-ADK-Agent, Gemini-Prompts, Tool-Anbindungen
- **Integration & Tests:** Komponenten verbinden, Fehler beheben, Demo vorbereiten

Die Rollen sind Vorschläge: Vor dem Start kurz absprechen, wer welche Bereiche übernimmt. Zuerst eine kleine funktionierende End-to-End-Demo bauen und danach erweitern.

## 11. `.gitignore`

Im **Repository-Hauptordner** eine Datei `.gitignore` mit folgendem Inhalt anlegen:

```gitignore
# Python
**/.venv/
**/__pycache__/
*.py[cod]
.pytest_cache/

# Geheimnisse / lokale Konfiguration
**/.env
**/.env.*
!**/.env.example

# Node / Vite
**/node_modules/
**/dist/

# Editor / Betriebssystem
.vscode/
.DS_Store
Thumbs.db
```

**Nicht ignorieren:** `README.md`, `backend/requirements.txt`, `frontend/package.json` und `frontend/package-lock.json`.

## ✅ Checkliste vor dem Hackathon

- [ ] Repository geklont und in VS Code geöffnet
- [ ] Python 3.13 installiert
- [ ] `backend/.venv` erstellt und aktiviert
- [ ] `python -m pip install -r requirements.txt` erfolgreich
- [ ] Python-Interpreter in VS Code ausgewählt
- [ ] Node.js und npm funktionieren
- [ ] Gemini API-Key sicher in `backend/.env` abgelegt
- [ ] Codex in VS Code eingerichtet (optional)
- [ ] Aufgaben im Team verteilt

**Viel Erfolg beim Hackathon! 🚀**
