# AgentTikTok Shop

## Brasil: APK de preparação para criador (versão 1.2)

O APK agora usa o nome **AgentTikTok Shop**, interface de entrada em português e uma área Brasil para criar um vídeo MP4 vertical de 12 segundos a partir de foto e frases fornecidas pelo operador. A foto deve pertencer ao criador ou ter licença de uso. O arquivo pode ser revisado, baixado ou compartilhado; envio para TikTok continua manual. O vídeo não adiciona seguidores automaticamente. O endpoint `/v1/creator-video` exige sessão de operador, limita a imagem a 3 MB, nunca recebe senha TikTok e apaga os arquivos temporários após o download.

**Corte de segurança:** o antigo livro comercial ainda contém UK/GBP. O APK Brasil não monta as antigas telas de dinheiro nem de operação UK. Não traduzimos cifras históricas em libras como reais. Uma migração de dados com moeda e mercado por registro, testes PostgreSQL e confirmação da conta brasileira devem preceder ativar comércio no Brasil. OAuth de identidade não fornece aprovação da Shop nem permissão para postar. Comentários automáticos de captação em vídeos alheios não são implementados. O titular deve fazer a verificação do próprio perfil e controlar a publicação e o saque.

O nome solicitado contém uma marca do TikTok; a publicação pública e a inscrição como aplicativo de desenvolvedor dependem de validação pelas regras de marca e aprovação do TikTok. Esta compilação é para teste interno.

O projeto permanece no mesmo repositório, backend HTTPS e `applicationId`. O serviço existente de hospedagem não deve ser renomeado só por esta troca de rótulo: isso poderia criar outro serviço cobrado. O fluxo UK/GBP abaixo descreve o backend histórico e **não** deve ser usado para registrar receitas do Brasil.

## Android test build

The [Android Debug APK workflow](.github/workflows/android.yml) builds the existing React/Vite UI in Capacitor 8 and uploads **`agenttiktok-shop-br-android-debug`**, containing **`app-debug.apk`**. Package: `com.tiktokshopprofitagent.app`; current source version `versionCode=4`, `versionName=1.3`. This is a debug-signed test build, not a Play Store release. CI checks the APK ZIP, bundled HTML, package identity and internet-only permission; physical installation must be checked on an Android device. To install: open the latest completed/successful Android Debug APK run on `main`, download the named artifact ZIP, extract `app-debug.apk`, and open the APK on your phone. Android may ask permission to install from the app you used to open it. A debug build from a different signing key may require uninstalling an older one first.

**Private Android TikTok login architecture:** the APK starts TikTok Login Kit Web in an external Chrome Custom Tab. The app creates a server-side one-time OAuth intent tied to its operator session and CSRF token; TikTok returns to the registered Railway HTTPS callback; the backend consumes the state, exchanges the code, verifies `user.info.basic`, and stores encrypted tokens. The callback then displays a success page in the browser; closing the Custom Tab returns to the APK, whose Browser completion event refreshes identity. The client secret and tokens never enter the APK or a return link. The HTTPS callback is intentionally not an Android App Link, so Chrome delivers the response to Railway for server-side exchange. Web Login Kit uses server-side state protections; PKCE remains in the retained OpenSDK implementation for its separate mobile flow and is not part of this Web authorization. The OpenSDK source and Android Keystore code remain in the APK for now, but the Web path is the active path pending a real-device authorization test. Sandbox Web settings and the owner Target User are configured; the TikTok authorization and physical APK test are still pending.

The current Android workflow makes a **debug-signed test APK**, not a Play Store release. The repository contains no release keystore or release signing configuration. A debug fingerprint must never be represented as the production fingerprint; for Google Play distribution, register the Play App Signing certificate fingerprints.

Backend deployment needs PostgreSQL, the variables in [`server/.env.example`](server/.env.example), an HTTPS reverse proxy, and the registered Login Kit callback `https://YOUR-DOMAIN/v1/tiktok/callback`. The [Dockerfile](Dockerfile) builds frontend and backend together, runs Alembic before serving, and disables HTTP access logs so callback `state` and authorization code do not appear there. Redact the callback query at the TLS proxy too. No TikTok app credentials, domain or hosting are provided by the repository. The manual Shop/Affiliate evidence path remains operator asserted. After login the mobile workspace reads the PostgreSQL portfolio and offers a manual Operate path guarded by server-owned capital, product evidence, ProductTruth, creative approval and launch intent. The earlier browser-only workflow is no longer mounted. The APK does not prove a connected account or first £.

Mobile-first, single-operator affiliate experiment prototype. The guiding loop is **discover → test → observe → reconcile → learn**. The decision and money models are implemented in TypeScript; external publication, account setup, payout, and withdrawal remain manual.

## Actual state

