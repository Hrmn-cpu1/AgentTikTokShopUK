import { describe, expect, it } from 'vitest';
import { deriveLearning, LearningMemory, type LearningInput } from './learningLoop';

const diagnosis = {
  winnerStage: 'PROFIT_VALIDATED',
  failureDomain: 'NONE',
  decision: 'WAIT',
  reason: 'Profit once; repeatability pending.',
} as const;

const base: LearningInput = {
  learningId: 'LEARN-001', decisionId: 'DEC-001', experimentId: 'EXP-001',
  opportunityId: 'OPP-001', creativeId: 'CREATIVE-001',
  hypothesis: 'Result-first demo improves qualified commerce intent.',
  variableUnderTest: 'hook', market: 'UK',
  settledCommissionGbp: 7, realizedContributionGbp: 5,
  refunded: false, rewardMature: true, diagnosis,
  evidenceRefs: ['creator-center:earnings:settle-1'],
};

describe('learning loop', () => {
  it('learns from positive settled contribution without declaring one cycle reusable', () => {
    const r = deriveLearning(base);
    expect(r).toMatchObject({ outcome: 'PROFIT', reusable: false, nextDecision: 'WAIT' });
  });

  it('promotes learning to reusable only after repeatability is validated', () => {
    const r = deriveLearning({ ...base, diagnosis: { ...diagnosis, winnerStage: 'REPEATABILITY_VALIDATED', decision: 'SCALE' } });
    expect(r).toMatchObject({ outcome: 'PROFIT', reusable: true, nextDecision: 'SCALE' });
  });

  it('learns from loss and break-even instead of discarding failed economics', () => {
    expect(deriveLearning({ ...base, realizedContributionGbp: -2 }).outcome).toBe('LOSS');
    expect(deriveLearning({ ...base, realizedContributionGbp: 0 }).outcome).toBe('BREAK_EVEN');
  });

  it('records refund as its own outcome and never reusable winner knowledge', () => {
    const r = deriveLearning({ ...base, refunded: true, diagnosis: { ...diagnosis, winnerStage: 'REPEATABILITY_VALIDATED', decision: 'SCALE' } });
    expect(r).toMatchObject({ outcome: 'REFUND', reusable: false });
  });

  it('keeps immature reward distinct from zero', () => {
    const r = deriveLearning({ ...base, rewardMature: false, settledCommissionGbp: null, realizedContributionGbp: null });
    expect(r).toMatchObject({ outcome: 'IMMATURE', realizedContributionGbp: null, reusable: false });
  });

  it('requires evidence provenance before creating durable learning', () => {
    expect(() => deriveLearning({ ...base, evidenceRefs: [] })).toThrow();
  });

  it('stores learning idempotently', () => {
    const memory = new LearningMemory();
    const record = deriveLearning(base);
    expect(memory.remember(record).duplicate).toBe(false);
    expect(memory.remember(record).duplicate).toBe(true);
  });

  it('returns only repeatability-validated reusable knowledge', () => {
    const memory = new LearningMemory();
    memory.remember(deriveLearning(base));
    memory.remember(deriveLearning({
      ...base, learningId: 'LEARN-002',
      diagnosis: { ...diagnosis, winnerStage: 'REPEATABILITY_VALIDATED', decision: 'SCALE' },
    }));
    expect(memory.reusableLearnings().map((x) => x.learningId)).toEqual(['LEARN-002']);
  });
});
