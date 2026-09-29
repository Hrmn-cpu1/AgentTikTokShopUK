export type AnalystContext = {
  market: 'UK';
  currency: 'GBP';
  productName: string;
  opportunityScore: number;
  expectedRealizedProfit: number;
  cashVelocity: number;
  confidenceScore: number | null;
  confidenceCoverage: number;
  allocationDecision: 'ALLOCATE' | 'NO_ACTION';
  marketEligibility: 'ELIGIBLE' | 'CONDITIONAL' | 'BLOCKED' | 'UNKNOWN';
  evidenceSummary: string[];
  knownRisks: string[];
  unknowns: string[];
};

export type OpportunityAnalysis = {
  thesis: string;
  whyNow: string;
  strengths: string[];
  risks: string[];
  unknowns: string[];
  recommendedHypothesis: string;
  recommendedTest: string;
  doNotAssume: string[];
};

export type OpportunityAnalyst = {
  analyze(context: Readonly<AnalystContext>): Promise<OpportunityAnalysis>;
};

export const OPPORTUNITY_ANALYST_SYSTEM = `
You are the Opportunity Analyst for TikTok Shop Profit Agent, UK-first.
Goal: recommend the cheapest useful commercial experiment, not maximize views or GMV.

Immutable truths:
- VIRAL != WINNER. ORDER != WINNER. GMV != WINNER.
- Winner means repeatable risk-adjusted realized profit.
- Money path: attention -> intent -> order -> delivery -> settlement -> realized contribution.
- UNKNOWN is not zero and is not evidence.
- LLM reasoning is not authorization.
- Never change deterministic economics, confidence, ranking, eligibility, allocation or policy outputs.
- Never invent TikTok eligibility, seller quality, supply, commission, orders, settlement, product claims or evidence.
- If allocationDecision is NO_ACTION, do not recommend spending or external execution.
- If marketEligibility is not ELIGIBLE, real-money UK execution remains blocked.
- Prefer minimum-cost tests with high information value.
- Human approval remains required for external execution in V0.
- Withdrawal and payout changes remain manual.
- Distinguish evidence from inference and name material unknowns.
- Optimize expected realized contribution / capital / time / risk, not currency strength or vanity metrics.
Return only the structured OpportunityAnalysis contract.
`.trim();

export function validateOpportunityAnalysis(value: OpportunityAnalysis): OpportunityAnalysis {
  const requiredStrings: Array<keyof Pick<OpportunityAnalysis, 'thesis' | 'whyNow' | 'recommendedHypothesis' | 'recommendedTest'>> =
    ['thesis', 'whyNow', 'recommendedHypothesis', 'recommendedTest'];
  for (const key of requiredStrings) {
    if (!value[key]?.trim()) throw new Error(`OpportunityAnalysis.${key} is required`);
  }
  for (const key of ['strengths', 'risks', 'unknowns', 'doNotAssume'] as const) {
    if (!Array.isArray(value[key])) throw new Error(`OpportunityAnalysis.${key} must be an array`);
  }
  return value;
}

export function buildOpportunityAnalystInput(context: AnalystContext) {
  return {
    system: OPPORTUNITY_ANALYST_SYSTEM,
    context: structuredClone(context),
  };
}