- The mounted mobile app handles operator login, official TikTok Login Kit identity, capability status, and a server-backed Home, Experiments, Money and manual Operate workflow. Its earlier `localStorage` domain prototype remains in source for historical tests but cannot authorize actions in the mounted app.
- Server-owned PostgreSQL records cover capital authority, UK product/opportunity evidence, factual ProductTruth claims, immutable creative hashes, human approval snapshots, manual launch intents, publication and commerce observations, costs, refunds and economic learning. Launch intent explicitly has `externalExecutionAllowed=false`. The operator must submit evidence references; software does not verify that the external observations happened.
- Order observations link to a publication, delivery and settlement to an order, and refund to a settlement using an explicit external parent ID. A different payload under an existing identity conflicts. Existing unbound historical records remain auditable, but cannot satisfy the new linked First Pound candidate.
- Server capital checks compare required capital and maximum loss with operator-approved decimal limits; unsupported/UNKNOWN/BLOCKED claims cannot enter an approved creative. Creative content and the ProductTruth snapshot are hashed; later changes invalidate unpublished launch authority.
- The `/ready` endpoint checks the database and current Alembic revision plus operator login configuration. Backend CI migrates PostgreSQL 16 and runs the full API and fake-provider E2E. `/health` only indicates that the process responds.
- TikTok Login Kit grants **identity only**. Shop, Affiliate, posting, orders, commission and settlement remain independently UNKNOWN without actual capability evidence. Manual UK/Affiliate references expire in 30 days and are labelled operator assertions. Tokens are encrypted server-side; refresh and disconnect fail closed. No real Login Kit authorization has completed.
- Money uses Decimal/NUMERIC. Gross settlement minus linked refunds minus observed costs determines the manual contribution projection. The First Pound *candidate* can be revoked after a refund or added cost, including after backend restart. `commercialProof` remains `NOT_PROVEN` because manual observations cannot certify real TikTok commerce.
- Learning stores the economic snapshot and marks it stale when a refund or cost changes facts. Repeatability and scale are not operationally proven; automatic publishing, withdrawal and scale are absent.

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

The browser and `/v1` API must be served from the same HTTPS origin in deployment. In development, Vite proxies `/v1` to the backend on port 8000; the official web callback must use a registered static HTTPS URL without query parameters. The operator login uses HttpOnly Secure cookies and a separate CSRF token. “Keep me signed in” is enabled by default in the private app and retains the server-side operator session for 30 days; clearing app data or unchecking it retains the 12-hour session. Do not expose the bearer API secret, developer app secret, or encryption key to Vite. Keep the encryption key stable across restarts and protect database backups. Set up a TikTok developer app, add Login Kit for Web, register the exact callback URI, enable `user.info.basic`, and supply its real credentials. Without these settings, Continue with TikTok is disabled. GitHub Actions uses a fake provider and never connects a real TikTok account.

Official documentation: [Login Kit web](https://developers.tiktok.com/docs/en/login-kit-web), [token exchange, refresh and revoke](https://developers.tiktok.com/docs/en/oauth-user-access-token-management), [user identity](https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info), [Direct Post approval](https://developers.tiktok.com/docs/en/content-posting-api-get-started). Web uses server-side `state`; TikTok's PKCE requirement in this documentation applies to the mobile and desktop flows. A successful Login Kit authorization does not imply a Shop Partner, Affiliate or settlement authorization.

The backend CI runs the migration and API tests against PostgreSQL 16. SQLite is used only for the fast local migration and API tests; its pass alone is not PostgreSQL proof. API money responses use decimal strings, not JSON floats. Secrets stay in environment variables and `server/.env.example` is only a template.

Current official provider access findings are recorded in [TikTok provider boundary](docs/provider-capabilities.md). No account-specific affiliate API scopes or settlement feed have been demonstrated.

## Production deployment and external setup

[`render.yaml`](render.yaml) is a minimal Blueprint for one Render Docker service and paid PostgreSQL 16 in Frankfurt. Render provides HTTPS and private database networking; external database ingress is disabled. The Blueprint generates the API token, operator login key and token encryption key in Render. The [Dockerfile](Dockerfile) builds frontend and backend at one origin and runs `alembic upgrade head` before accepting traffic. **No Render resources have been created or paid for by this repository.** Current Render plans and costs must be reviewed in Render before the owner creates resources; avoid an expiring free database for durable commerce truth.

Once the owner creates and links the Blueprint in their Render account, verify the exact assigned HTTPS service origin and its `/ready` response. Retrieve the generated `OPERATOR_LOGIN_SECRET` securely within Render to sign in; do not paste secrets into chat. Configure the GitHub repository variable `ANDROID_APP_ORIGIN` to **that verified exact HTTPS origin**, then build the next Android APK with `versionCode=3`. The existing `versionCode=1` artifact has no origin, remains installable in offline demo mode and cannot authenticate. Android must not assume a guessed URL or `localhost`.

For TikTok identity, create/register an app in [TikTok for Developers](https://developers.tiktok.com/), add [Login Kit for Web](https://developers.tiktok.com/docs/en/login-kit-web), register the **exact** redirect `https://YOUR-ACTUAL-RENDER-HOST/v1/tiktok/callback`, and request `user.info.basic`. Set `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` and `TIKTOK_REDIRECT_URI` directly in Render environment settings, never in GitHub or Android. Re-deploy after adding them; `/ready` reports `tiktokAuthorizationConfigured`. OAuth goes to TikTok's official browser page, the backend exchanges the code, and the Android return link carries no token or code. TikTok Shop/Affiliate and commerce access need separate real evidence; manual verified workflows are available without those APIs after a real identity connects.

Manual commerce path in Operate: record a real UK listing and evidence, operator-approved capital limits and opportunity, freeze a uniquely identified experiment, record claim provenance and creative content, obtain human approval, create an immutable manual launch intent, publish outside the app, then observe the real video/order/delivery/settlement/refund/cost references. The server validates trace and recomputes economics. A synthetic E2E is engineering proof only. **No real TikTok login, real settlement, physical APK installation or bank payout has been observed here.**
