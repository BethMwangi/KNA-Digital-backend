# KNA Digital Archive — Backend

Django REST Framework API for the Enterprise Digital Archive Commerce Platform
(Phase One). PostgreSQL + JWT + RBAC + OpenAPI docs.

> Note: this implementation supersedes SDD ADR-002 (FastAPI) — the stack
> decision is Django REST Framework. All other ADRs and the §16 API contract
> are unchanged.

## Structure

```
kna-digital-archive-backend/
├── .github/workflows/       # CI: ruff, black, migration check, pytest
├── config/                  # Django project
│   ├── settings/            # base.py / development.py / production.py
│   ├── urls.py              # /api/v1 mounting + /docs + /redoc
│   └── wsgi.py, asgi.py
├── core/                    # shared kernel
│   ├── models.py            # BaseModel: UUID pk, timestamps, soft delete (SDD §15.2)
│   └── exceptions.py        # standard error envelope (SDD §16.19)
├── apps/
│   ├── accounts/            # ✅ auth, users, roles, audit logs (this delivery)
│   ├── assets/              # next: digital_assets, variants, categories,
│   │                        #        collections, tags, licenses, pricing
│   ├── commerce/            # next: carts, orders
│   ├── payments/            # next: eCitizen / M-Pesa adapters
│   ├── downloads/           # next: signed URLs, download limits
│   └── administration/      # next: dashboard, reports, settings
├── requirements/            # base.txt / development.txt / production.txt
├── tests/                   # cross-app integration tests
├── scripts/                 # ops & data scripts
├── docs/                    # SDD + ADR updates
├── media/                   # local dev only (production = Supabase/MinIO, ADR-004)
├── docker-compose.yml       # local Postgres + backend
├── Dockerfile
└── manage.py
```

## Quick start

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/development.txt

docker compose up db -d          # or point DATABASE_URL at Supabase
python manage.py makemigrations accounts
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Swagger UI: http://localhost:8000/docs/
- ReDoc:      http://localhost:8000/redoc/
- Django admin: http://localhost:8000/admin/

## Auth API (implemented, SDD §16.5–16.6, §16.15)

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Customer self-registration |
| POST | `/api/v1/auth/login` | JWT access + refresh + profile |
| POST | `/api/v1/auth/refresh` | Rotate tokens |
| POST | `/api/v1/auth/logout` | Blacklist refresh token |
| POST | `/api/v1/auth/forgot-password` | Send reset email |
| POST | `/api/v1/auth/reset-password` | Confirm reset |
| POST | `/api/v1/auth/verify-email` | Verify email |
| GET/PUT | `/api/v1/users/me` | Profile |
| PUT | `/api/v1/users/password` | Change password |
| CRUD | `/api/v1/admin/users/` | Staff & role management (Admin+) |

## Roles & RBAC (SDD §17)

Guest → Customer → Content Editor → Administrator → Super Administrator.
Enforce with `apps.accounts.permissions`:

```python
from apps.accounts.permissions import IsContentEditorOrAbove

class AssetAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsContentEditorOrAbove]
```

## Testing

```bash
pytest
```

## Git workflow (SDD §24)

`main` (production) ← `develop` ← `feature/*`; hotfixes via `hotfix/*`.
All changes via reviewed PRs; CI must be green.
