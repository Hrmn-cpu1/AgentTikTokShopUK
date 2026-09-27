import {evaluateAction} from './policyEngine';import type {CapitalAuthority} from './capitalAuthority';import type {RepeatabilityVerdict} from './repeatabilityGate';
export type ScaleGateStatus='BLOCKED'|'REQUIRE_APPROVAL'|'READY_FOR_MANUAL_SCALE';
export type ScaleProposal={additionalCapitalGbp:number;maximumLossGbp:number;evidenceRef:string};
export type ScaleGateInput={repeatability:RepeatabilityVerdict;capital:CapitalAuthority|null;proposal:ScaleProposal;executionEnabled:boolean;marketEligible:boolean;accountRiskAcceptable:boolean;claimsValid:boolean;humanApproved:boolean};
export type ScaleGateVerdict={status:ScaleGateStatus;policyDecision:'BLOCK'|'REQUIRE_APPROVAL'|'ALLOW';externalExecutionAllowed:false;reasons:string[]};
export function evaluateScaleAuthority(i:ScaleGateInput):ScaleGateVerdict{
 const reasons:string[]=[];
 if(!i.repeatability.repeatableWinnerProven)reasons.push('REPEATABILITY_NOT_PROVEN');
 if(!i.capital)reasons.push('CAPITAL_AUTHORITY_MISSING');
 if(!Number.isFinite(i.proposal.additionalCapitalGbp)||i.proposal.additionalCapitalGbp<0||!Number.isFinite(i.proposal.maximumLossGbp)||i.proposal.maximumLossGbp<0||!i.proposal.evidenceRef.trim())reasons.push('INVALID_SCALE_PROPOSAL');
 const withinCapital=Boolean(i.capital)&&i.proposal.additionalCapitalGbp<=i.capital!.limits.capitalLimit&&i.proposal.additionalCapitalGbp<=i.capital!.limits.availableCapital;
 const withinLoss=Boolean(i.capital)&&i.proposal.maximumLossGbp<=i.capital!.limits.lossLimit;
 if(i.capital&&!withinCapital)reasons.push('CAPITAL_LIMIT_EXCEEDED');if(i.capital&&!withinLoss)reasons.push('LOSS_LIMIT_EXCEEDED');
 const policy=evaluateAction('SPEND',{executionEnabled:i.executionEnabled,marketEligible:i.marketEligible,claimsValid:i.claimsValid,humanApproved:i.humanApproved,withinCapitalLimit:withinCapital,withinLossLimit:withinLoss,accountRiskAcceptable:i.accountRiskAcceptable});
 if(policy==='BLOCK')reasons.push('POLICY_BLOCK');
 if(reasons.length)return Object.freeze({status:'BLOCKED',policyDecision:'BLOCK',externalExecutionAllowed:false,reasons:[...new Set(reasons)]});
 if(policy==='REQUIRE_APPROVAL')return Object.freeze({status:'REQUIRE_APPROVAL',policyDecision:policy,externalExecutionAllowed:false,reasons:['HUMAN_APPROVAL_REQUIRED']});
 return Object.freeze({status:'READY_FOR_MANUAL_SCALE',policyDecision:'ALLOW',externalExecutionAllowed:false,reasons:[]});
}
