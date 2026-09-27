import { describe, expect, it } from 'vitest';
import { orchestrateReadiness } from './realityReadinessOrchestrator';
import { RealityEvidenceRegistry, type RealitySubject } from './realityEvidenceRegistry';

const subjects: RealitySubject[] = [
  'UK_ACCOUNT_ELIGIBILITY','IDENTITY_KYC','AFFILIATE_ACCESS','PAYOUT_METHOD','REAL_PRODUCT',
  'PRODUCT_FRESHNESS','SUPPLY','CREATIVE_APPROVAL','PRODUCT_CLAIMS','CAPITAL_BOUND','LOSS_BOUND',
];
const now = '2026-09-27T14:00:00Z';
function verifiedRegistry() {
  const r = new RealityEvidenceRegistry();
  subjects.forEach((subject, i) => r.record({
    evidenceId: `E-${i}`, subject, state: 'VERIFIED', source: 'OPERATOR_VERIFIED',
    observedAt: '2026-09-27T13:00:00Z', validUntil: null, reference: `ref:${subject}`, containsSensitiveData: false,
  }));
  return r;
}

describe('reality readiness orchestrator', () => {
  it('chooses the next cheapest critical verification from a completely unknown reality', () => {
    const r = orchestrateReadiness(new RealityEvidenceRegistry(), now, true);
    expect(r.action).toBe('VERIFY_NEXT');
    expect(r.nextProbe?.dependencyTier).toBe(1);
  });

  it('advances downstream after upstream reality becomes verified', () => {
    const registry = new RealityEvidenceRegistry();
    ['UK_ACCOUNT_ELIGIBILITY','IDENTITY_KYC','AFFILIATE_ACCESS','PAYOUT_METHOD'].forEach((subject, i) =>
      registry.record({ evidenceId: `U-${i}`, subject: subject as RealitySubject, state: 'VERIFIED', source: 'TIKTOK_UI', observedAt: '2026-09-27T13:00:00Z', validUntil: null, reference: 'ui-check', containsSensitiveData: false }));
    const r = orchestrateReadiness(registry, now, true);
    expect(r.action).toBe('VERIFY_NEXT');
    expect(r.nextProbe?.dependencyTier).toBe(2);
  });

  it('surfaces a known blocker instead of suggesting unrelated work', () => {
    const registry = new RealityEvidenceRegistry();
    registry.record({ evidenceId: 'B-1', subject: 'AFFILIATE_ACCESS', state: 'BLOCKED', source: 'TIKTOK_UI', observedAt: '2026-09-27T13:00:00Z', validUntil: null, reference: 'ui-blocked', containsSensitiveData: false });
    expect(orchestrateReadiness(registry, now, true).action).toBe('RESOLVE_BLOCKER');
  });

  it('declares ready only when all reality evidence is verified and execution is enabled', () => {
    const r = orchestrateReadiness(verifiedRegistry(), now, true);
    expect(r).toMatchObject({ action: 'READY_TO_LAUNCH', launch: { readiness: 'READY', mayPublishManually: true } });
  });

  it('keeps the kill switch stronger than complete evidence', () => {
    const r = orchestrateReadiness(verifiedRegistry(), now, false);
    expect(r).toMatchObject({ action: 'RESOLVE_BLOCKER', launch: { readiness: 'BLOCKED', mayPublishManually: false } });
  });

  it('automatically reopens verification when previously verified evidence expires', () => {
    const registry = verifiedRegistry();
    registry.record({ evidenceId: 'EXPIRING', subject: 'PAYOUT_METHOD', state: 'VERIFIED', source: 'TIKTOK_UI', observedAt: '2026-09-28T13:00:00Z', validUntil: '2026-09-28T13:30:00Z', reference: 'payout-check', containsSensitiveData: false });
    const r = orchestrateReadiness(registry, '2026-09-28T14:00:00Z', true);
    expect(r.action).toBe('VERIFY_NEXT');
    expect(r.nextProbe?.subject).toBe('PAYOUT_METHOD');
  });
});
