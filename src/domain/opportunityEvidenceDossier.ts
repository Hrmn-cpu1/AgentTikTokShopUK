import type { ConfidenceInput } from './confidence';

export type OpportunityEvidenceInput={
 expectedOrders:number|null; settlementProbability:number|null; experimentCostGbp:number|null;
 capitalRequiredGbp:number|null; timeToCashDays:number|null;
 creativePotential:number|null; supplyReliability:number|null; informationValue:number|null;
 opportunityWindow:number|null; riskPenalty:number|null; urgency:number|null;
 confidence:ConfidenceInput; evidenceRefs:string[];
};

export type OpportunityEvidenceDossier=OpportunityEvidenceInput&{
 state:'READY'|'INCOMPLETE'; missing:string[];
};

const numericKeys=['expectedOrders','settlementProbability','experimentCostGbp','capitalRequiredGbp','timeToCashDays','creativePotential','supplyReliability','informationValue','opportunityWindow','riskPenalty','urgency'] as const;

export function buildOpportunityEvidenceDossier(input:OpportunityEvidenceInput):OpportunityEvidenceDossier{
 if(input.evidenceRefs.filter(x=>x.trim()).length===0) throw new Error('Opportunity evidence requires provenance');
 const missing:string[]=[];
 for(const key of numericKeys){
  const value=input[key];
  if(value===null){missing.push(key);continue}
  if(!Number.isFinite(value)||value<0) throw new Error(key+' must be null or finite and non-negative');
 }
 if(input.settlementProbability!==null&&input.settlementProbability>1) throw new Error('settlementProbability must be between 0 and 1');
 for(const key of ['creativePotential','supplyReliability','informationValue','opportunityWindow','riskPenalty','urgency'] as const){
  const value=input[key]; if(value!==null&&value>100) throw new Error(key+' must be between 0 and 100');
 }
 for(const [key,value] of Object.entries(input.confidence)) if(value===null) missing.push('confidence.'+key);
 return Object.freeze({...input,evidenceRefs:[...new Set(input.evidenceRefs.map(x=>x.trim()).filter(Boolean))],state:missing.length?'INCOMPLETE':'READY',missing});
}
