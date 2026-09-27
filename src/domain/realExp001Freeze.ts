import type { RealProductRecord } from './realProductIntake';
import type { RealOpportunityInput, RealOpportunityResult } from './realOpportunityPipeline';
import type { ExperimentSpec } from './experimentEngine';

export type FrozenExp001Candidate = {
  experiment: ExperimentSpec;
  product: Readonly<RealProductRecord>;
  opportunityScore: number;
  decisionConfidence: number;
  allocationScore: number;
  expectedRealizedProfitGbp: number;
  evidenceRefs: readonly string[];
  frozenAt: string;
};

export function freezeRealExp001(
  input: RealOpportunityInput,
  result: RealOpportunityResult,
  frozenAt: string,
  additionalEvidenceRefs: readonly string[] = [],
): FrozenExp001Candidate {
  if (result.allocation.decision !== 'ALLOCATE') throw new Error('EXP-001 cannot be frozen without an ALLOCATE decision');
  if (result.productId !== input.product.productId) throw new Error('Opportunity/product trace mismatch');
  if (!result.fresh) throw new Error('EXP-001 requires fresh product evidence');
  if (!Number.isFinite(Date.parse(frozenAt))) throw new Error('frozenAt must be a valid timestamp');

  const evidenceRefs = [...new Set([input.product.listingRef, ...additionalEvidenceRefs].filter(ref => ref.trim()))];
  if (!evidenceRefs[0]?.trim()) throw new Error('EXP-001 requires product evidence reference');

  const experiment: ExperimentSpec = {
    experimentId: 'EXP-001',
    decisionId: 'DEC-001',
    opportunityId: input.product.productId,
    hypothesis: 'A result-first product demonstration produces qualified commerce intent with positive settled economics.',
    variableUnderTest: 'hook',
    controlDescription: 'Problem-first opening',
    treatmentDescription: 'Product result demonstrated in the first two seconds',
    primaryMetric: 'settled_realized_contribution_gbp',
    capitalLimit: input.limits.capitalLimit,
    lossLimit: input.limits.lossLimit,
    durationHours: 72,
    successThreshold: 0.01,
    failureThreshold: 0,
    minimumEvidence: 1,
  };

  return Object.freeze({
    experiment: Object.freeze(experiment),
    product: Object.freeze(structuredClone(input.product)),
    opportunityScore: result.opportunityScore,
    decisionConfidence: result.decisionConfidence,
    allocationScore: result.allocation.allocationScore,
    expectedRealizedProfitGbp: result.economics.expectedRealizedProfit,
    evidenceRefs: Object.freeze([...evidenceRefs]),
    frozenAt,
  });
}
