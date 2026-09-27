import { evaluateRealOpportunity, type RealOpportunityInput, type RealOpportunityResult } from './realOpportunityPipeline';
import type { RealProductRecord } from './realProductIntake';
import type { OpportunityEvidenceDossier } from './opportunityEvidenceDossier';
import type { OpportunityAuthority } from './opportunityAuthority';
import type { CapitalAuthority } from './capitalAuthority';

export function buildEvidenceBackedOpportunityInput(product:RealProductRecord,d:OpportunityEvidenceDossier,nowIso:string,authority?:OpportunityAuthority,capitalAuthority?:CapitalAuthority):RealOpportunityInput|null{
 if(d.state!=='READY'||!authority||!capitalAuthority) return null;
 return {
  product,nowIso,
  economics:{expectedOrders:d.expectedOrders!,settlementProbability:d.settlementProbability!,experimentCost:d.experimentCostGbp!,capitalRequired:d.capitalRequiredGbp!,timeToCashDays:d.timeToCashDays!},
  confidence:d.confidence,creativePotential:d.creativePotential!,supplyReliability:d.supplyReliability!,informationValue:d.informationValue!,
  opportunityWindow:d.opportunityWindow!,riskPenalty:d.riskPenalty!,urgency:d.urgency!,
  marketEligible:authority.marketEligible,policyAllowed:authority.policyAllowed,accountRiskAcceptable:authority.accountRiskAcceptable,expectedLoss:d.experimentCostGbp!,
  limits:capitalAuthority.limits,
 };
}
export function evaluateEvidenceBackedOpportunity(product:RealProductRecord,d:OpportunityEvidenceDossier,nowIso:string,authority?:OpportunityAuthority,capitalAuthority?:CapitalAuthority):RealOpportunityResult|null{
 const input=buildEvidenceBackedOpportunityInput(product,d,nowIso,authority,capitalAuthority);
 return input?evaluateRealOpportunity(input):null;
}
