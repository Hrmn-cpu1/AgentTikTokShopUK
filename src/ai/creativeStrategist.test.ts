import { describe, expect, it } from 'vitest';
import { CREATIVE_STRATEGIST_SYSTEM, buildCreativeStrategistInput, validateCreativeStrategy, type CreativeContext, type CreativeStrategy } from './creativeStrategist';

const context: CreativeContext = {
  experimentId: 'EXP-001',
  hypothesis: 'A result-first hook improves qualified commerce intent.',
  variableUnderTest: 'hook',
  productName: 'Demo Product',
  creatorArchetype: 'practical demonstrator',
  offer: 'affiliate offer',
  productTruth: {
    verifiedFacts: ['Portable'],
    supportedClaims: ['Includes USB-C cable'],
    unsupportedClaims: ['Cures pain'],
    prohibitedClaims: ['Guaranteed results'],
  },
  winnerPatterns: ['show product result early'],
  failurePatterns: ['long generic intro'],
};

const strategy: CreativeStrategy = {
  hypothesis: context.hypothesis,
  hook: 'Show the product result immediately',
  firstFrame: 'Product already in use',
  demo: 'Demonstrate one real use case',
  proof: 'Show included USB-C cable',
  objection: 'Show compact size',
  offer: 'affiliate offer',
  cta: 'See the product details',
  shotList: ['result', 'demo', 'proof', 'cta'],
  script: ['Here is the result', 'Here is how it works'],
  mutation: { parentCreativeId: 'CREATIVE-000', variableChanged: 'hook', rationale: 'Test result-first opening' },
  claimsUsed: ['Portable', 'Includes USB-C cable'],
};

describe('creative strategist boundary', () => {
  it('preserves the experiment and product truth context', () => {
    const input = buildCreativeStrategistInput(context);
    expect(input.context).toEqual(context);
    expect(input.context).not.toBe(context);
  });

  it('locks commerce and authority lessons into the strategist contract', () => {
    expect(CREATIVE_STRATEGIST_SYSTEM).toContain('Attention is not commerce truth');
    expect(CREATIVE_STRATEGIST_SYSTEM).toContain('human-native');
    expect(CREATIVE_STRATEGIST_SYSTEM).toContain('change one declared variable');
    expect(CREATIVE_STRATEGIST_SYSTEM).toContain('human approval');
  });

  it('accepts only claims grounded in ProductTruth', () => {
    expect(validateCreativeStrategy(strategy, context)).toEqual(strategy);
  });

  it('blocks unsupported or prohibited product claims', () => {
    expect(() => validateCreativeStrategy({ ...strategy, claimsUsed: ['Cures pain'] }, context)).toThrow('Unverified creative claim');
    expect(() => validateCreativeStrategy({ ...strategy, claimsUsed: ['Guaranteed results'] }, context)).toThrow('Unverified creative claim');
  });

  it('prevents the LLM from changing the experiment hypothesis', () => {
    expect(() => validateCreativeStrategy({ ...strategy, hypothesis: 'A different hypothesis' }, context)).toThrow();
  });

  it('enforces controlled mutation lineage against the declared test variable', () => {
    expect(() => validateCreativeStrategy({ ...strategy, mutation: { ...strategy.mutation, variableChanged: 'offer' } }, context)).toThrow();
  });

  it('requires an executable shot list and script', () => {
    expect(() => validateCreativeStrategy({ ...strategy, shotList: [] }, context)).toThrow();
  });
});
