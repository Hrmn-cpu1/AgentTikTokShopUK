import { describe, expect, it } from 'vitest';
import { prepareExp001, type Exp001Candidate } from './exp001';

const candidate: Exp001Candidate = {
  opportunityId: 'OPP-REAL-001', productName: 'Evidence-backed UK candidate',
  sourceRefs: ['source-1'], observedAt: '2026-09-27T00:00:00Z',
  economics: { expectedOrders: 3, paidPrice: 25, commissionRate: 0.15, settlementProbability: 0.8, experimentCost: 4, capitalRequired: 4, timeToCashDays: 5, experimentShots: 1 },
  confidence: { sourceReliability: 80, sampleStrength: 60, freshness: 95, crossSourceAgreement: 60, attributionQuality: 50 },
  creativePotential: 80, supplyReliability: 70, informationValue: 85, opportunityWindow: 80, riskPenalty: 10, urgency: 75,
};
const eligible = { account_location: 'VERIFIED', identity_kyc: 'VERIFIED', affiliate_access: 'VERIFIED', payout_method: 'VERIFIED' } as const;
const limits = { availableCapital: 10, capitalLimit: 8, lossLimit: 8, minimumAllocationScore: 50 };

describe('EXP-001 preparation', () => {
  it('builds the first experiment through deterministic economics confidence ranking and allocation', () => {
    const result = prepareExp001(candidate, eligible, limits);
    expect(result.experiment.experimentId).toBe('EXP-001');
    expect(result.experiment.primaryMetric).toBe('settled_realized_contribution_gbp');
    expect(result.allocation.decision).toBe('ALLOCATE');
  });

  it('blocks real execution when UK money-path eligibility is not proven', () => {
    const result = prepareExp001(candidate, { ...eligible, payout_method: 'UNKNOWN' }, limits);
    expect(result.eligibility).toBe('CONDITIONAL');
    expect(result.allocation.decision).toBe('NO_ACTION');
  });

  it('requires source provenance and freshness before EXP-001 exists', () => {
    expect(() => prepareExp001({ ...candidate, sourceRefs: [] }, eligible, limits)).toThrow();
    expect(() => prepareExp001({ ...candidate, observedAt: '' }, eligible, limits)).toThrow();
  });

  it('blocks weak supply even when the opportunity otherwise scores well', () => {
    const result = prepareExp001({ ...candidate, supplyReliability: 40 }, eligible, limits);
    expect(result.allocation.decision).toBe('NO_ACTION');
  });

  it('keeps the experiment loss bounded by the explicit UK shot limits', () => {
    const result = prepareExp001(candidate, eligible, limits);
    expect(result.experiment.capitalLimit).toBe(8);
    expect(result.experiment.lossLimit).toBe(8);
  });
});
