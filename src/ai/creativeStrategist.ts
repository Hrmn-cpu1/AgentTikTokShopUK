export type ProductTruth = {
  verifiedFacts: string[];
  supportedClaims: string[];
  unsupportedClaims: string[];
  prohibitedClaims: string[];
};

export type CreativeContext = {
  experimentId: string;
  hypothesis: string;
  variableUnderTest: string;
  productName: string;
  creatorArchetype: string;
  offer: string;
  productTruth: ProductTruth;
  winnerPatterns: string[];
  failurePatterns: string[];
};

export type CreativeStrategy = {
  hypothesis: string;
  hook: string;
  firstFrame: string;
  demo: string;
  proof: string;
  objection: string;
  offer: string;
  cta: string;
  shotList: string[];
  script: string[];
  mutation: {
    parentCreativeId: string | null;
    variableChanged: string;
    rationale: string;
  };
  claimsUsed: string[];
};

export const CREATIVE_STRATEGIST_SYSTEM = `
You are the Creative Strategist for TikTok Shop Profit Agent, UK-first.
Create one controlled creative expression of the supplied experiment hypothesis.

Creative chain:
HOOK -> RETENTION -> COMMERCE INTENT -> PROOF -> OFFER -> CTA.

Rules learned from commerce research:
- Attention is not commerce truth. Views do not make a winner.
- Demonstrate the product early when demonstration is relevant.
- Optimize for qualified intent and eventual realized profit, not vanity metrics.
- Use winner patterns as evidence-informed patterns, never as guarantees.
- Use failure patterns to avoid repeating known losing structures.
- Prefer human-native, credible content over AI-slop or mass random generation.
- Mutations must have lineage and change one declared variable at a time.
- Never invent product facts, seller facts, discounts, scarcity, reviews, results or guarantees.
- Every factual claim must exist in verifiedFacts or supportedClaims.
- Never use unsupportedClaims or prohibitedClaims.
- Do not change experiment hypothesis, deterministic economics, thresholds, eligibility, allocation or policy.
- External publishing still requires human approval in V0.
Return only the structured CreativeStrategy contract.
`.trim();

export function allowedClaims(truth: ProductTruth): Set<string> {
  return new Set([...truth.verifiedFacts, ...truth.supportedClaims]);
}

export function validateCreativeStrategy(strategy: CreativeStrategy, context: CreativeContext): CreativeStrategy {
  for (const key of ['hypothesis','hook','firstFrame','demo','proof','objection','offer','cta'] as const) {
    if (!strategy[key].trim()) throw new Error(`CreativeStrategy.${key} is required`);
  }
  if (strategy.hypothesis !== context.hypothesis) throw new Error('Creative strategy cannot change the experiment hypothesis');
  if (strategy.mutation.variableChanged !== context.variableUnderTest) {
    throw new Error('Mutation must change only the experiment variableUnderTest');
  }
  const allowed = allowedClaims(context.productTruth);
  const forbidden = new Set([...context.productTruth.unsupportedClaims, ...context.productTruth.prohibitedClaims]);
  for (const claim of strategy.claimsUsed) {
    if (!allowed.has(claim)) throw new Error(`Unverified creative claim: ${claim}`);
    if (forbidden.has(claim)) throw new Error(`Forbidden creative claim: ${claim}`);
  }
  if (strategy.shotList.length === 0 || strategy.script.length === 0) throw new Error('Creative requires shotList and script');
  return strategy;
}

export function buildCreativeStrategistInput(context: CreativeContext) {
  return { system: CREATIVE_STRATEGIST_SYSTEM, context: structuredClone(context) };
}
