---
summary: "Workspace template for TOOLS.md"
read_when:
  - Bootstrapping a workspace manually
---

# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

## GitHub Access (Forward V5)

**✅ ACCESS CONFIRMED:** Fine-grained Personal Access Token (PAT) gespeichert

**Repository:** `https://github.com/dpxyz/pecz`  
**Deploy-Ziel:** Cloudflare Pages → `https://pecz.pages.dev`  
**Credentials:** In `~/.netrc` gespeichert

### Push-Command
```bash
cd /data/.openclaw/workspace/forward_v5/forward_v5
git add -A
git commit -m "Update: beschreibung"
git push origin main
# Auto-deploy zu Cloudflare Pages
```

---

## ⚠️ SECRETS SAFETY CHECKLIST

**Diese Checks MÜSSEN vor jedem Commit durchgeführt werden:**

### Pre-Commit Prüfung (MANDATORY)

- [ ] **Keine `.env` Dateien committed**
  ```bash
  git status | grep -E "\.env|token|secret|key|password|pat_"
  ```

- [ ] **Keine Tokens in Markdown/JS/Config**
  ```bash
  # Prüfe auf gängige Token-Muster
  git diff --cached | grep -E "(ghp_|github_pat_|gho_|gpr_)"
  git diff --cached | grep -E "(sk-|pk-)[a-zA-Z0-9]{20,}"  # OpenAI/API Keys
  git diff --cached | grep -E "[a-z0-9]{32,}"  # API Keys
  ```

- [ ] **Keine Privaten Keys**
  ```bash
  git diff --cached | grep -E "(BEGIN|END) (RSA|DSA|EC|OPENSSH) PRIVATE KEY"
  ```

- [ ] **Keine Passwörter**
  ```bash
  git diff --cached | grep -iE "password|passwd|pwd.*="
  ```

- [ ] **~/.netrc hat korrekte Rechte (600)**
  ```bash
  ls -la ~/.netrc  # Sollte zeigen: -rw-------
  ```

### Rote Linien (NIEMALS)

| Was | Warum |
|-----|-------|
| `~/.netrc` | Niemals im Git |
| `.env` Dateien | Niemals committed |
| Token direkt in URL | Niemals in Code |
| SSH Private Keys | Niemals committed |
| API Keys | Niemals in Dokumentation |

### Wenn Secret geleaked wurde

1. **SOFORT** Token auf GitHub revoke
2. **SOFORT** Secret aus Datei entfernen
3. **SOFORT** `git commit --amend` oder `git reset`
4. **SOFORT** `git push --force-with-lease`
5. Benutzer informieren

### Safe Patterns (Beispiele)

```bash
# ✅ SAFE: Environment Variable nutzen
REPO_URL="https://${GITHUB_TOKEN}@github.com/user/repo.git"

# ✅ SAFE: Config mit Platzhaltern
discord_webhook: "${DISCORD_WEBHOOK_URL}"  # Wird zur Laufzeit ersetzt

# ❌ UNSAFE: Hardcoded Token
discord_webhook: "https://discord.com/api/webhooks/12345/ABC-DEF-GHI"

# ❌ UNSAFE: Token in URL
git remote add origin https://ghp_XXX@github.com/user/repo.git
```

---

## 🚀 Mission Control Deployment (WICHTIG!)

**Repo:** `https://github.com/dpxyz/pecz`  
**Deploy:** Cloudflare Pages auto-build  
**URL:** `https://pecz.pages.dev`  
**Build-Verzeichnis:** `forward_v5/docs/site/` (NICHT `docs/site/`!)

### ⚠️ KRITISCHE WORKAROUNDS

#### 1. Doppelte Verzeichnisstruktur
Das Repo hat **ZWEI** `site/` Verzeichnisse:

```
pecz/
├── docs/site/              # ← Das wird NICHT von Cloudflare gebaut
│   ├── index.md
│   ├── phases.md
│   └── ...
│
└── forward_v5/docs/site/   # ← DAS wird von Cloudflare gebaut!
    ├── docs/
    │   ├── index.md      # ← Startseite
    │   ├── phases.md     # ← Phasenplan
    │   ├── blockers.md   # ← Blocker
    │   ├── roadmap.md    # ← Roadmap
    │   └── architecture/
    │       ├── adr-001.md
    │       ├── adr-002.md
    │       ├── adr-003.md  # ← Neue ADRs hier!
    │       └── adr-004.md
    ├── mkdocs.yml         # ← Navigation MUSS hier aktualisiert werden
    └── requirements.txt
```

**WICHTIG:** Änderungen müssen in `forward_v5/docs/site/` landen!

---

#### 2. Sync-Workflow (bei jeder Änderung)

