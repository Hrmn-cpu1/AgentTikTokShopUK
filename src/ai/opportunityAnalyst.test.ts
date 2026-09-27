import { describe, expect, it } from 'vitest';
import {
  OPPORTUNITY_ANALYST_SYSTEM,
  buildOpportunityAnalystInput,
  validateOpportunityAnalysis,
  type AnalystContext,
} from './opportunityAnalyst';

const context: AnalystContext = {
  market: 'UK', currency: 'GBP', productName: 'Demo Product',
  opportunityScore: 73.5, expectedRealizedProfit: 27.99, cashVelocity: 0.87,
  confidenceScore: 78, confidenceCoverage: 100, allocationDecision: 'ALLOCATE',
  marketEligibility: 'ELIGIBLE', evidenceSummary: ['direct seller listing'],
  knownRisks: ['returns unknown'], unknowns: ['settlement rate'],
};

describe('opportunity analyst boundary', () => {
  it('preserves deterministic context without recalculating it', () => {
    const input = buildOpportunityAnalystInput(context);
    expect(input.context).toEqual(context);
    expect(input.context).not.toBe(context);
  });

  it('freezes the critical commercial and authority invariants into the analyst contract', () => {
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('VIRAL != WINNER');
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('LLM reasoning is not authorization');
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('Never change deterministic economics');
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('NO_ACTION');
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('settlement');
  });

  it('explicitly blocks real-money execution when UK eligibility is not ELIGIBLE', () => {
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('marketEligibility is not ELIGIBLE');
    expect(OPPORTUNITY_ANALYST_SYSTEM).toContain('real-money UK execution remains blocked');
  });

  it('requires structured analysis fields', () => {
    expect(validateOpportunityAnalysis({
      thesis: 'Test demand cheaply', whyNow: 'Evidence window is current',
      strengths: ['demonstrable'], risks: ['returns'], unknowns: ['settlement'],
      recommendedHypothesis: 'Demo-first hook increases intent',
      recommendedTest: 'One controlled organic creative',
      doNotAssume: ['orders equal profit'],
    }).thesis).toBe('Test demand cheaply');
  });

  it('rejects incomplete structured output', () => {
    expect(() => validateOpportunityAnalysis({
      thesis: '', whyNow: 'now', strengths: [], risks: [], unknowns: [],
      recommendedHypothesis: 'h', recommendedTest: 't', doNotAssume: [],
    })).toThrow();
  });
});
