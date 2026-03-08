# Forward V5 Mission Control

Statische Dokumentations-Website für Forward V5 Trading System.

## Setup

```bash
cd forward_v5/docs/site
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdocs serve
# → http://127.0.0.1:8000
```

## Deploy (Cloudflare Pages)

### Build Configuration

| Setting | Value |
|---------|-------|
| **Build command** | `cd forward_v5/docs/site && pip install -r requirements.txt && mkdocs build` |
| **Build output directory** | `forward_v5/docs/site/site` |
| **Root directory** | `/` |
| **Environment** | `PYTHON_VERSION=3.11` |

### Deploy URL

```
https://pecz.pages.dev
```

## Files

```
.
├── mkdocs.yml              # Configuration
├── requirements.txt        # Dependencies
├── index.md                # Mission Control
├── phases.md               # Phase plan 0-9
├── roadmap.md              # Current tasks
├── blockers.md             # Open blockers
├── test-reports.md         # Test results
├── economics.md            # Economics
├── changelog.md            # Changes
├── architecture/
│   └── index.md            # ADR overview
├── runbooks/
│   └── index.md            # Procedures
├── strategy-lab/
│   └── index.md            # Strategy Lab
└── .cloudflare/
    └── DEPLOY_CFPAGES.md   # Deploy docs
```

## Update

1. Edit Markdown files
2. `git add .`
3. `git commit -m "Update docs"`
4. `git push`
5. Auto-deploy via Cloudflare Pages

---

*Forward V5 Mission Control*
