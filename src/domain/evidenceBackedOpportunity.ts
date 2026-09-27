import { evaluateRealOpportunity, type RealOpportunityResult } from './realOpportunityPipeline';
import type { RealProductRecord } from './realProductIntake';
import type { OpportunityEvidenceDossier } from './opportunityEvidenceDossier';

export function evaluateEvidenceBackedOpportunity(product:RealProductRecord,d:OpportunityEvidenceDossier,nowIso:string):RealOpportunityResult|null{
 if(d.state!=='READY') return null;
 return evaluateRealOpportunity({
  product,nowIso,
  economics:{expectedOrders:d.expectedOrders!,settlementProbability:d.settlementProbability!,experimentCost:d.experimentCostGbp!,capitalRequired:d.capitalRequiredGbp!,timeToCashDays:d.timeToCashDays!},
  confidence:d.confidence,creativePotential:d.creativePotential!,supplyReliability:d.supplyReliability!,informationValue:d.informationValue!,
  opportunityWindow:d.opportunityWindow!,riskPenalty:d.riskPenalty!,urgency:d.urgency!,
  marketEligible:true,policyAllowed:true,accountRiskAcceptable:true,expectedLoss:d.experimentCostGbp!,
  limits:{capitalLimit:Math.max(d.capitalRequiredGbp!,d.experimentCostGbp!),lossLimit:d.experimentCostGbp!},
 });
}
