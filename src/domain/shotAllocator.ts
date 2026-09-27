export type AllocationCandidate = {
  id: string;
  opportunityScore: number;
  confidence: number;
  informationValue: number;
  urgency: number;
  capitalRequired: number;
  expectedLoss: number;
  marketEligible: boolean;
  policyAllowed: boolean;
  supplyAcceptable: boolean;
  accountRiskAcceptable: boolean;
};

export type AllocationLimits = {
  availableCapital: number;
  capitalLimit: number;
  lossLimit: number;
  minimumAllocationScore: number;
};

export type AllocationDecision =
  | { decision: 'ALLOCATE'; candidateId: string; allocationScore: number; capital: number }
  | { decision: 'NO_ACTION'; reason: string };

function assertScore(name: string, value: number) {
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error(`${name} must be between 0 and 100`);
}
function assertMoney(name: string, value: number) {
  if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must be a finite non-negative number`);
}

export function allocationScore(candidate: AllocationCandidate): number {
  assertScore('opportunityScore', candidate.opportunityScore);
  assertScore('confidence', candidate.confidence);
  assertScore('informationValue', candidate.informationValue);
  assertScore('urgency', candidate.urgency);
  return Math.round((
    candidate.opportunityScore * 0.45 +
    candidate.confidence * 0.25 +
    candidate.informationValue * 0.20 +
    candidate.urgency * 0.10
  ) * 100) / 100;
}

function isEligible(candidate: AllocationCandidate, limits: AllocationLimits): boolean {
  return candidate.marketEligible &&
    candidate.policyAllowed &&
    candidate.supplyAcceptable &&
    candidate.accountRiskAcceptable &&
    candidate.capitalRequired <= limits.availableCapital &&
    candidate.capitalRequired <= limits.capitalLimit &&
    candidate.expectedLoss <= limits.lossLimit;
}

export function allocateNextShot(
  candidates: AllocationCandidate[],
  limits: AllocationLimits,
): AllocationDecision {
  assertMoney('availableCapital', limits.availableCapital);
  assertMoney('capitalLimit', limits.capitalLimit);
  assertMoney('lossLimit', limits.lossLimit);
  assertScore('minimumAllocationScore', limits.minimumAllocationScore);

  const ranked = candidates
    .filter((candidate) => {
      assertMoney('capitalRequired', candidate.capitalRequired);
      assertMoney('expectedLoss', candidate.expectedLoss);
      allocationScore(candidate);
      return isEligible(candidate, limits);
    })
    .map((candidate) => ({ candidate, score: allocationScore(candidate) }))
    .filter(({ score }) => score >= limits.minimumAllocationScore)
    .sort((a, b) => b.score - a.score || a.candidate.id.localeCompare(b.candidate.id));

  if (ranked.length === 0) {
    return { decision: 'NO_ACTION', reason: 'No candidate passes eligibility, risk, capital and score gates.' };
  }

  const winner = ranked[0];
  return {
    decision: 'ALLOCATE',
    candidateId: winner.candidate.id,
    allocationScore: winner.score,
    capital: winner.candidate.capitalRequired,
  };
}
