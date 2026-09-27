import { describe, expect, it } from 'vitest';
import { buildDecisionMoneyTrace, type DecisionMoneyInput } from './decisionMoney';
import type { CommerceEvent } from './actionEventLedger';

const event = (type: CommerceEvent['type'], id: string, amountGbp: number | null = null, experimentId = 'EXP-001'): CommerceEvent => ({
  eventId: id, source: 'manual', externalEventId: id, experimentId, actionId: 'ACT-1',
  type, occurredAt: '2026-09-27T10:00:00Z', amountGbp,
});

const base: DecisionMoneyInput = {
  decisionId: 'DEC-001', experimentId: 'EXP-001', opportunityId: 'OPP-001',
  allocationDecision: 'ALLOCATE', marketEligibility: 'ELIGIBLE', policyAllowed: true,
  experimentCostsGbp: 2,
  events: [],
  performance: {
    attentionValidated: true, intentValidated: true, conversionValidated: true,
    fulfillmentValidated: true, repeatedProfitableCycles: 1,
    supplyAvailable: true, creativeFatigued: false,
  },
};

describe('decision to money trace', () => {
  it('keeps decision truth separate from missing economic truth', () => {
    const trace = buildDecisionMoneyTrace(base);
    expect(trace.decisionTruth.executable).toBe(true);
    expect(trace.economicTruth.realizedContributionGbp).toBeNull();
    expect(trace.outcome.nextDecision).toBe('WAIT');
  });

  it('never turns an order into realized contribution', () => {
    const trace = buildDecisionMoneyTrace({ ...base, events: [event('ORDER_CREATED','o')] });
    expect(trace.executionTruth.highestStage).toBe('ORDER');
    expect(trace.economicTruth.settledCommissionGbp).toBeNull();
    expect(trace.economicTruth.realizedContributionGbp).toBeNull();
  });

  it('computes realized contribution only from settled commission minus experiment costs', () => {
    const trace = buildDecisionMoneyTrace({ ...base, events: [event('COMMISSION_SETTLED','s',7)] });
    expect(trace.economicTruth).toEqual({ settledCommissionGbp: 7, experimentCostsGbp: 2, realizedContributionGbp: 5 });
    expect(trace.outcome).toMatchObject({ winnerStage: 'PROFIT_VALIDATED', nextDecision: 'WAIT' });
  });

  it('scales only when profitable settled economics are repeated', () => {
    const trace = buildDecisionMoneyTrace({
      ...base,
      events: [event('COMMISSION_SETTLED','s',7)],
      performance: { ...base.performance, repeatedProfitableCycles: 2 },
    });
    expect(trace.outcome).toMatchObject({ winnerStage: 'REPEATABILITY_VALIDATED', nextDecision: 'SCALE' });
  });

  it('turns settled non-positive contribution into an economics kill', () => {
    const trace = buildDecisionMoneyTrace({ ...base, events: [event('COMMISSION_SETTLED','s',1)] });
    expect(trace.economicTruth.realizedContributionGbp).toBe(-1);
    expect(trace.outcome).toMatchObject({ failureDomain: 'ECONOMICS', nextDecision: 'KILL' });
  });

  it('filters foreign experiment events out of the economic trace', () => {
    const trace = buildDecisionMoneyTrace({
      ...base,
      events: [event('COMMISSION_SETTLED','foreign',100,'EXP-999'), event('ORDER_CREATED','local')],
    });
    expect(trace.executionTruth.observedEvents).toBe(1);
    expect(trace.economicTruth.realizedContributionGbp).toBeNull();
  });

  it('never marks a blocked market or NO_ACTION decision executable', () => {
    expect(buildDecisionMoneyTrace({ ...base, marketEligibility: 'BLOCKED' }).decisionTruth.executable).toBe(false);
    expect(buildDecisionMoneyTrace({ ...base, allocationDecision: 'NO_ACTION' }).decisionTruth.executable).toBe(false);
  });

  it('preserves zero settlement as known economic truth', () => {
    const trace = buildDecisionMoneyTrace({ ...base, experimentCostsGbp: 0, events: [event('COMMISSION_SETTLED','s',0)] });
    expect(trace.economicTruth).toEqual({ settledCommissionGbp: 0, experimentCostsGbp: 0, realizedContributionGbp: 0 });
    expect(trace.outcome.nextDecision).toBe('KILL');
  });
});
