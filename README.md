# TikTok Shop Profit Agent UK

## Android test build

The [Android Debug APK workflow](.github/workflows/android.yml) builds the existing React/Vite UI in Capacitor 8 and uploads **`tiktok-shop-profit-agent-android-debug`**, containing **`app-debug.apk`**. Package: `com.tiktokshopprofitagent.app`; `versionCode=1`, `versionName=1.0`. This is a debug-signed test build, not a Play Store release. CI checks the APK ZIP, bundled HTML, package identity and internet-only permission; physical installation must be checked on an Android device. To install: open the latest completed/successful Android Debug APK run on `main`, download the named artifact ZIP, extract `app-debug.apk`, and open the APK on your phone. Android may ask permission to install from the app you used to open it. A debug build from a different signing key may require uninstalling an older one first.

**Current APK without a public backend:** the first screen says `BACKEND UNAVAILABLE`, shows `Continue with TikTok` disabled, and cannot sign in. That is the honest install/UI test state; do not type a TikTok password into this app. To produce a connected build later, deploy the backend and frontend at one HTTPS origin, then set the non-secret repository variable `ANDROID_APP_ORIGIN` to that exact origin and rebuild. Do not set it to `localhost`. The WebView will load that HTTPS origin and use same-origin operator cookies. The app launches official TikTok authorization in an external Android browser; the registered TikTok OAuth redirect stays at the HTTPS backend callback. The backend returns to the APK using `com.tiktokshopprofitagent.app://oauth-return`, carrying **no code or tokens**. A random one-time state links the Android start to the server session; the browser callback does not require the browser to share the WebView's cookie.

Backend deployment needs PostgreSQL, the variables in [`server/.env.example`](server/.env.example), an HTTPS reverse proxy, and the registered Login Kit callback `https://YOUR-DOMAIN/v1/tiktok/callback`. The [Dockerfile](Dockerfile) builds frontend and backend together, runs Alembic before serving, and disables HTTP access logs so callback `state` and authorization code do not appear there. Redact the callback query at the TLS proxy too. No TikTok app credentials, domain or hosting are provided by the repository. The manual Shop/Affiliate evidence path remains operator asserted; the existing experiment workspace still contains localStorage assertions and is not production-grade business authority. The APK does not prove a connected account or first £.

Mobile-first, single-operator affiliate experiment prototype. The guiding loop is **discover → test → observe → reconcile → learn**. The decision and money models are implemented in TypeScript; external publication, account setup, payout, and withdrawal remain manual.

## Actual state

