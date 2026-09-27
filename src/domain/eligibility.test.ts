import { describe, expect, it } from 'vitest';
import { canExecuteExternally, defaultEligibility, resolveEligibility, type EligibilitySnapshot } from './eligibility';

const verified: EligibilitySnapshot = {
  account_location: 'VERIFIED',
  identity_kyc: 'VERIFIED',
  affiliate_access: 'VERIFIED',
  payout_method: 'VERIFIED',
};

describe('UK eligibility gate', () => {
  it('starts UNKNOWN and fails closed', () => {
    expect(resolveEligibility(defaultEligibility)).toBe('UNKNOWN');
    expect(canExecuteExternally(defaultEligibility)).toBe(false);
  });

  it('is ELIGIBLE only when every requirement is verified', () => {
    expect(resolveEligibility(verified)).toBe('ELIGIBLE');
    expect(canExecuteExternally(verified)).toBe(true);
  });

  it('is CONDITIONAL when evidence is incomplete', () => {
    expect(resolveEligibility({ ...verified, payout_method: 'UNKNOWN' })).toBe('CONDITIONAL');
    expect(canExecuteExternally({ ...verified, payout_method: 'UNKNOWN' })).toBe(false);
  });

  it('BLOCKED overrides verified and unknown states', () => {
    const state = { ...verified, identity_kyc: 'BLOCKED' } as EligibilitySnapshot;
    expect(resolveEligibility(state)).toBe('BLOCKED');
    expect(canExecuteExternally(state)).toBe(false);
  });
});
