export type FailureDomain =
  | 'NONE' | 'ATTENTION' | 'INTENT' | 'CONVERSION'
  | 'FULFILLMENT' | 'ECONOMICS' | 'POLICY' | 'SUPPLY' | 'FATIGUE' | 'UNKNOWN';

export type WinnerStage =
  | 'DISCOVERED' | 'ATTENTION_VALIDATED' | 'INTENT_VALIDATED'
  | 'CONVERSION_VALIDATED' | 'FULFILLMENT_VALIDATED'
  | 'PROFIT_VALIDATED' | 'REPEATABILITY_VALIDATED';

export type NextDecision = 'SCALE' | 'MUTATE' | 'WAIT' | 'KILL';

export type PerformanceEvidence = {
  attentionValidated: boolean | null;
  intentValidated: boolean | null;
  conversionValidated: boolean | null;
  fulfillmentValidated: boolean | null;
  realizedContributionGbp: number | null;
  repeatedProfitableCycles: number;
  policyAllowed: boolean;
  supplyAvailable: boolean;
  creativeFatigued: boolean;
  rewardMature: boolean;
};

export type WinnerDiagnosis = {
  winnerStage: WinnerStage;
  failureDomain: FailureDomain;
  decision: NextDecision;
  reason: string;
};

export function diagnoseOutcome(e: PerformanceEvidence): WinnerDiagnosis {
  if (!e.policyAllowed) return { winnerStage: 'DISCOVERED', failureDomain: 'POLICY', decision: 'KILL', reason: 'Policy boundary blocks continuation.' };
  if (!e.supplyAvailable) return { winnerStage: 'DISCOVERED', failureDomain: 'SUPPLY', decision: 'WAIT', reason: 'Supply is unavailable; do not spend into an unfulfillable opportunity.' };
  if (e.creativeFatigued) return { winnerStage: stageFromEvidence(e), failureDomain: 'FATIGUE', decision: 'MUTATE', reason: 'Previously useful creative evidence is fatigued.' };

  if (e.attentionValidated === false) return { winnerStage: 'DISCOVERED', failureDomain: 'ATTENTION', decision: 'MUTATE', reason: 'Attention failed; mutate the hook or first frame.' };
  if (e.attentionValidated === null) return unknown(e);

  if (e.intentValidated === false) return { winnerStage: 'ATTENTION_VALIDATED', failureDomain: 'INTENT', decision: 'MUTATE', reason: 'Attention exists but qualified commerce intent failed.' };
  if (e.intentValidated === null) return unknown(e, 'ATTENTION_VALIDATED');

  if (e.conversionValidated === false) return { winnerStage: 'INTENT_VALIDATED', failureDomain: 'CONVERSION', decision: 'MUTATE', reason: 'Intent exists but conversion failed; inspect product, offer or trust.' };
  if (e.conversionValidated === null) return unknown(e, 'INTENT_VALIDATED');

  if (e.fulfillmentValidated === false) return { winnerStage: 'CONVERSION_VALIDATED', failureDomain: 'FULFILLMENT', decision: 'KILL', reason: 'Orders do not survive fulfillment quality.' };
  if (e.fulfillmentValidated === null) return unknown(e, 'CONVERSION_VALIDATED');

  if (!e.rewardMature || e.realizedContributionGbp === null) {
    return { winnerStage: 'FULFILLMENT_VALIDATED', failureDomain: 'UNKNOWN', decision: 'WAIT', reason: 'Commerce is validated but economic reward is not mature.' };
  }

  if (e.realizedContributionGbp <= 0) {
    return { winnerStage: 'FULFILLMENT_VALIDATED', failureDomain: 'ECONOMICS', decision: 'KILL', reason: 'Settled realized contribution is not positive.' };
  }

  if (e.repeatedProfitableCycles >= 2) {
    return { winnerStage: 'REPEATABILITY_VALIDATED', failureDomain: 'NONE', decision: 'SCALE', reason: 'Positive settled economics repeated across controlled cycles.' };
  }

  return { winnerStage: 'PROFIT_VALIDATED', failureDomain: 'NONE', decision: 'WAIT', reason: 'Profit is validated once; repeatability still needs another controlled cycle.' };
}

function unknown(e: PerformanceEvidence, stage: WinnerStage = 'DISCOVERED'): WinnerDiagnosis {
  return { winnerStage: stage, failureDomain: 'UNKNOWN', decision: 'WAIT', reason: 'Evidence is incomplete; UNKNOWN is not failure and not permission to scale.' };
}

function stageFromEvidence(e: PerformanceEvidence): WinnerStage {
  if (e.realizedContributionGbp !== null && e.realizedContributionGbp > 0 && e.rewardMature) {
    return e.repeatedProfitableCycles >= 2 ? 'REPEATABILITY_VALIDATED' : 'PROFIT_VALIDATED';
  }
  if (e.fulfillmentValidated) return 'FULFILLMENT_VALIDATED';
  if (e.conversionValidated) return 'CONVERSION_VALIDATED';
  if (e.intentValidated) return 'INTENT_VALIDATED';
  if (e.attentionValidated) return 'ATTENTION_VALIDATED';
  return 'DISCOVERED';
}
