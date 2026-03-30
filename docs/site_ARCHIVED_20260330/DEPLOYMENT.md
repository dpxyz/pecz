# GitHub Pages Deployment

## Voraussetzungen

- GitHub Repository `forward_v5`
- Python 3.8+
- pip

---

## Installation (lokal)

```bash
# Ins Verzeichnis wechseln
cd forward_v5/docs/site

# Python venv erstellen
python3 -m venv venv
source venv/bin/activate

# MkDocs + Material installieren
pip install mkdocs-material
pip install mkdocs-git-revision-date-localized-plugin

# Lokaler Server
mkdocs serve

# Öffne: http://127.0.0.1:8000
```

---

## Manuelle Inhalte

Diese Dateien werden **manuell** gepflegt:

| Datei | Pflege | Beschreibung |
|-------|--------|--------------|
| `index.md` | Manuel | Startseite, Status, GO/NO-GO |
| `phases.md` | Manuel | Phasenplan 0-9 |
| `roadmap.md` | Manuel | Aktuelle Aufgaben |
| `blockers.md` | Manuel | Offene Blocker |
| `architecture/*.md` | Manuel | ADRs |
| `runbooks/*.md` | Manuel | Operating Procedures |
| `strategy-lab/*.md` | Manuel | Strategie-Doku |
| `mkdocs.yml` | Manuel | Navigation, Theme |

---

## Automatische Inhalte

Diese Inhalte werden **automatisch** generiert/eingebunden:

| Quelle | Ziel | Methode |
|--------|------|---------|
| `docs/M5_SUMMARY.md` | `milestones/m5.md` | Symlink/Copy |
| `docs/M6_canary_release_plan.md` | `milestones/m6.md` | Symlink/Copy |
| Test Results | `test-reports.md` | Cron/CI update |
| Git Commit | Footer timestamp | Plugin |
| Build Date | Site info | Plugin |

### Auto-Update Script

```bash
#!/bin/bash
# update-site.sh

echo "Updating Mission Control..."

# Kopiere externe Dokumente
cp ../M5_SUMMARY.md milestones/m5.md
cp ../M6_SUMMARY_EXEC.md milestones/m6.md
cp ../ADR-001-target-architecture.md architecture/adr-001.md
cp ../ADR-002-hyperliquid-integration.md architecture/adr-002.md

# Timestamp aktualisieren
echo "---" > generated/timestamp.md
echo "title: \"Generated Timestamp\"" >> generated/timestamp.md
echo "---" >> generated/timestamp.md
echo "" >> generated/timestamp.md
echo "# Build Information" >> generated/timestamp.md
echo "" >> generated/timestamp.md
echo "**Generated:** $(date -u '+%Y-%m-%d %H:%M UTC')" >> generated/timestamp.md
echo "" >> generated/timestamp.md
echo "**Commit:** $(git rev-parse --short HEAD)" >> generated/timestamp.md
echo "" >> generated/timestamp.md
echo "**Status:** Phase 1 In Progress" >> generated/timestamp.md

# Build
mkdocs build

echo "Done!"
```

---

## GitHub Pages Deployment

### 1. Repository Settings

```
Settings → Pages → Source
Branch: gh-pages
Folder: / (root)
```

### 2. GitHub Action `.github/workflows/docs.yml`

```yaml
name: Deploy Docs

on:
  push:
    branches:
      - main
    paths:
      - 'docs/site/**'
      - 'docs/**.md'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install mkdocs-material
          pip install mkdocs-git-revision-date-localized-plugin
      
      - name: Copy external docs
        run: |
          mkdir -p docs/site/milestones
          cp docs/M5_SUMMARY.md docs/site/milestones/m5.md || true
          cp docs/M6_SUMMARY_EXEC.md docs/site/milestones/m6.md || true
          cp docs/ADR-001-target-architecture.md docs/site/architecture/adr-001.md || true
          cp docs/ADR-002-hyperliquid-integration.md docs/site/architecture/adr-002.md || true
      
      - name: Build
        run: |
          cd docs/site
          mkdocs build
      
      - name: Setup Pages
        uses: actions/configure-pages@v4
      
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: 'docs/site/site'
      
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### 3. Erster Deploy

```bash
# Lokal bauen und deployen (erstmalig)
cd forward_v5/docs/site
mkdocs gh-deploy --force

# Oder warten auf GitHub Action
```

---

## URL

Nach Deployment erreichbar unter:

```
https://user.github.io/forward_v5
```

---

## Lokale Entwicklung

```bash
cd forward_v5/docs/site

# Aktiviere venv
source venv/bin/activate

# Start dev server
mkdocs serve

# Öffne http://127.0.0.1:8000

# Änderungen werden live neu geladen
```

---

## Content Update Workflow

### Manuelle Updates

```
1. Markdown editieren
2. mkdocs serve (testen)
3. git commit -m "Update docs"
4. git push
5. GitHub Action deployed automatisch
```

### Auto-Updates

```
1. Externe Dokumente ändern (z.B. M5_SUMMARY.md)
2. Cron/CI ruft update-site.sh auf
3. Dateien werden kopiert
4. mkdocs build
5. Deploy
```

---

## Struktur

```
forward_v5/
├── docs/
│   ├── M5_SUMMARY.md              # ← Manuelles Original
│   ├── M6_SUMMARY_EXEC.md         # ← Manuelles Original
│   ├── ADR-*.md                   # ← Manuelles Original
│   └── site/                      # ← Mission Control
│       ├── mkdocs.yml             # ← Manuelle Config
│       ├── index.md               # ← Manuel (Status)
│       ├── phases.md              # ← Manuel (Phasen)
│       ├── milestones/            # ← Auto (Kopien)
│       │   ├── m5.md              # ← Auto (from M5_SUMMARY)
│       │   └── m6.md              # ← Auto (from M6_SUMMARY)
│       ├── architecture/          # ← Manuel + Auto
│       │   ├── index.md           # ← Manuel
│       │   └── adr-*.md           # ← Auto (Kopien)
│       └── generated/             # ← Auto (Timestamp)
└── .github/workflows/
    └── docs.yml                   # ← CI/CD
```

---

Last updated: 2026-03-06 12:41 UTC
