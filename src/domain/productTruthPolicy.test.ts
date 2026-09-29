import { describe, expect, it } from 'vitest';
import { assertPublishableClaims, resolveClaim, type ProductTruthRecord } from './productTruth';
import { evaluateAction, type PolicyContext } from './policyEngine';

const truth: ProductTruthRecord = {
  productId: 'P-1',
  claims: [
    { text: 'Portable', state: 'VERIFIED', sourceRefs: ['seller-page'] },
    { text: 'Includes cable', state: 'SUPPORTED', sourceRefs: ['manual'] },
    { text: 'Guaranteed results', state: 'BLOCKED', sourceRefs: ['policy'] },
  ],
};

const safe: PolicyContext = {
  executionEnabled: true, marketEligible: true, claimsValid: true, humanApproved: false,
  withinCapitalLimit: true, withinLossLimit: true, accountRiskAcceptable: true,
};

describe('product truth and policy gate', () => {
  it('keeps missing claims UNKNOWN instead of treating absence as false or safe', () => {
    expect(resolveClaim(truth, 'Waterproof')).toBe('UNKNOWN');
  });

  it('allows only verified or supported claims to cross the publication boundary', () => {
    expect(() => assertPublishableClaims(truth, ['Portable', 'Includes cable'])).not.toThrow();
    expect(() => assertPublishableClaims(truth, ['Waterproof'])).toThrow('Unknown claim');
    expect(() => assertPublishableClaims(truth, ['Guaranteed results'])).toThrow('Blocked claim');
  });

  it('requires human approval for external execution in V0', () => {
    expect(evaluateAction('PUBLISH', safe)).toBe('REQUIRE_APPROVAL');
    expect(evaluateAction('PUBLISH', { ...safe, humanApproved: true })).toBe('ALLOW');
  });

  it('makes the kill switch stronger than human approval', () => {
    expect(evaluateAction('PUBLISH', { ...safe, humanApproved: true, executionEnabled: false })).toBe('BLOCK');
  });

  it('blocks external action when eligibility, claims, risk or financial limits fail', () => {
    expect(evaluateAction('SPEND', { ...safe, humanApproved: true, marketEligible: false })).toBe('BLOCK');
    expect(evaluateAction('PUBLISH', { ...safe, humanApproved: true, claimsValid: false })).toBe('BLOCK');
    expect(evaluateAction('PUBLISH', { ...safe, humanApproved: true, accountRiskAcceptable: false })).toBe('BLOCK');
    expect(evaluateAction('SPEND', { ...safe, humanApproved: true, withinLossLimit: false })).toBe('BLOCK');
  });

  it('keeps withdrawal transfer and payout changes forbidden in V0', () => {
    expect(evaluateAction('WITHDRAW', safe)).toBe('BLOCK');
    expect(evaluateAction('TRANSFER', safe)).toBe('BLOCK');
    expect(evaluateAction('CHANGE_PAYOUT', safe)).toBe('BLOCK');
  });

  it('lets safe internal reasoning proceed while deferring invalid creative drafts', () => {
    expect(evaluateAction('ANALYZE', { ...safe, executionEnabled: false })).toBe('ALLOW');
    expect(evaluateAction('DRAFT_CREATIVE', { ...safe, claimsValid: false })).toBe('DEFER');
  });
});
