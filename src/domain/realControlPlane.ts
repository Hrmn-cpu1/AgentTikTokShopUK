import type { CapitalAuthority } from './capitalAuthority';
import type { OpportunityAuthority } from './opportunityAuthority';

export type RealControlPlaneState={
 capitalReady:boolean;
 marketEligible:boolean;
 accountRiskAcceptable:boolean;
 policyAllowed:boolean;
 readyForOpportunityEvaluation:boolean;
 blockers:string[];
};

export function buildRealControlPlaneState(authority:OpportunityAuthority,capital:CapitalAuthority|null):RealControlPlaneState{
 const blockers=[...authority.blockers];
 if(!capital)blockers.push('CAPITAL_AUTHORITY:MISSING');
 if(!authority.policyAllowed)blockers.push('POLICY:NOT_ALLOWED');
 return Object.freeze({
  capitalReady:capital!==null,
  marketEligible:authority.marketEligible,
  accountRiskAcceptable:authority.accountRiskAcceptable,
  policyAllowed:authority.policyAllowed,
  readyForOpportunityEvaluation:capital!==null&&authority.marketEligible&&authority.accountRiskAcceptable&&authority.policyAllowed,
  blockers:[...new Set(blockers)],
 });
}
