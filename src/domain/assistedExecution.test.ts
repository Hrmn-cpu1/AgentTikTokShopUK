import { describe, expect, it } from 'vitest';
import { prepareAssistedExecution, type AssistedExecutionInput } from './assistedExecution';

const base: AssistedExecutionInput = {
  decisionId: 'DEC-001', experimentId: 'EXP-001', creativeId: 'CREATIVE-001',
  marketEligibility: 'ELIGIBLE', experimentReady: true, claimsValid: true,
  humanApproved: true, executionEnabled: true, withinCapitalLimit: true,
  withinLossLimit: true, accountRiskAcceptable: true,
};

describe('assisted execution', () => {
  it('prepares a manual publication manifest only after every execution gate passes', () => {
    const plan = prepareAssistedExecution(base);
    expect(plan.ready).toBe(true);
    expect(plan.policyDecision).toBe('ALLOW');
    expect(plan.idempotencyKey).toBe('publish:EXP-001:CREATIVE-001');
    expect(plan.manualSteps).toContain('PUBLISH_MANUALLY');
    expect(plan.manualSteps).toContain('RECORD_EXTERNAL_ID');
  });

  it('requires human approval rather than auto-publishing in V0', () => {
    const plan = prepareAssistedExecution({ ...base, humanApproved: false });
    expect(plan.ready).toBe(false);
    expect(plan.policyDecision).toBe('REQUIRE_APPROVAL');
  });

  it('blocks assisted execution when UK eligibility is incomplete', () => {
    const plan = prepareAssistedExecution({ ...base, marketEligibility: 'CONDITIONAL' });
    expect(plan.ready).toBe(false);
    expect(plan.policyDecision).toBe('BLOCK');
  });

  it('blocks publication when EXP-001 is not ready or claims are invalid', () => {
    expect(prepareAssistedExecution({ ...base, experimentReady: false }).ready).toBe(false);
    expect(prepareAssistedExecution({ ...base, claimsValid: false }).ready).toBe(false);
  });

  it('keeps kill switch and financial risk boundaries stronger than approval', () => {
    expect(prepareAssistedExecution({ ...base, executionEnabled: false }).ready).toBe(false);
    expect(prepareAssistedExecution({ ...base, withinCapitalLimit: false }).ready).toBe(false);
    expect(prepareAssistedExecution({ ...base, withinLossLimit: false }).ready).toBe(false);
  });

  it('never includes automated KYC payout or publishing operations', () => {
    const plan = prepareAssistedExecution(base);
    expect(plan.manualSteps).toEqual([
      'CONFIRM_TIKTOK_SESSION', 'CONFIRM_KYC', 'CONFIRM_AFFILIATE_ACCESS',
      'CONFIRM_PAYOUT', 'PUBLISH_MANUALLY', 'RECORD_EXTERNAL_ID',
    ]);
  });
});
