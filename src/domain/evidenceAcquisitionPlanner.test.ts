import { describe, expect, it } from 'vitest';
import { planEvidenceAcquisition } from './evidenceAcquisitionPlanner';
import type { RealityState, RealitySubject } from './realityEvidenceRegistry';

const s = (subject: RealitySubject, state: 'VERIFIED'|'BLOCKED'|'UNKNOWN'): RealityState => ({ subject, state, evidenceId: null, reason: 'test' });

describe('evidence acquisition planner', () => {
  it('prioritizes critical money-path uncertainty before product or creative work', () => {
    const p = planEvidenceAcquisition([s('PAYOUT_METHOD','UNKNOWN'), s('REAL_PRODUCT','UNKNOWN'), s('CREATIVE_APPROVAL','UNKNOWN')]);
    expect(p.next?.subject).toBe('PAYOUT_METHOD');
    expect(p.ordered.every((x) => x.dependencyTier === 1)).toBe(true);
  });

  it('chooses the highest information-per-cost probe within the same dependency tier', () => {
    const p = planEvidenceAcquisition([s('IDENTITY_KYC','UNKNOWN'), s('AFFILIATE_ACCESS','UNKNOWN')]);
    expect(p.next?.subject).toBe('AFFILIATE_ACCESS');
  });

  it('stops acquisition planning on a known hard blocker', () => {
    const p = planEvidenceAcquisition([s('UK_ACCOUNT_ELIGIBILITY','BLOCKED'), s('AFFILIATE_ACCESS','UNKNOWN')]);
    expect(p.next).toBeNull();
    expect(p.blocked.map((x) => x.subject)).toContain('UK_ACCOUNT_ELIGIBILITY');
  });

  it('moves to product/supply evidence after critical account and money-path gates are verified', () => {
    const p = planEvidenceAcquisition([s('UK_ACCOUNT_ELIGIBILITY','VERIFIED'), s('AFFILIATE_ACCESS','VERIFIED'), s('REAL_PRODUCT','UNKNOWN'), s('SUPPLY','UNKNOWN')]);
    expect(p.next?.dependencyTier).toBe(2);
  });

  it('moves to creative/economic confirmation only after upstream evidence is resolved', () => {
    const p = planEvidenceAcquisition([s('REAL_PRODUCT','VERIFIED'), s('SUPPLY','VERIFIED'), s('CAPITAL_BOUND','UNKNOWN'), s('CREATIVE_APPROVAL','UNKNOWN')]);
    expect(p.next?.dependencyTier).toBe(3);
  });

  it('returns no action when every supplied reality state is verified', () => {
    expect(planEvidenceAcquisition([s('AFFILIATE_ACCESS','VERIFIED')]).next).toBeNull();
  });

  it('never requests raw KYC or banking secrets in probe instructions', () => {
    const p = planEvidenceAcquisition([s('IDENTITY_KYC','UNKNOWN'), s('PAYOUT_METHOD','UNKNOWN')]);
    const text = p.ordered.map((x) => x.instruction.toLowerCase()).join(' ');
    expect(text).not.toContain('passport number');
    expect(text).not.toContain('bank password');
  });
});
