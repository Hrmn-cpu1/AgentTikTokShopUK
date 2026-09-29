export type ExperimentStatus =
  | 'DRAFT' | 'READY' | 'RUNNING' | 'WAITING_REWARD'
  | 'SUCCEEDED' | 'FAILED' | 'INCONCLUSIVE' | 'KILLED';

export type ExperimentSpec = {
  experimentId: string;
  decisionId: string;
  opportunityId: string;
  hypothesis: string;
  variableUnderTest: string;
  controlDescription: string;
  treatmentDescription: string;
  primaryMetric: string;
  capitalLimit: number;
  lossLimit: number;
  durationHours: number;
  successThreshold: number;
  failureThreshold: number;
  minimumEvidence: number;
};

export type ExperimentObservation = {
  metricValue: number | null;
  evidenceCount: number;
  elapsedHours: number;
  spentCapital: number;
  realizedLoss: number;
  rewardMature: boolean;
};

export type ExperimentEvaluation = {
  status: ExperimentStatus;
  reason: string;
};

function finiteNonNegative(name: string, value: number) {
  if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must be finite and non-negative`);
}

export function validateExperiment(spec: ExperimentSpec): ExperimentSpec {
  for (const key of ['experimentId','decisionId','opportunityId','hypothesis','variableUnderTest','controlDescription','treatmentDescription','primaryMetric'] as const) {
    if (!spec[key].trim()) throw new Error(`${key} is required`);
  }
  finiteNonNegative('capitalLimit', spec.capitalLimit);
  finiteNonNegative('lossLimit', spec.lossLimit);
  finiteNonNegative('durationHours', spec.durationHours);
  finiteNonNegative('minimumEvidence', spec.minimumEvidence);
  if (spec.durationHours === 0) throw new Error('durationHours must be greater than zero');
  if (spec.successThreshold <= spec.failureThreshold) throw new Error('successThreshold must be greater than failureThreshold');
  return spec;
}

export function evaluateExperiment(spec: ExperimentSpec, observation: ExperimentObservation): ExperimentEvaluation {
  validateExperiment(spec);
  finiteNonNegative('evidenceCount', observation.evidenceCount);
  finiteNonNegative('elapsedHours', observation.elapsedHours);
  finiteNonNegative('spentCapital', observation.spentCapital);
  finiteNonNegative('realizedLoss', observation.realizedLoss);

  if (observation.spentCapital > spec.capitalLimit) return { status: 'KILLED', reason: 'Capital limit breached.' };
  if (observation.realizedLoss > spec.lossLimit) return { status: 'KILLED', reason: 'Loss limit breached.' };

  const enoughEvidence = observation.evidenceCount >= spec.minimumEvidence;
  const timeExpired = observation.elapsedHours >= spec.durationHours;

  if (observation.metricValue === null) {
    return timeExpired
      ? { status: 'INCONCLUSIVE', reason: 'Experiment ended without an observable primary metric.' }
      : { status: 'RUNNING', reason: 'Primary metric is still unknown.' };
  }

  if (!enoughEvidence) {
    return timeExpired
      ? { status: 'INCONCLUSIVE', reason: 'Experiment ended without minimum evidence.' }
      : { status: 'RUNNING', reason: 'Minimum evidence has not been reached.' };
  }

  if (!observation.rewardMature) {
    return { status: 'WAITING_REWARD', reason: 'Signal exists, but delayed economic reward is not mature.' };
  }

  if (observation.metricValue >= spec.successThreshold) {
    return { status: 'SUCCEEDED', reason: 'Primary metric met the predefined success threshold.' };
  }
  if (observation.metricValue <= spec.failureThreshold) {
    return { status: 'FAILED', reason: 'Primary metric met the predefined failure threshold.' };
  }

  return timeExpired
    ? { status: 'INCONCLUSIVE', reason: 'Metric finished between success and failure thresholds.' }
    : { status: 'RUNNING', reason: 'Metric is between thresholds and the experiment is still active.' };
}
