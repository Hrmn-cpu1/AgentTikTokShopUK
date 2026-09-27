export type ConfidenceComponent = number | null;

export type ConfidenceInput = {
  sourceReliability: ConfidenceComponent;
  sampleStrength: ConfidenceComponent;
  freshness: ConfidenceComponent;
  crossSourceAgreement: ConfidenceComponent;
  attributionQuality: ConfidenceComponent;
};

export type ConfidenceResult = {
  score: number | null;
  knownWeight: number;
  coverage: number;
  state: 'KNOWN' | 'PARTIAL' | 'UNKNOWN';
  missing: (keyof ConfidenceInput)[];
};

const weights: Record<keyof ConfidenceInput, number> = {
  sourceReliability: 0.30,
  sampleStrength: 0.20,
  freshness: 0.20,
  crossSourceAgreement: 0.15,
  attributionQuality: 0.15,
};

function validate(name: string, value: ConfidenceComponent) {
  if (value === null) return;
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`${name} must be null or between 0 and 100`);
  }
}

export function calculateConfidence(input: ConfidenceInput): ConfidenceResult {
  const keys = Object.keys(weights) as (keyof ConfidenceInput)[];
  keys.forEach((key) => validate(key, input[key]));

  const known = keys.filter((key) => input[key] !== null);
  const missing = keys.filter((key) => input[key] === null);
  const knownWeight = known.reduce((sum, key) => sum + weights[key], 0);

  if (knownWeight === 0) {
    return { score: null, knownWeight: 0, coverage: 0, state: 'UNKNOWN', missing };
  }

  const weighted = known.reduce((sum, key) => sum + (input[key] as number) * weights[key], 0);
  const score = Math.round((weighted / knownWeight) * 100) / 100;
  const coverage = Math.round(knownWeight * 10000) / 100;

  return {
    score,
    knownWeight: Math.round(knownWeight * 100) / 100,
    coverage,
    state: missing.length === 0 ? 'KNOWN' : 'PARTIAL',
    missing,
  };
}

export function confidenceForDecision(result: ConfidenceResult): number {
  if (result.score === null) return 0;
  return Math.round(result.score * (result.coverage / 100) * 100) / 100;
}