- React 19 / Vite frontend: UK setup, real product and evidence intake, opportunity scoring, frozen EXP-001, ProductTruth, creative pack and human approval, manual launch packet, publication evidence, commerce ledger, cost and net settlement views.
- Product, evidence, approval, launch and commerce records reside in **browser localStorage**. They are local operator assertions, not server-verified business truth. A second device cannot recover them. Local storage can be edited by the browser owner. Do not use this prototype as an authorization service or as an audited accounting ledger.
- A separate Python 3.12 FastAPI observation API now has SQLAlchemy 2 models, Alembic migrations and PostgreSQL 16 CI coverage. Its `/v1/experiments`, `/v1/events`, `/v1/costs`, `/v1/cost-adjustments` and `/v1/experiments/{id}/economics` endpoints require a single operator bearer secret. IDs, publication order, conflicting retries and Decimal accounting are checked on the server. Later observed costs append with a distinct ID and can revoke a prior local First Pound candidate. It **does not yet drive the frontend**, validate ProductTruth or capital authority server side, or verify external TikTok data. It is not deployed. All API evidence is explicitly marked `MANUAL_ASSERTION`; `commercial_proof` stays `NOT_PROVEN`.
- App entry now checks a server-side operator session, then a TikTok Login Kit web connection. Without either, Home and Money are not mounted. The OAuth callback verifies a short-lived, one-use state bound to the operator session. Tokens are encrypted in PostgreSQL and are never returned to the browser. Refresh rotates stored refresh tokens; disconnect removes local authority before calling TikTok's official revoke endpoint. If revoke fails, authority stays disabled and revocation needs retry.
- TikTok Login Kit authenticates **identity only**. Shop, Affiliate, UK market, publishing, orders, commission and settlement API capabilities remain UNKNOWN without separate provider evidence. An operator can record UK and Affiliate evidence references as **manual assertions** valid for 30 days. This unlocks a labelled manual workspace, not API access or server-verified commercial authority. Server-side observation writes require both an active TikTok identity and current manual references; historical economic reads survive disconnect. The existing workspace remains localStorage backed, and its readiness logic is not yet a server authority decision.
- A missing amount or evidence is UNKNOWN. Invalid stored commerce records fail closed instead of becoming an empty ledger. Exact retries are idempotent; conflicting reuse of an external event ID is rejected. A refund with an observed amount changes net settlement. The home and Money pages use the same net reward and observed cost calculation.
- Invalid local learning records also fail closed, and a reused learning ID with different economics is rejected. If local truth cannot be read, the mobile UI blocks actions and shows an evidence recovery message instead of displaying a fresh-looking empty account.
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
export OPERATOR_LOGIN_SECRET='another-independent-random-secret-of-at-least-32-characters'
# Set the following only after registering Login Kit for Web with TikTok:
export TIKTOK_CLIENT_KEY='your-client-key'
export TIKTOK_CLIENT_SECRET='your-server-only-client-secret'
export TIKTOK_REDIRECT_URI='https://your-domain.example/v1/tiktok/callback'
export TIKTOK_TOKEN_ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest -q server/tests
.venv/bin/uvicorn server.api:create_app --factory
```

The browser and `/v1` API must be served from the same HTTPS origin in deployment. In development, Vite proxies `/v1` to the backend on port 8000; the official web callback must use a registered static HTTPS URL without query parameters. The operator login uses an HttpOnly Secure cookie and a separate CSRF token. Do not expose the bearer API secret, developer app secret, or encryption key to Vite. Keep the encryption key stable across restarts and protect database backups. Set up a TikTok developer app, add Login Kit for Web, register the exact callback URI, enable `user.info.basic`, and supply its real credentials. Without these settings, Continue with TikTok is disabled. GitHub Actions uses a fake provider and never connects a real TikTok account.

Official documentation: [Login Kit web](https://developers.tiktok.com/docs/en/login-kit-web), [token exchange, refresh and revoke](https://developers.tiktok.com/docs/en/oauth-user-access-token-management), [user identity](https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info), [Direct Post approval](https://developers.tiktok.com/docs/en/content-posting-api-get-started). Web uses server-side `state`; TikTok's PKCE requirement in this documentation applies to the mobile and desktop flows. A successful Login Kit authorization does not imply a Shop Partner, Affiliate or settlement authorization.

The backend CI runs the migration and API tests against PostgreSQL 16. SQLite is used only for the fast local migration and API tests; its pass alone is not PostgreSQL proof. API money responses use decimal strings, not JSON floats. Secrets stay in environment variables and `server/.env.example` is only a template.

Current official provider access findings are recorded in [TikTok provider boundary](docs/provider-capabilities.md). No account-specific affiliate API scopes or settlement feed have been demonstrated.

## Manual operation and outstanding gates

Enter an observed UK product and evidence, establish operator-entered account and capital checks, freeze EXP-001, record ProductTruth claims, validate and approve a creative pack, then prepare a manual launch packet. Publication requires a real video ID and evidence reference entered by the operator. Record order, delivery, commission settlement, refund and observed cost independently. Orders and expected commissions are not realized contribution; settled commission net of refunds less observed experiment cost is the local economic measure. Bank arrival remains UNKNOWN until separately checked.

Before production use, move product/creative approval and capital authority to the server, bind the manual workspace to server-side economic and connection evidence, verify actual Shop Partner and Affiliate capabilities for the approved account, link orders to settlements and refunds by a real external identity, deploy HTTPS and run integrated golden and adversarial paths. A live TikTok login and commercial settlement have not been performed. Engineering tests cannot prove a real connected account or first £.