```bash
# 1. ADRs im Root aktualisieren (Quelle)
# docs/ADR-003-state-model.md
# docs/ADR-004-risk-controls.md

# 2. In Mission Control-Struktur kopieren
cp docs/ADR-003-state-model.md forward_v5/docs/site/docs/architecture/adr-003.md
cp docs/ADR-004-risk-controls.md forward_v5/docs/site/docs/architecture/adr-004.md

# 3. Startseite + Inhalte kopieren
cp docs/site/index.md forward_v5/docs/site/docs/index.md
cp docs/site/phases.md forward_v5/docs/site/docs/phases.md
cp docs/site/roadmap.md forward_v5/docs/site/docs/roadmap.md
cp docs/site/blockers.md forward_v5/docs/site/docs/blockers.md

# 4. MkDocs Navigation prüfen/update
# forward_v5/docs/site/mkdocs.yml → nav: muss alle ADRs enthalten!

# 5. Commit + Push
git add forward_v5/docs/site/
git commit -m "Update: Beschreibung"
git push origin main

# 6. Cloudflare baut automatisch (2-3 Min Wartezeit)
```

---

#### 3. Symlinks funktionieren NICHT

**❌ Funktioniert nicht in Cloudflare Pages:**
```bash
ln -s ../../ADR-001.md architecture/adr-001.md  # ← Funktioniert nicht!
```

**✅ Muss echte Kopie sein:**
```bash
cp docs/ADR-001-target-architecture.md forward_v5/docs/site/docs/architecture/adr-001.md
```

---

#### 4. MkDocs Navigation immer aktualisieren

Wenn neue ADRs hinzugefügt werden, MUSS `mkdocs.yml` aktualisiert werden:

```yaml
nav:
  - Mission Control: index.md
  - Phases: phases.md
  - Architecture:
    - Overview: architecture/index.md
    - ADR-001: architecture/adr-001.md  # ← Muss hier stehen!
    - ADR-002: architecture/adr-002.md  # ← Muss hier stehen!
    - ADR-003: architecture/adr-003.md  # ← NEU: Muss hier stehen!
    - ADR-004: architecture/adr-004.md  # ← NEU: Muss hier stehen!
  - Runbooks:
    ...
```

**Dateipfad:** `forward_v5/docs/site/mkdocs.yml`

---

#### 5. Checkliste vor jedem Mission Control Update

**Muss immer geprüft werden:**

- [ ] Änderungen in `forward_v5/docs/site/docs/` (nicht nur `docs/`)
- [ ] ADRs als echte Dateien (keine Symlinks)
- [ ] MkDocs Navigation enthält alle neue ADRs
- [ ] Alle 4 Dateien sync'd: `index.md`, `phases.md`, `roadmap.md`, `blockers.md`
- [ ] Keine Secrets/Tokens im Commit
- [ ] Nach Push: 2-3 Min Wartezeit für Cloudflare Build
- [ ] Prüfe: https://pecz.pages.dev (Hard Reload mit Ctrl+Shift+R)

---

#### 6. Troubleshooting

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Seite zeigt alten Stand | Browser Cache | `Ctrl+Shift+R` (Hard Reload) |
| Änderungen nicht live | Falsches Verzeichnis | Muss in `forward_v5/` sein |
| ADRs nicht in Navigation | mkdocs.yml vergessen | Navigation aktualisieren |
| 404 auf neue ADRs | Symlinks statt echte Dateien | `cp` statt `ln -s` nutzen |
| Deploy failed | Cloudflare Build Error | Dashboard prüfen → Pages → pecz → Deployments |

---

#### 7. Wichtige URLs

| URL | Zweck |
|-----|-------|
| https://pecz.pages.dev | Mission Control Startseite |
| https://pecz.pages.dev/phases | Phasenplan |
| https://pecz.pages.dev/architecture/adr-001/ | ADR-001 |
| https://pecz.pages.dev/architecture/adr-002/ | ADR-002 |
| https://pecz.pages.dev/architecture/adr-003/ | ADR-003 (State Model) |
| https://pecz.pages.dev/architecture/adr-004/ | ADR-004 (Risk Controls) |
| https://pecz.pages.dev/blockers | Offene Blocker |
| https://pecz.pages.dev/roadmap | Aktuelle Aufgaben |

---

## Memory: GitHub Push Workflow

**Automatischer Workflow bei Code-Änderungen:**

1. **Änderungen vornehmen** → Editieren
2. **Doppelte Struktur sync** → In `forward_v5/` kopieren
3. **Secrets Check** → `git diff --cached | grep token`
4. **MkDocs Navigation prüfen** → Neue ADRs hinzugefügt?
5. **Commit mit Beschreibung**
6. **Push** → GitHub → Cloudflare Pages
7. **2-3 Min warten** → Build + Deploy
8. **Verifizieren** → https://pecz.pages.dev

---

Add whatever helps you do your job. This is your cheat sheet.
**Remember: Secrets gehören NIE ins Git!** 🔒
