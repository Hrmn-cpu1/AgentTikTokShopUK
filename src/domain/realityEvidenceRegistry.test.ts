import { describe, expect, it } from 'vitest';
import { RealityEvidenceRegistry, type RealityEvidence } from './realityEvidenceRegistry';

const evidence: RealityEvidence = {
  evidenceId: 'EVID-001', subject: 'AFFILIATE_ACCESS', state: 'VERIFIED',
  source: 'TIKTOK_UI', observedAt: '2026-09-27T12:00:00Z',
  validUntil: '2026-10-04T12:00:00Z', reference: 'operator-check:affiliate-center',
  containsSensitiveData: false,
};

describe('reality evidence registry', () => {
  it('moves UNKNOWN to VERIFIED only through recorded evidence', () => {
    const r = new RealityEvidenceRegistry();
    expect(r.resolve('AFFILIATE_ACCESS', '2026-09-27T12:00:00Z').state).toBe('UNKNOWN');
    r.record(evidence);
    expect(r.resolve('AFFILIATE_ACCESS', '2026-09-27T12:01:00Z')).toMatchObject({ state: 'VERIFIED', evidenceId: 'EVID-001' });
  });

  it('expires stale evidence back to UNKNOWN rather than assuming reality', () => {
    const r = new RealityEvidenceRegistry(); r.record(evidence);
    expect(r.resolve('AFFILIATE_ACCESS', '2026-10-05T00:00:00Z').state).toBe('UNKNOWN');
  });

  it('records BLOCKED evidence as truth instead of hiding it', () => {
    const r = new RealityEvidenceRegistry();
    r.record({ ...evidence, evidenceId: 'EVID-BLOCK', state: 'BLOCKED' });
    expect(r.resolve('AFFILIATE_ACCESS', '2026-09-27T13:00:00Z').state).toBe('BLOCKED');
  });

  it('is idempotent by evidence id', () => {
    const r = new RealityEvidenceRegistry();
    expect(r.record(evidence).duplicate).toBe(false);
    expect(r.record(evidence).duplicate).toBe(true);
  });

  it('uses the latest observed evidence for a subject', () => {
    const r = new RealityEvidenceRegistry(); r.record(evidence);
    r.record({ ...evidence, evidenceId: 'EVID-002', state: 'BLOCKED', observedAt: '2026-09-28T12:00:00Z' });
    expect(r.resolve('AFFILIATE_ACCESS', '2026-09-28T13:00:00Z')).toMatchObject({ state: 'BLOCKED', evidenceId: 'EVID-002' });
  });

  it('refuses evidence payloads marked as containing sensitive KYC or payout data', () => {
    const r = new RealityEvidenceRegistry();
    expect(() => r.record({ ...evidence, containsSensitiveData: true } as never)).toThrow();
  });

  it('returns exactly the reality subjects that still need work', () => {
    const r = new RealityEvidenceRegistry(); r.record(evidence);
    const unresolved = r.unresolved(['AFFILIATE_ACCESS', 'PAYOUT_METHOD'], '2026-09-27T13:00:00Z');
    expect(unresolved.map((x) => x.subject)).toEqual(['PAYOUT_METHOD']);
  });
});
