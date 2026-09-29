import { describe, expect, it } from 'vitest';
import { evaluateExp001Launch, type Exp001LaunchEvidence } from './exp001LaunchGate';

const ready: Exp001LaunchEvidence = {
  ukAccountEligibility: 'VERIFIED', identityKyc: 'VERIFIED', affiliateAccess: 'VERIFIED',
  payoutMethod: 'VERIFIED', realProductSelected: 'VERIFIED', productEvidenceFresh: 'VERIFIED',
  supplyAvailable: 'VERIFIED', creativeApproved: 'VERIFIED', productClaimsValid: 'VERIFIED',
  capitalBounded: 'VERIFIED', lossBounded: 'VERIFIED', executionEnabled: true,
};

describe('EXP-001 reality launch gate', () => {
  it('allows manual launch only when every real-world prerequisite is verified', () => {
    expect(evaluateExp001Launch(ready)).toMatchObject({ readiness: 'READY', mayPublishManually: true });
  });

  it('fails closed when UK account eligibility is unknown', () => {
    const r = evaluateExp001Launch({ ...ready, ukAccountEligibility: 'UNKNOWN' });
    expect(r).toMatchObject({ readiness: 'NOT_PROVEN', mayPublishManually: false });
    expect(r.unknowns).toContain('UK account eligibility');
  });

  it('blocks when KYC affiliate or payout path is blocked', () => {
    expect(evaluateExp001Launch({ ...ready, identityKyc: 'BLOCKED' }).readiness).toBe('BLOCKED');
    expect(evaluateExp001Launch({ ...ready, affiliateAccess: 'BLOCKED' }).readiness).toBe('BLOCKED');
    expect(evaluateExp001Launch({ ...ready, payoutMethod: 'BLOCKED' }).readiness).toBe('BLOCKED');
  });

  it('does not launch a simulated or stale product candidate', () => {
    expect(evaluateExp001Launch({ ...ready, realProductSelected: 'UNKNOWN' }).mayPublishManually).toBe(false);
    expect(evaluateExp001Launch({ ...ready, productEvidenceFresh: 'BLOCKED' }).mayPublishManually).toBe(false);
  });

  it('requires supply creative claims and economic bounds together', () => {
    expect(evaluateExp001Launch({ ...ready, supplyAvailable: 'UNKNOWN' }).mayPublishManually).toBe(false);
    expect(evaluateExp001Launch({ ...ready, creativeApproved: 'UNKNOWN' }).mayPublishManually).toBe(false);
    expect(evaluateExp001Launch({ ...ready, productClaimsValid: 'BLOCKED' }).mayPublishManually).toBe(false);
    expect(evaluateExp001Launch({ ...ready, capitalBounded: 'BLOCKED' }).mayPublishManually).toBe(false);
    expect(evaluateExp001Launch({ ...ready, lossBounded: 'BLOCKED' }).mayPublishManually).toBe(false);
  });

  it('keeps the kill switch stronger than a fully verified launch manifest', () => {
    const r = evaluateExp001Launch({ ...ready, executionEnabled: false });
    expect(r).toMatchObject({ readiness: 'BLOCKED', mayPublishManually: false });
    expect(r.blockers).toContain('Execution kill switch');
  });
});
