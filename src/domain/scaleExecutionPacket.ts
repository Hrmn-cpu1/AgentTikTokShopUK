import type {ScaleProposal,ScaleGateVerdict} from './scaleAuthorityGate';import type {CapitalAuthority} from './capitalAuthority';import type {RepeatabilityVerdict} from './repeatabilityGate';
export type ScaleApproval={approvalId:string;approvedBy:'OPERATOR';approvedAt:string;proposal:ScaleProposal;profitableExperimentIds:string[];capitalEvidenceRef:string};
export function approveScale(proposal:ScaleProposal,repeatability:RepeatabilityVerdict,capital:CapitalAuthority,approvedAt:string):ScaleApproval{
 if(!repeatability.repeatableWinnerProven||repeatability.profitableExperimentIds.length<2)throw new Error('Repeatability is not proven');
 if(!Number.isFinite(Date.parse(approvedAt)))throw new Error('approvedAt must be valid');
 return Object.freeze({approvalId:'SCALE-APP-'+repeatability.profitableExperimentIds.join('-'),approvedBy:'OPERATOR',approvedAt,proposal:structuredClone(proposal),profitableExperimentIds:[...repeatability.profitableExperimentIds].sort(),capitalEvidenceRef:capital.evidenceRef});
}
export type ScaleExecutionPacket={packetId:string;approvalId:string;createdAt:string;additionalCapitalGbp:number;maximumLossGbp:number;proposalEvidenceRef:string;capitalEvidenceRef:string;profitableExperimentIds:string[];idempotencyKey:string;readyForManualScale:true;externalExecutionAllowed:false};
export function buildScaleExecutionPacket(verdict:ScaleGateVerdict,approval:ScaleApproval,createdAt:string):ScaleExecutionPacket{
 if(verdict.status!=='READY_FOR_MANUAL_SCALE'||verdict.policyDecision!=='ALLOW')throw new Error('Scale authority is not ready');
 if(!Number.isFinite(Date.parse(createdAt)))throw new Error('createdAt must be valid');
 const ids=[...approval.profitableExperimentIds].sort();const key=['scale',ids.join(','),approval.proposal.additionalCapitalGbp.toFixed(2),approval.proposal.maximumLossGbp.toFixed(2)].join(':');
 return Object.freeze({packetId:'SCALE-PACKET-'+approval.approvalId,approvalId:approval.approvalId,createdAt,additionalCapitalGbp:approval.proposal.additionalCapitalGbp,maximumLossGbp:approval.proposal.maximumLossGbp,proposalEvidenceRef:approval.proposal.evidenceRef,capitalEvidenceRef:approval.capitalEvidenceRef,profitableExperimentIds:ids,idempotencyKey:key,readyForManualScale:true,externalExecutionAllowed:false});
}
