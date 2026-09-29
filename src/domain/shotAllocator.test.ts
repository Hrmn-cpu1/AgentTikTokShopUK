import { describe, expect, it } from 'vitest';
import { allocateNextShot, allocationScore, type AllocationCandidate } from './shotAllocator';

const candidate: AllocationCandidate = {
  id: 'exp-a', opportunityScore: 80, confidence: 70, informationValue: 60, urgency: 50,
  capitalRequired: 8, expectedLoss: 8, marketEligible: true, policyAllowed: true,
  supplyAcceptable: true, accountRiskAcceptable: true,
};
const limits = { availableCapital: 20, capitalLimit: 10, lossLimit: 8, minimumAllocationScore: 60 };

describe('shot allocator', () => {
  it('uses the frozen allocation formula', () => {
    expect(allocationScore(candidate)).toBe(70.5);
  });

  it('allocates to the highest eligible candidate', () => {
    const decision = allocateNextShot([
      candidate,
      { ...candidate, id: 'exp-b', opportunityScore: 90, confidence: 80 },
    ], limits);
    expect(decision).toMatchObject({ decision: 'ALLOCATE', candidateId: 'exp-b', capital: 8 });
  });

  it('returns NO_ACTION when market eligibility is blocked', () => {
    expect(allocateNextShot([{ ...candidate, marketEligible: false }], limits).decision).toBe('NO_ACTION');
  });

  it('returns NO_ACTION when capital or loss limits would be breached', () => {
    expect(allocateNextShot([{ ...candidate, capitalRequired: 11 }], limits).decision).toBe('NO_ACTION');
    expect(allocateNextShot([{ ...candidate, expectedLoss: 9 }], limits).decision).toBe('NO_ACTION');
  });

  it('returns NO_ACTION when policy, supply or account risk gates fail', () => {
    expect(allocateNextShot([{ ...candidate, policyAllowed: false }], limits).decision).toBe('NO_ACTION');
    expect(allocateNextShot([{ ...candidate, supplyAcceptable: false }], limits).decision).toBe('NO_ACTION');
    expect(allocateNextShot([{ ...candidate, accountRiskAcceptable: false }], limits).decision).toBe('NO_ACTION');
  });

  it('does not force action below the minimum allocation score', () => {
    expect(allocateNextShot([{ ...candidate, opportunityScore: 10, confidence: 10, informationValue: 10, urgency: 10 }], limits).decision).toBe('NO_ACTION');
  });

  it('uses candidate id only as deterministic tie breaker', () => {
    const decision = allocateNextShot([{ ...candidate, id: 'b' }, { ...candidate, id: 'a' }], limits);
    expect(decision).toMatchObject({ decision: 'ALLOCATE', candidateId: 'a' });
  });
});
