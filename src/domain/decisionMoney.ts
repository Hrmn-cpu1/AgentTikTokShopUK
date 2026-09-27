import type { CommerceEvent } from './actionEventLedger';
import { resolveReward } from './rewardResolver';
import { realizedContribution } from './economics';
import { diagnoseOutcome, type PerformanceEvidence } from './failureWinnerEngine';

export type DecisionMoneyInput = {
  decisionId: string;
  experimentId: string;
  opportunityId: string;
  allocationDecision: 'ALLOCATE' | 'NO_ACTION';
  marketEligibility: 'ELIGIBLE' | 'CONDITIONAL' | 'BLOCKED' | 'UNKNOWN';
  policyAllowed: boolean;
  experimentCostsGbp: number;
  events: CommerceEvent[];
  performance: Omit<PerformanceEvidence, 'realizedContributionGbp' | 'rewardMature' | 'policyAllowed'>;
};

export type DecisionMoneyTrace = {
  decisionTruth: {
    decisionId: string;
    experimentId: string;
    opportunityId: string;
    allocationDecision: 'ALLOCATE' | 'NO_ACTION';
    executable: boolean;
  };
  executionTruth: {
    observedEvents: number;
    highestStage: string;
    rewardMaturity: string;
    economicTruthKnown: boolean;
  };
  economicTruth: {
    settledCommissionGbp: number | null;
    experimentCostsGbp: number;
    realizedContributionGbp: number | null;
  };
  outcome: {
    winnerStage: string;
    failureDomain: string;
    nextDecision: string;
    reason: string;
  };
};

function money(value: number) {
  if (!Number.isFinite(value) || value < 0) throw new Error('experimentCostsGbp must be finite and non-negative');
  return Math.round(value * 100) / 100;
}

export function buildDecisionMoneyTrace(input: DecisionMoneyInput): DecisionMoneyTrace {
  if (!input.decisionId || !input.experimentId || !input.opportunityId) throw new Error('Decision, experiment and opportunity ids are required');

  const executable =
    input.allocationDecision === 'ALLOCATE' &&
    input.marketEligibility === 'ELIGIBLE' &&
    input.policyAllowed;

  const relevantEvents = input.events.filter((event) => event.experimentId === input.experimentId);
  const reward = resolveReward(relevantEvents);
  const costs = money(input.experimentCostsGbp);

  const contribution = reward.economicTruthKnown
    ? realizedContribution(reward.settledCommissionGbp, costs)
    : null;

  const diagnosis = diagnoseOutcome({
    ...input.performance,
    policyAllowed: input.policyAllowed,
    rewardMature: reward.economicTruthKnown,
    realizedContributionGbp: contribution,
  });

  return {
    decisionTruth: {
      decisionId: input.decisionId,
      experimentId: input.experimentId,
      opportunityId: input.opportunityId,
      allocationDecision: input.allocationDecision,
      executable,
    },
    executionTruth: {
      observedEvents: relevantEvents.length,
      highestStage: reward.stage,
      rewardMaturity: reward.maturity,
      economicTruthKnown: reward.economicTruthKnown,
    },
    economicTruth: {
      settledCommissionGbp: reward.economicTruthKnown ? reward.settledCommissionGbp : null,
      experimentCostsGbp: costs,
      realizedContributionGbp: contribution,
    },
    outcome: {
      winnerStage: diagnosis.winnerStage,
      failureDomain: diagnosis.failureDomain,
      nextDecision: diagnosis.decision,
      reason: diagnosis.reason,
    },
  };
}
