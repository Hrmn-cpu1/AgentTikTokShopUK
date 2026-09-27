import { describe, expect, it } from 'vitest';
import { evaluateExperiment, validateExperiment, type ExperimentSpec } from './experimentEngine';

const spec: ExperimentSpec = {
  experimentId: 'EXP-001', decisionId: 'DEC-001', opportunityId: 'OPP-001',
  hypothesis: 'A demo-first hook improves qualified commerce intent.',
  variableUnderTest: 'hook', controlDescription: 'Problem-first hook',
  treatmentDescription: 'Product-result in first two seconds',
  primaryMetric: 'qualified_conversion_rate', capitalLimit: 8, lossLimit: 8,
  durationHours: 48, successThreshold: 5, failureThreshold: 2, minimumEvidence: 20,
};

describe('experiment engine', () => {
  it('requires traceable ids and a falsifiable experiment contract', () => {
    expect(validateExperiment(spec)).toEqual(spec);
    expect(() => validateExperiment({ ...spec, decisionId: '' })).toThrow();
  });

  it('kills immediately when capital or loss limits are breached', () => {
    expect(evaluateExperiment(spec, { metricValue: 6, evidenceCount: 30, elapsedHours: 10, spentCapital: 9, realizedLoss: 0, rewardMature: true }).status).toBe('KILLED');
    expect(evaluateExperiment(spec, { metricValue: 6, evidenceCount: 30, elapsedHours: 10, spentCapital: 8, realizedLoss: 9, rewardMature: true }).status).toBe('KILLED');
  });

  it('keeps UNKNOWN distinct from failure', () => {
    expect(evaluateExperiment(spec, { metricValue: null, evidenceCount: 0, elapsedHours: 10, spentCapital: 0, realizedLoss: 0, rewardMature: false }).status).toBe('RUNNING');
  });

  it('waits for delayed reward instead of declaring an early winner', () => {
    expect(evaluateExperiment(spec, { metricValue: 8, evidenceCount: 30, elapsedHours: 20, spentCapital: 4, realizedLoss: 0, rewardMature: false }).status).toBe('WAITING_REWARD');
  });

  it('only succeeds after evidence and mature reward meet the frozen threshold', () => {
    expect(evaluateExperiment(spec, { metricValue: 6, evidenceCount: 30, elapsedHours: 20, spentCapital: 4, realizedLoss: 0, rewardMature: true }).status).toBe('SUCCEEDED');
  });

  it('fails only on observable mature evidence below the predefined failure threshold', () => {
    expect(evaluateExperiment(spec, { metricValue: 1, evidenceCount: 30, elapsedHours: 20, spentCapital: 4, realizedLoss: 4, rewardMature: true }).status).toBe('FAILED');
  });

  it('ends inconclusive rather than inventing certainty when evidence is insufficient', () => {
    expect(evaluateExperiment(spec, { metricValue: 6, evidenceCount: 5, elapsedHours: 48, spentCapital: 4, realizedLoss: 0, rewardMature: true }).status).toBe('INCONCLUSIVE');
  });

  it('rejects overlapping or inverted success and failure thresholds', () => {
    expect(() => validateExperiment({ ...spec, successThreshold: 2, failureThreshold: 2 })).toThrow();
  });
});
