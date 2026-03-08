# Commit Checklist für pecz Repo

## Ziel-Repository
```
https://github.com/dpxyz/pecz.git
```

## Verzeichnis-Struktur im Repo

```
pecz/
└── forward_v5/
    └── docs/
        └── site/              # ← Mission Control
            ├── mkdocs.yml
            ├── requirements.txt
            ├── index.md
            ├── phases.md
            ├── roadmap.md
            ├── blockers.md
            ├── test-reports.md
            ├── economics.md
            ├── changelog.md
            │
            ├── architecture/
            │   └── index.md
            │
            ├── runbooks/
            │   └── index.md
            │
            ├── strategy-lab/
            │   └── index.md
            │
            ├── milestones/
            │   ├── m5.md       # → symlink/copy von ../../M5_SUMMARY.md
            │   └── m6.md       # → symlink/copy von ../../M6_SUMMARY_EXEC.md
            │
            └── .cloudflare/
                └── DEPLOY_CFPAGES.md
```

## Erster Commit (Minimal)

### Phase 1: Grundgerüst
```bash
cd /pfad/zu/pecz

# Verzeichnis erstellen
mkdir -p forward_v5/docs/site/.cloudflare
mkdir -p forward_v5/docs/site/architecture
mkdir -p forward_v5/docs/site/runbooks
mkdir -p forward_v5/docs/site/strategy-lab
mkdir -p forward_v5/docs/site/milestones

# Files kopieren (aus lokalem workspace)
cp -r /data/.openclaw/workspace/forward_v5/docs/site/* forward_v5/docs/site/

# Oder: einzelne Files
```

### Phase 2: Files commiten

```bash
cd /pfad/zu/pecz

git add forward_v5/docs/site/mkdocs.yml
git add forward_v5/docs/site/requirements.txt
git add forward_v5/docs/site/index.md
git add forward_v5/docs/site/phases.md
git add forward_v5/docs/site/roadmap.md
git add forward_v5/docs/site/blockers.md
git add forward_v5/docs/site/test-reports.md
git add forward_v5/docs/site/economics.md
git add forward_v5/docs/site/changelog.md
git add forward_v5/docs/site/architecture/
git add forward_v5/docs/site/runbooks/
git add forward_v5/docs/site/strategy-lab/
git add forward_v5/docs/site/milestones/
git add forward_v5/docs/site/.cloudflare/

git commit -m "Add Forward V5 Mission Control (MkDocs)"

git push origin main
```

## Reihenfolge

| # | File | Priorität | Grund |
|---|------|-----------|-------|
| 1 | `mkdocs.yml` | KRITISCH | Build-Konfiguration |
| 2 | `requirements.txt` | KRITISCH | Dependencies |
| 3 | `index.md` | KRITISCH | Startseite |
| 4 | `phases.md` | KRITISCH | Phasenplan |
| 5 | `roadmap.md` | HOCH | Aufgaben |
| 6 | `blockers.md` | HOCH | Blocker |
| 7 | `test-reports.md` | MITTEL | Tests |
| 8 | `economics.md` | MITTEL | Wirtschaftlichkeit |
| 9 | `changelog.md` | NIEDRIG | Historie |
| 10 | `architecture/` | MITTEL | ADRs |
| 11 | `runbooks/` | MITTEL | Prozeduren |
| 12 | `strategy-lab/` | MITTEL | Strategien |
| 13 | `milestones/` | NIEDRIG | Externe Doku |
| 14 | `.cloudflare/` | HOCH | Deploy-Doku |

## Was NICHT committen

```bash
# Diese Files/Dirs ignorieren
echo "site/" >> forward_v5/docs/site/.gitignore        # Build-Output
echo "venv/" >> forward_v5/docs/site/.gitignore       # Python Env
echo "__pycache__/" >> .gitignore                     # Python Cache
```

## Cloudflare Deploy Test

Nach dem Push:

1. Cloudflare Dashboard → Pages
2. Neues Projekt → Connect to Git → `dpxyz/pecz`
3. Build Settings:
   - Build command: `cd forward_v5/docs/site && pip install -r requirements.txt && mkdocs build`
   - Output dir: `forward_v5/docs/site/site`
4. Deploy

## Schnell-Test (lokal)

```bash
cd pecz/forward_v5/docs/site

# Python Env
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Build
mkdocs build

# Server
mkdocs serve

# → http://127.0.0.1:8000
```

---

Last updated: 2026-03-06 13:07 UTC
