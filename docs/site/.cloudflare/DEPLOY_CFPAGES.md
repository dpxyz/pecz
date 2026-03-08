# Cloudflare Pages Deployment

## Repo-Struktur

```
pecz/
├── forward_v5/
│   └── docs/
│       └── site/           # ← Mission Control Root
│           ├── mkdocs.yml
│           ├── index.md
│           ├── requirements.txt
│           └── ...
├── andere_projekte/
└── ...
```

**Wichtig:** Root des Repos ist `pecz/`, nicht `forward_v5/`

---

## Cloudflare Pages Setup

### 1. Neue Pages-Projekt erstellen

1. Cloudflare Dashboard → Pages
2. "Create a project"
3. "Connect to Git"
5. Repository: `dpxyz/pecz`
6. Branch: `main`

### 2. Build-Konfiguration

| Setting | Wert |
|---------|------|
| **Framework preset** | None (Custom) |
| **Build command** | `cd forward_v5/docs/site && pip install -r requirements.txt && mkdocs build` |
| **Build output directory** | `forward_v5/docs/site/site` |
| **Root directory** | `/` (oder leer) |

### 3. Build-Einstellungen (Umgebungsvariablen)

| Variable | Wert |
|----------|------|
| `PYTHON_VERSION` | `3.11` |

### 4. Erster Deploy

Push auf main → Auto-Deploy

---

## Alternative: Build Command (einfacher)

Falls Cloudflare Probleme mit `cd` hat:

**Build command:**
```bash
pip install -r forward_v5/docs/site/requirements.txt && cd forward_v5/docs/site && mkdocs build
```

**Build output:**
```
forward_v5/docs/site/site
```

---

## Lokale Vorschau

```bash
# Repo klonen
git clone https://github.com/dpxyz/pecz.git
cd pecz/forward_v5/docs/site

# Python-Env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Dev server
mkdocs serve

# → http://127.0.0.1:8000
```

---

## Ziel-URL

Nach Deploy:
```
https://pecz.pages.dev
```

Oder eigene Domain:
```
https://mission-control.ihre-domain.de
```

---

## Automatische Deploys

| Trigger | Action |
|---------|--------|
| Push zu `main` | Auto-Deploy |
| PR Preview | Auto-Preview-URL |
| Branch deploy | Manuelle Auswahl |

---

## Troubleshooting

### Build fehlt `mkdocs`

**Fehler:** `mkdocs: command not found`

**Lösung:** `requirements.txt` muss im Root der Build-Umgebung installiert werden

### Pfad-Fehler

**Fehler:** `mkdocs.yml not found`

**Lösung:** Build command mit `cd` oder absolute Pfade

### Python Version

**Fehler:** Package incompatibility

**Lösung:** Umgebungsvariable `PYTHON_VERSION=3.11` setzen

---

## Backup: Vercel

Falls Cloudflare Probleme macht:

### Vercel Setup

1. Vercel Dashboard → New Project
2. Import from GitHub: `dpxyz/pecz`
3. Framework: Other
4. Build Command: `cd forward_v5/docs/site && pip install -r requirements.txt && mkdocs build`
5. Output Dir: `forward_v5/docs/site/site`

---

## Rollout-Plan

| Schritt | Action | Status |
|---------|--------|--------|
| 1 | `pecz` Repo erstellen/bereitmachen | ⏳ |
| 2 | Files committen (siehe unten) | ⏳ |
| 3 | Cloudflare Pages Projekt anlegen | ⏳ |
| 4 | Build testen | ⏳ |
| 5 | DNS/Domain (optional) | ⏳ |

---

Last updated: 2026-03-06 13:07 UTC
