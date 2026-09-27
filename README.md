# TikTok Shop Profit Agent UK

Mobile-first, single-operator affiliate experiment prototype. The guiding loop is **discover → test → observe → reconcile → learn**. The decision and money models are implemented in TypeScript; external publication, account setup, payout, and withdrawal remain manual.

## Actual state

- React 19 / Vite frontend: UK setup, real product and evidence intake, opportunity scoring, frozen EXP-001, ProductTruth, creative pack and human approval, manual launch packet, publication evidence, commerce ledger, cost and net settlement views.
- Product, evidence, approval, launch and commerce records reside in **browser localStorage**. They are local operator assertions, not server-verified business truth. A second device cannot recover them. Local storage can be edited by the browser owner. Do not use this prototype as an authorization service or as an audited accounting ledger.
- A separate Python 3.12 FastAPI observation API now has SQLAlchemy 2 models, Alembic migrations and PostgreSQL 16 CI coverage. Its `/v1/experiments`, `/v1/events`, `/v1/costs`, `/v1/cost-adjustments` and `/v1/experiments/{id}/economics` endpoints require a single operator bearer secret. IDs, publication order, conflicting retries and Decimal accounting are checked on the server. Later observed costs append with a distinct ID and can revoke a prior local First Pound candidate. It **does not yet drive the frontend**, validate ProductTruth or capital authority server side, or verify external TikTok data. It is not deployed. All API evidence is explicitly marked `MANUAL_ASSERTION`; `commercial_proof` stays `NOT_PROVEN`.
- A missing amount or evidence is UNKNOWN. Invalid stored commerce records fail closed instead of becoming an empty ledger. Exact retries are idempotent; conflicting reuse of an external event ID is rejected. A refund with an observed amount changes net settlement. The home and Money pages use the same net reward and observed cost calculation.
- First Pound is a **local calculation only**. It requires a matching frozen decision, creative approval, launch packet, publication record, observed cost, settlement and provenance. It recomputes from facts on every read, so a later refund revokes the local conclusion. It is not a claim that the first real £ has been proved commercially. Earlier frozen records without a decision snapshot cannot qualify.
- Repeatability requires distinct economically mature experiments in the domain model. EXP-002 is not yet an operator workflow. A scale packet represents an approved **manual intent** and never grants external execution.

## Run and test

Node 22+:

```bash
npm ci
npm run typecheck
npm test
npm run build
npm run dev
```

Frontend CI runs typecheck, Vitest and build with the committed dependency lock. Frontend tests use synthetic records and do not constitute TikTok integration tests.

Backend local development (use a PostgreSQL database you control and a random secret):

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
export DATABASE_URL='postgresql+psycopg://operator:password@localhost:5432/tiktok_profit'
export OPERATOR_API_TOKEN='your-own-random-secret-of-at-least-32-characters'
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest -q server/tests
.venv/bin/uvicorn server.api:create_app --factory
```

The backend CI runs the migration and API tests against PostgreSQL 16. SQLite is used only for the fast local migration and API tests; its pass alone is not PostgreSQL proof. API money responses use decimal strings, not JSON floats. Secrets stay in environment variables and `server/.env.example` is only a template.

Current official provider access findings are recorded in [TikTok provider boundary](docs/provider-capabilities.md). No account-specific affiliate API scopes or settlement feed have been demonstrated.

## Manual operation and outstanding gates

Enter an observed UK product and evidence, establish operator-entered account and capital checks, freeze EXP-001, record ProductTruth claims, validate and approve a creative pack, then prepare a manual launch packet. Publication requires a real video ID and evidence reference entered by the operator. Record order, delivery, commission settlement, refund and observed cost independently. Orders and expected commissions are not realized contribution; settled commission net of refunds less observed experiment cost is the local economic measure. Bank arrival remains UNKNOWN until separately checked.

Before production use, integrate the frontend with the backend, move product/creative approval and capital authority to the server, complete an external provider or genuinely verified manual evidence workflow, link orders to settlements and refunds by a real external identity, and run integrated golden and adversarial paths against a deployed backend. The backend prototype proves durable observation and arithmetic, not the full authority chain or commercial proof.
