# TikTok Shop Profit Agent UK

Mobile-first, single-operator affiliate experiment prototype. The guiding loop is **discover → test → observe → reconcile → learn**. The decision and money models are implemented in TypeScript; external publication, account setup, payout, and withdrawal remain manual.

## Actual state

- React 19 / Vite frontend: UK setup, real product and evidence intake, opportunity scoring, frozen EXP-001, ProductTruth, creative pack and human approval, manual launch packet, publication evidence, commerce ledger, cost and net settlement views.
- Product, evidence, approval, launch and commerce records reside in **browser localStorage**. They are local operator assertions, not server-verified business truth. A second device cannot recover them. Local storage can be edited by the browser owner. Do not use this prototype as an authorization service or as an audited accounting ledger.
- No deployed backend, PostgreSQL, Alembic migrations, operator authentication, live TikTok provider, or real TikTok settlement feed exists yet. The code cannot certify that any publication or commission occurred externally.
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

CI runs typecheck, Vitest and build with the committed dependency lock. Tests use synthetic records and do not constitute TikTok or PostgreSQL integration tests.

## Manual operation and outstanding gates

Enter an observed UK product and evidence, establish operator-entered account and capital checks, freeze EXP-001, record ProductTruth claims, validate and approve a creative pack, then prepare a manual launch packet. Publication requires a real video ID and evidence reference entered by the operator. Record order, delivery, commission settlement, refund and observed cost independently. Orders and expected commissions are not realized contribution; settled commission net of refunds less observed experiment cost is the local economic measure. Bank arrival remains UNKNOWN until separately checked.

Before production use, move authoritative facts and authority to an authenticated server, migrate them through PostgreSQL with verified migrations and Decimal/NUMERIC accounting, connect a permitted real observation provider or a controlled manual verification workflow, verify restart and conflicting retry behavior, and run integrated golden and adversarial paths against the deployed backend. These are open gates, not completed features.
