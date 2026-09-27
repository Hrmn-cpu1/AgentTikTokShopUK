import { evaluateRealOpportunity, type RealOpportunityResult } from './realOpportunityPipeline';
import type { RealProductRecord } from './realProductIntake';
import type { OpportunityEvidenceDossier } from './opportunityEvidenceDossier';
import type { OpportunityAuthority } from './opportunityAuthority';

export function evaluateEvidenceBackedOpportunity(product:RealProductRecord,d:OpportunityEvidenceDossier,nowIso:string,authority?:OpportunityAuthority):RealOpportunityResult|null{
 if(d.state!=='READY'||!authority) return null;
 return evaluateRealOpportunity({
  product,nowIso,
  economics:{expectedOrders:d.expectedOrders!,settlementProbability:d.settlementProbability!,experimentCost:d.experimentCostGbp!,capitalRequired:d.capitalRequiredGbp!,timeToCashDays:d.timeToCashDays!},
  confidence:d.confidence,creativePotential:d.creativePotential!,supplyReliability:d.supplyReliability!,informationValue:d.informationValue!,
  opportunityWindow:d.opportunityWindow!,riskPenalty:d.riskPenalty!,urgency:d.urgency!,
  marketEligible:authority.marketEligible,policyAllowed:authority.policyAllowed,accountRiskAcceptable:authority.accountRiskAcceptable,expectedLoss:d.experimentCostGbp!,
  limits:{capitalLimit:Math.max(d.capitalRequiredGbp!,d.experimentCostGbp!),availableCapital:Math.max(d.capitalRequiredGbp!,d.experimentCostGbp!),lossLimit:d.experimentCostGbp!,minimumAllocationScore:0},
 });
}
