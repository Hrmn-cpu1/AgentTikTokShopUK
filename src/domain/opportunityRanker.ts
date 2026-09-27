export type OpportunitySignals = {
  economicPotential: number;
  cashVelocity: number;
  decisionConfidence: number;
  creativePotential: number;
  supplyReliability: number;
  informationValue: number;
  opportunityWindow: number;
  riskPenalty: number;
};

export type RankedOpportunity = OpportunitySignals & {
  id: string;
  score: number;
};

const weights = {
  economicPotential: 0.25,
  cashVelocity: 0.20,
  decisionConfidence: 0.15,
  creativePotential: 0.15,
  supplyReliability: 0.10,
  informationValue: 0.10,
  opportunityWindow: 0.05,
} as const;

function assertScore(name: string, value: number) {
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`${name} must be between 0 and 100`);
  }
}

export function scoreOpportunity(signals: OpportunitySignals): number {
  for (const [key, value] of Object.entries(signals)) assertScore(key, value);
  const positive =
    signals.economicPotential * weights.economicPotential +
    signals.cashVelocity * weights.cashVelocity +
    signals.decisionConfidence * weights.decisionConfidence +
    signals.creativePotential * weights.creativePotential +
    signals.supplyReliability * weights.supplyReliability +
    signals.informationValue * weights.informationValue +
    signals.opportunityWindow * weights.opportunityWindow;
  return Math.round(Math.max(0, Math.min(100, positive - signals.riskPenalty)) * 100) / 100;
}

export function rankOpportunities(
  opportunities: Array<{ id: string; signals: OpportunitySignals }>,
): RankedOpportunity[] {
  return opportunities
    .map(({ id, signals }) => ({ id, ...signals, score: scoreOpportunity(signals) }))
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
}
