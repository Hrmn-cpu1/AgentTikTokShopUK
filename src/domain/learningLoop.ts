import type { WinnerDiagnosis } from './failureWinnerEngine';

export type LearningOutcome = 'PROFIT' | 'LOSS' | 'BREAK_EVEN' | 'REFUND' | 'IMMATURE';

export type LearningInput = {
  learningId: string;
  decisionId: string;
  experimentId: string;
  opportunityId: string;
  creativeId: string;
  hypothesis: string;
  variableUnderTest: string;
  market: 'UK';
  settledCommissionGbp: number | null;
  realizedContributionGbp: number | null;
  refunded: boolean;
  rewardMature: boolean;
  diagnosis: WinnerDiagnosis;
  evidenceRefs: string[];
};

export type LearningRecord = {
  learningId: string;
  trace: {
    decisionId: string;
    experimentId: string;
    opportunityId: string;
    creativeId: string;
  };
  hypothesis: string;
  variableUnderTest: string;
  market: 'UK';
  outcome: LearningOutcome;
  realizedContributionGbp: number | null;
  winnerStage: WinnerDiagnosis['winnerStage'];
  nextDecision: WinnerDiagnosis['decision'];
  reusable: boolean;
  evidenceRefs: string[];
};

export function deriveLearning(input: LearningInput): LearningRecord {
  if (!input.learningId || !input.decisionId || !input.experimentId || !input.opportunityId || !input.creativeId) {
    throw new Error('Learning requires complete trace ids');
  }
  if (input.evidenceRefs.length === 0) throw new Error('Learning requires evidence provenance');

  let outcome: LearningOutcome = 'IMMATURE';
  if (input.refunded) outcome = 'REFUND';
  else if (input.rewardMature && input.realizedContributionGbp !== null) {
    if (input.realizedContributionGbp > 0) outcome = 'PROFIT';
    else if (input.realizedContributionGbp < 0) outcome = 'LOSS';
    else outcome = 'BREAK_EVEN';
  }

  const reusable =
    input.rewardMature &&
    !input.refunded &&
    input.realizedContributionGbp !== null &&
    input.diagnosis.winnerStage === 'REPEATABILITY_VALIDATED';

  return {
    learningId: input.learningId,
    trace: {
      decisionId: input.decisionId,
      experimentId: input.experimentId,
      opportunityId: input.opportunityId,
      creativeId: input.creativeId,
    },
    hypothesis: input.hypothesis,
    variableUnderTest: input.variableUnderTest,
    market: input.market,
    outcome,
    realizedContributionGbp: input.realizedContributionGbp,
    winnerStage: input.diagnosis.winnerStage,
    nextDecision: input.diagnosis.decision,
    reusable,
    evidenceRefs: [...input.evidenceRefs],
  };
}

export class LearningMemory {
  private readonly records = new Map<string, LearningRecord>();

  remember(record: LearningRecord): { record: LearningRecord; duplicate: boolean } {
    const existing = this.records.get(record.learningId);
    if (existing) return { record: structuredClone(existing), duplicate: true };
    this.records.set(record.learningId, structuredClone(record));
    return { record: structuredClone(record), duplicate: false };
  }

  reusableLearnings(): LearningRecord[] {
    return [...this.records.values()].filter((record) => record.reusable).map((record) => structuredClone(record));
  }
}
