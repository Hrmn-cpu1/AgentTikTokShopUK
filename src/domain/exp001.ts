import { calculateEconomics, type EconomicsInput } from './economics';
import { calculateConfidence, confidenceForDecision, type ConfidenceInput } from './confidence';
import { scoreOpportunity, type OpportunitySignals } from './opportunityRanker';
import { allocateNextShot, type AllocationLimits } from './shotAllocator';
import { resolveEligibility, type EligibilitySnapshot } from './eligibility';
import type { ExperimentSpec } from './experimentEngine';

export type Exp001Candidate = {
  opportunityId: string;
  productName: string;
  sourceRefs: string[];
  observedAt: string;
  economics: EconomicsInput;
  confidence: ConfidenceInput;
  creativePotential: number;
  supplyReliability: number;
  informationValue: number;
  opportunityWindow: number;
  riskPenalty: number;
  urgency: number;
};

export type Exp001Preparation = {
  experiment: ExperimentSpec;
  eligibility: ReturnType<typeof resolveEligibility>;
  opportunityScore: number;
  decisionConfidence: number;
  allocation: ReturnType<typeof allocateNextShot>;
  sourceRefs: string[];
  observedAt: string;
};

function normalizePositive(value: number): number {
  if (!Number.isFinite(value)) throw new Error('Signal must be finite');
  return Math.max(0, Math.min(100, value));
}

export function prepareExp001(
  candidate: Exp001Candidate,
  eligibilitySnapshot: EligibilitySnapshot,
  limits: AllocationLimits,
): Exp001Preparation {
  if (candidate.sourceRefs.length === 0) throw new Error('EXP-001 requires at least one evidence source');
  if (!candidate.observedAt) throw new Error('EXP-001 requires evidence freshness timestamp');

  const eligibility = resolveEligibility(eligibilitySnapshot);
  const economics = calculateEconomics(candidate.economics);
  const confidence = calculateConfidence(candidate.confidence);
  const decisionConfidence = confidenceForDecision(confidence);

  const economicPotential = normalizePositive(50 + economics.expectedRealizedProfit * 2);
  const cashVelocity = normalizePositive(50 + economics.cashVelocity * 10);

  const signals: OpportunitySignals = {
    economicPotential,
    cashVelocity,
    decisionConfidence,
    creativePotential: candidate.creativePotential,
    supplyReliability: candidate.supplyReliability,
    informationValue: candidate.informationValue,
    opportunityWindow: candidate.opportunityWindow,
    riskPenalty: candidate.riskPenalty,
  };
  const opportunityScore = scoreOpportunity(signals);

  const allocation = allocateNextShot([{
    id: 'EXP-001',
    opportunityScore,
    confidence: decisionConfidence,
    informationValue: candidate.informationValue,
    urgency: candidate.urgency,
    capitalRequired: candidate.economics.capitalRequired,
    expectedLoss: candidate.economics.experimentCost,
    marketEligible: eligibility === 'ELIGIBLE',
    policyAllowed: true,
    supplyAcceptable: candidate.supplyReliability >= 50,
    accountRiskAcceptable: true,
  }], limits);

  const experiment: ExperimentSpec = {
    experimentId: 'EXP-001',
    decisionId: 'DEC-001',
    opportunityId: candidate.opportunityId,
    hypothesis: 'A result-first product demonstration produces qualified commerce intent with positive settled economics.',
    variableUnderTest: 'hook',
    controlDescription: 'Problem-first opening',
    treatmentDescription: 'Product result demonstrated in the first two seconds',
    primaryMetric: 'settled_realized_contribution_gbp',
    capitalLimit: limits.capitalLimit,
    lossLimit: limits.lossLimit,
    durationHours: 72,
    successThreshold: 0.01,
    failureThreshold: 0,
    minimumEvidence: 1,
  };

  return { experiment, eligibility, opportunityScore, decisionConfidence, allocation, sourceRefs: [...candidate.sourceRefs], observedAt: candidate.observedAt };
}
