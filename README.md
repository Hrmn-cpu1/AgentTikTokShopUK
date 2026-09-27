# AgentTikTokShopUK 🇬🇧

Mobile-first TikTok Shop UK profit experimentation agent.

## Principle

**Automate the brain first. Automate the hands later.**

V0 loop:

`UK Product → Score → Experiment → Creative → Human Approval → Result → Settlement → Learning`

KYC, publishing, payout configuration and withdrawals remain manual in V0.

## Frontend

React 19 + TypeScript + Vite. Current UI:
- UK Setup / money-path eligibility
- Home
- UK Product Radar
- Opportunity detail
- Experiments
- Money / Decision-to-Money trace

Current product/opportunity figures are clearly labelled demo data. No TikTok integration is claimed yet.

## Local run

```bash
npm install
npm run dev
```

## Quality gate

```bash
npm run typecheck
npm run build
```

## Safety invariants

- LLM is not financial or policy authority.
- Human approval before external execution in V0.
- Orders are not realized profit.
- Profit is only recognized from reconciled/settled economic evidence.
- Agent does not withdraw, transfer, or change payout destinations.
- UK eligibility is a gate, not an assumption.
