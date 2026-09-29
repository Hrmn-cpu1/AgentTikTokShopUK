import { describe, expect, it } from 'vitest';
import { rankOpportunities, scoreOpportunity, type OpportunitySignals } from './opportunityRanker';

const strong: OpportunitySignals = {
  economicPotential: 90, cashVelocity: 80, decisionConfidence: 75,
  creativePotential: 85, supplyReliability: 80, informationValue: 70,
  opportunityWindow: 80, riskPenalty: 8,
};

describe('opportunity ranker', () => {
  it('uses the frozen economic-first weighted score', () => {
    expect(scoreOpportunity(strong)).toBe(73.5);
  });

  it('penalizes weak evidence even when a product looks viral', () => {
    const viralButUnknown = { ...strong, creativePotential: 100, opportunityWindow: 100, decisionConfidence: 5 };
    expect(scoreOpportunity(viralButUnknown)).toBeLessThan(scoreOpportunity(strong));
  });

  it('applies risk as an explicit penalty', () => {
    expect(scoreOpportunity({ ...strong, riskPenalty: 40 })).toBe(41.5);
  });

  it('ranks deterministically and uses id only as a stable tie breaker', () => {
    const ranked = rankOpportunities([
      { id: 'b', signals: strong },
      { id: 'low', signals: { ...strong, economicPotential: 20 } },
      { id: 'a', signals: strong },
    ]);
    expect(ranked.map((item) => item.id)).toEqual(['a', 'b', 'low']);
  });

  it('never emits a negative score after risk', () => {
    expect(scoreOpportunity({ ...strong, riskPenalty: 100 })).toBe(0);
  });

  it('rejects malformed normalized inputs', () => {
    expect(() => scoreOpportunity({ ...strong, cashVelocity: 101 })).toThrow();
  });
});
