# Mission Control Structure

## Übersicht

```
docs/site/
├── mkdocs.yml              # Konfiguration
├── index.md                # Startseite (Mission Control)
├── phases.md               # Phasenplan 0-9
├── roadmap.md              # Aktuelle Aufgaben
├── blockers.md             # Offene Blocker
├── test-reports.md         # Test-Übersicht
├── economics.md            # Wirtschaftlichkeit
├── changelog.md            # Änderungshistorie
├── DEPLOYMENT.md           # Deploy-Anleitung
├── STRUCTURE.md            # Diese Datei
│
├── architecture/
│   ├── index.md            # Architektur-Übersicht
│   ├── adr-001.md          # → ADR-001-target-architecture.md
│   └── adr-002.md          # ADR-002 (folgt)
│
├── runbooks/
│   ├── index.md            # Runbooks-Übersicht
│   ├── incident.md         # Incident Response
│   └── rollback.md         # Rollback-Verfahren
│
├── strategy-lab/
│   ├── index.md            # Strategy Lab Übersicht
│   └── scorecards.md       # Scorecard-Template
│
├── milestones/
│   ├── m5.md               # → M5_SUMMARY.md (auto)
│   └── m6.md               # → M6_SUMMARY_EXEC.md (auto)
│
└── generated/
    └── timestamp.md        # Auto-generiert
```

## Manuelle vs Automatische Inhalte

### Manuelle Inhalte (Von Hand aktualisiert)

| Datei | Pflege | Wer |
|-------|--------|-----|
| `index.md` | Status, GO/NO-GO | @assistant |
| `phases.md` | Phasenplan | @assistant |
| `roadmap.md` | Nächste Aufgaben | @assistant |
| `blockers.md` | Blocker-Liste | @assistant |
| `architecture/*.md` | ADRs | @assistant + @user |
| `runbooks/*.md` | Prozeduren | @assistant |
| `strategy-lab/*.md` | Strategie-Doku | @user |
| `mkdocs.yml` | Navigation | @assistant |

### Automatische Inhalte (Kopiert/generiert)

| Datei | Quelle | Methode |
|-------|--------|---------|
| `milestones/m5.md` | `../M5_SUMMARY.md` | Copy/Symlink |
| `milestones/m6.md` | `../M6_SUMMARY_EXEC.md` | Copy/Symlink |
| `architecture/adr-001.md` | `../ADR-001*.md` | Copy/Symlink |
| `architecture/adr-002.md` | `../ADR-002*.md` | Copy/Symlink |
| `generated/timestamp.md` | Build-Zeit | CI Script |

### Semi-Automatisch (Manuell gestartet)

| Datei | Quelle | Methode |
|-------|--------|---------|
| `test-reports.md` | Test-Output | Script |
| `changelog.md` | Git commits | Manuell |

## Update-Workflow

### Täglich (Manuell)

```bash
# In docs/site/

# 1. Status aktualisieren
vim index.md          # GO/NO-GO, Blocker, Nächste Aufgaben

# 2. Phasen-Status aktualisieren
vim phases.md         # Phase X In Progress

# 3. Roadmap aktualisieren
vim roadmap.md        # Erledigte Aufgaben

# 4. Blocker aktualisieren
vim blockers.md       # Neue/Gelöste Blocker

# 5. Commit
 git add .
 git commit -m "docs: Update Mission Control $(date +%Y%m%d)"
 git push
```

### Bei Milestones (Semi-Automatisch)

```bash
# 1. Update-Script laufen lassen
./update-site.sh

# 2. Review
mkdocs serve

# 3. Deploy
mkdocs gh-deploy
```

### CI/CD (Voll-Automatisch)

```
Git Push → GitHub Action → Build → Deploy
```

## Navigation (mkdocs.yml)

```yaml
nav:
  - Mission Control: index.md
  - Phases: phases.md
  - Roadmap: roadmap.md
  - Blockers: blockers.md
  - Architecture:
    - architecture/index.md
    - architecture/adr-001.md
    - architecture/adr-002.md
  - Runbooks:
    - runbooks/index.md
    - runbooks/incident.md
    - runbooks/rollback.md
  - Strategy Lab:
    - strategy-lab/index.md
    - strategy-lab/scorecards.md
  - Test Reports: test-reports.md
  - Economics: economics.md
  - Changelog: changelog.md
```

## Lokale Entwicklung

```bash
cd docs/site
source venv/bin/activate
mkdocs serve

# http://127.0.0.1:8000
```

## Produktiv-URL

```
https://user.github.io/forward_v5
```

---

## Style Guide

### Status-Codes

| Code | Bedeutung | Farbe |
|------|-----------|-------|
| ✅ | Complete/Done | Grün |
| 🔄 | In Progress | Gelb |
| ⬜ | Pending | Grau |
| ⏳ | Waiting | Orange |
| ⛔ | Blocked | Rot |
| ⚠️ | Warning | Orange |
| ⭐ | Important | Gelb |

### Blocker

```markdown
| ID | Blocker | Status | Owner |
|----|---------|--------|-------|
| B1 | Titel | 🔄 | @name |
```

### Phasen

```markdown
| Phase | Name | Status | Blocker |
|-------|------|--------|---------|
| 1 | Titel | 🔄 | Phase 0 |
```

---

Last updated: 2026-03-06 12:41 UTC
