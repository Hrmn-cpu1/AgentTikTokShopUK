export type PolicyDecision = 'ALLOW' | 'REQUIRE_APPROVAL' | 'DEFER' | 'BLOCK';

export type ActionKind =
  | 'ANALYZE' | 'SCORE' | 'DRAFT_CREATIVE'
  | 'PUBLISH' | 'SPEND' | 'SEND_EXTERNAL_MESSAGE'
  | 'MODIFY_ACCOUNT' | 'WITHDRAW' | 'TRANSFER' | 'CHANGE_PAYOUT';

export type PolicyContext = {
  executionEnabled: boolean;
  marketEligible: boolean;
  claimsValid: boolean;
  humanApproved: boolean;
  withinCapitalLimit: boolean;
  withinLossLimit: boolean;
  accountRiskAcceptable: boolean;
};

const external = new Set<ActionKind>(['PUBLISH','SPEND','SEND_EXTERNAL_MESSAGE','MODIFY_ACCOUNT']);
const forbiddenV0 = new Set<ActionKind>(['WITHDRAW','TRANSFER','CHANGE_PAYOUT']);

export function evaluateAction(action: ActionKind, context: PolicyContext): PolicyDecision {
  if (forbiddenV0.has(action)) return 'BLOCK';

  if (external.has(action)) {
    if (!context.executionEnabled) return 'BLOCK';
    if (!context.marketEligible || !context.claimsValid || !context.accountRiskAcceptable) return 'BLOCK';
    if (!context.withinCapitalLimit || !context.withinLossLimit) return 'BLOCK';
    if (!context.humanApproved) return 'REQUIRE_APPROVAL';
    return 'ALLOW';
  }

  if (action === 'DRAFT_CREATIVE' && !context.claimsValid) return 'DEFER';
  return 'ALLOW';
}
