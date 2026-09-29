import type {OpportunityEvidenceInput} from './opportunityEvidenceDossier';

export type OpportunityEvidenceDraft=Record<
 'expectedOrders'|'settlementProbability'|'experimentCostGbp'|'capitalRequiredGbp'|'timeToCashDays'|
 'creativePotential'|'supplyReliability'|'informationValue'|'opportunityWindow'|'riskPenalty'|'urgency'|
 'sourceReliability'|'sampleStrength'|'freshness'|'crossSourceAgreement'|'attributionQuality',string>&{evidenceRefs:string};

const n=(v:string)=>v.trim()===''?null:Number(v);
export function parseOpportunityEvidenceDraft(d:OpportunityEvidenceDraft):OpportunityEvidenceInput{
 return {
  expectedOrders:n(d.expectedOrders),settlementProbability:n(d.settlementProbability),experimentCostGbp:n(d.experimentCostGbp),
  capitalRequiredGbp:n(d.capitalRequiredGbp),timeToCashDays:n(d.timeToCashDays),creativePotential:n(d.creativePotential),
  supplyReliability:n(d.supplyReliability),informationValue:n(d.informationValue),opportunityWindow:n(d.opportunityWindow),
  riskPenalty:n(d.riskPenalty),urgency:n(d.urgency),
  confidence:{sourceReliability:n(d.sourceReliability),sampleStrength:n(d.sampleStrength),freshness:n(d.freshness),crossSourceAgreement:n(d.crossSourceAgreement),attributionQuality:n(d.attributionQuality)},
  evidenceRefs:d.evidenceRefs.split('\n').map(x=>x.trim()).filter(Boolean),
 };
}
