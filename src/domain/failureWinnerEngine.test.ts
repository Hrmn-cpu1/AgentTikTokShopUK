import { describe, expect, it } from 'vitest';
import { diagnoseOutcome, type PerformanceEvidence } from './failureWinnerEngine';

const base: PerformanceEvidence = {
  attentionValidated: true, intentValidated: true, conversionValidated: true,
  fulfillmentValidated: true, realizedContributionGbp: 5, repeatedProfitableCycles: 1,
  policyAllowed: true, supplyAvailable: true, creativeFatigued: false, rewardMature: true,
};

describe('failure and winner engine', () => {
  it('mutates the hook when attention fails', () => {
    expect(diagnoseOutcome({ ...base, attentionValidated: false })).toMatchObject({ failureDomain: 'ATTENTION', decision: 'MUTATE' });
  });

  it('diagnoses intent and conversion separately', () => {
    expect(diagnoseOutcome({ ...base, intentValidated: false })).toMatchObject({ failureDomain: 'INTENT', decision: 'MUTATE' });
    expect(diagnoseOutcome({ ...base, conversionValidated: false })).toMatchObject({ failureDomain: 'CONVERSION', decision: 'MUTATE' });
  });

  it('kills a product that converts but fails fulfillment', () => {
    expect(diagnoseOutcome({ ...base, fulfillmentValidated: false })).toMatchObject({ failureDomain: 'FULFILLMENT', decision: 'KILL' });
  });

  it('waits instead of inventing economic truth while reward is immature', () => {
    expect(diagnoseOutcome({ ...base, rewardMature: false, realizedContributionGbp: null })).toMatchObject({ winnerStage: 'FULFILLMENT_VALIDATED', decision: 'WAIT' });
  });

  it('kills settled non-positive economics even after successful commerce', () => {
    expect(diagnoseOutcome({ ...base, realizedContributionGbp: 0 })).toMatchObject({ failureDomain: 'ECONOMICS', decision: 'KILL' });
    expect(diagnoseOutcome({ ...base, realizedContributionGbp: -2 })).toMatchObject({ failureDomain: 'ECONOMICS', decision: 'KILL' });
  });

  it('does not call one profitable cycle repeatable or scale it', () => {
    expect(diagnoseOutcome(base)).toMatchObject({ winnerStage: 'PROFIT_VALIDATED', decision: 'WAIT' });
  });

  it('scales only after positive settled economics repeat', () => {
    expect(diagnoseOutcome({ ...base, repeatedProfitableCycles: 2 })).toMatchObject({ winnerStage: 'REPEATABILITY_VALIDATED', failureDomain: 'NONE', decision: 'SCALE' });
  });

  it('treats policy as a hard stop and supply as a wait state', () => {
    expect(diagnoseOutcome({ ...base, policyAllowed: false })).toMatchObject({ failureDomain: 'POLICY', decision: 'KILL' });
    expect(diagnoseOutcome({ ...base, supplyAvailable: false })).toMatchObject({ failureDomain: 'SUPPLY', decision: 'WAIT' });
  });

  it('mutates fatigued creative instead of killing proven economics', () => {
    expect(diagnoseOutcome({ ...base, repeatedProfitableCycles: 2, creativeFatigued: true })).toMatchObject({ failureDomain: 'FATIGUE', decision: 'MUTATE' });
  });

  it('keeps UNKNOWN evidence as WAIT, never failure or scale', () => {
    expect(diagnoseOutcome({ ...base, attentionValidated: null })).toMatchObject({ failureDomain: 'UNKNOWN', decision: 'WAIT' });
  });
});
