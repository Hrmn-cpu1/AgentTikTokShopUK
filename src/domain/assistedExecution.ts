import { evaluateAction, type PolicyContext } from './policyEngine';

export type AssistedExecutionInput = {
  decisionId: string;
  experimentId: string;
  creativeId: string;
  marketEligibility: 'ELIGIBLE' | 'CONDITIONAL' | 'BLOCKED' | 'UNKNOWN';
  experimentReady: boolean;
  claimsValid: boolean;
  humanApproved: boolean;
  executionEnabled: boolean;
  withinCapitalLimit: boolean;
  withinLossLimit: boolean;
  accountRiskAcceptable: boolean;
};

export type ManualStep =
  | 'CONFIRM_TIKTOK_SESSION'
  | 'CONFIRM_KYC'
  | 'CONFIRM_AFFILIATE_ACCESS'
  | 'CONFIRM_PAYOUT'
  | 'PUBLISH_MANUALLY'
  | 'RECORD_EXTERNAL_ID';

export type AssistedExecutionPlan = {
  ready: boolean;
  policyDecision: ReturnType<typeof evaluateAction>;
  idempotencyKey: string;
  manualSteps: ManualStep[];
  blockedReasons: string[];
};

export function prepareAssistedExecution(input: AssistedExecutionInput): AssistedExecutionPlan {
  if (!input.decisionId || !input.experimentId || !input.creativeId) throw new Error('decisionId, experimentId and creativeId are required');

  const blockedReasons: string[] = [];
  if (input.marketEligibility !== 'ELIGIBLE') blockedReasons.push('UK market eligibility is not fully proven.');
  if (!input.experimentReady) blockedReasons.push('Experiment is not READY for execution.');
  if (!input.claimsValid) blockedReasons.push('Creative claims are not validated.');

  const policy: PolicyContext = {
    executionEnabled: input.executionEnabled,
    marketEligible: input.marketEligibility === 'ELIGIBLE',
    claimsValid: input.claimsValid,
    humanApproved: input.humanApproved,
    withinCapitalLimit: input.withinCapitalLimit,
    withinLossLimit: input.withinLossLimit,
    accountRiskAcceptable: input.accountRiskAcceptable,
  };

  const policyDecision = evaluateAction('PUBLISH', policy);
  if (policyDecision === 'BLOCK') blockedReasons.push('Policy gate blocks publication.');
  if (policyDecision === 'REQUIRE_APPROVAL') blockedReasons.push('Human approval is required before manual publication.');

  const ready = input.experimentReady && policyDecision === 'ALLOW' && blockedReasons.length === 0;

  return {
    ready,
    policyDecision,
    idempotencyKey: `publish:${input.experimentId}:${input.creativeId}`,
    manualSteps: [
      'CONFIRM_TIKTOK_SESSION',
      'CONFIRM_KYC',
      'CONFIRM_AFFILIATE_ACCESS',
      'CONFIRM_PAYOUT',
      'PUBLISH_MANUALLY',
      'RECORD_EXTERNAL_ID',
    ],
    blockedReasons,
  };
}
