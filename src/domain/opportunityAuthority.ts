import { evaluateAction, type PolicyContext } from './policyEngine';
import { RealityEvidenceRegistry } from './realityEvidenceRegistry';

export type OpportunityAuthority={
 marketEligible:boolean;
 accountRiskAcceptable:boolean;
 policyAllowed:boolean;
 evidenceIds:string[];
 blockers:string[];
};

export function resolveOpportunityAuthority(
 registry:RealityEvidenceRegistry,
 nowIso:string,
 context:Omit<PolicyContext,'marketEligible'|'accountRiskAcceptable'>,
):OpportunityAuthority{
 const subjects=['UK_ACCOUNT_ELIGIBILITY','IDENTITY_KYC','AFFILIATE_ACCESS'] as const;
 const states=subjects.map(subject=>registry.resolve(subject,nowIso));
 const blockers=states.filter(x=>x.state!=='VERIFIED').map(x=>x.subject+':'+x.state);
 const marketEligible=states.every(x=>x.state==='VERIFIED');
 const risk=registry.resolve('ACCOUNT_RISK',nowIso);
 const accountRiskAcceptable=risk.state==='VERIFIED';
 if(risk.state!=='VERIFIED') blockers.push('ACCOUNT_RISK:'+risk.state);
 const policy=evaluateAction('SCORE',{...context,marketEligible,accountRiskAcceptable});
 return {
  marketEligible,accountRiskAcceptable,policyAllowed:policy==='ALLOW',
  evidenceIds:[...states,risk].flatMap(x=>x.evidenceId?[x.evidenceId]:[]),blockers,
 };
}
