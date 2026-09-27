import { describe, expect, it } from 'vitest';
import { ingestOperatorEvidence } from './operatorEvidenceIntake';
import { RealityEvidenceRegistry } from './realityEvidenceRegistry';

const base = {
  evidenceId: 'E-OP-1', subject: 'AFFILIATE_ACCESS' as const, state: 'VERIFIED' as const,
  source: 'TIKTOK_UI' as const, observedAt: '2026-09-27T16:00:00Z',
  reference: 'creator-center:affiliate-access:verified',
};

describe('operator evidence intake', () => {
  it('normalizes safe operator evidence into the reality registry', () => {
    const r = new RealityEvidenceRegistry();
    expect(ingestOperatorEvidence(r, base).duplicate).toBe(false);
    expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T16:01:00Z').state).toBe('VERIFIED');
  });

  it('preserves blocked observations instead of converting them to unknown', () => {
    const r = new RealityEvidenceRegistry();
    ingestOperatorEvidence(r,{...base,evidenceId:'B1',state:'BLOCKED'});
    expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T16:01:00Z').state).toBe('BLOCKED');
  });

  it('preserves explicit UNKNOWN observations', () => {
    const r = new RealityEvidenceRegistry();
    ingestOperatorEvidence(r,{...base,evidenceId:'U1',state:'UNKNOWN'});
    expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T16:01:00Z').state).toBe('UNKNOWN');
  });

  it('inherits idempotency from the evidence registry', () => {
    const r = new RealityEvidenceRegistry();
    ingestOperatorEvidence(r,base);
    expect(ingestOperatorEvidence(r,base).duplicate).toBe(true);
  });

  it('rejects credentials and secrets embedded in evidence references', () => {
    const r = new RealityEvidenceRegistry();
    expect(()=>ingestOperatorEvidence(r,{...base,reference:'password=supersecret'})).toThrow();
    expect(()=>ingestOperatorEvidence(r,{...base,reference:'api token: abc'})).toThrow();
  });

  it('rejects raw identity or banking identifiers embedded in notes', () => {
    const r = new RealityEvidenceRegistry();
    expect(()=>ingestOperatorEvidence(r,{...base,note:'passport number: XX123'})).toThrow();
    expect(()=>ingestOperatorEvidence(r,{...base,note:'bank account: 123456'})).toThrow();
  });

  it('supports evidence expiration without weakening registry freshness semantics', () => {
    const r = new RealityEvidenceRegistry();
    ingestOperatorEvidence(r,{...base,validUntil:'2026-09-27T17:00:00Z'});
    expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T18:00:00Z').state).toBe('UNKNOWN');
  });
});
