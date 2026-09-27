import {buildOpportunityEvidenceDossier,type OpportunityEvidenceDossier,type OpportunityEvidenceInput} from './opportunityEvidenceDossier';

export const OPPORTUNITY_EVIDENCE_STORAGE_KEY='tiktok-profit-agent:opportunity-evidence:v1';

export function saveOpportunityEvidence(storage:Pick<Storage,'setItem'>,input:OpportunityEvidenceInput):OpportunityEvidenceDossier{
 const dossier=buildOpportunityEvidenceDossier(input);
 storage.setItem(OPPORTUNITY_EVIDENCE_STORAGE_KEY,JSON.stringify(dossier));
 return dossier;
}

export function loadOpportunityEvidence(storage:Pick<Storage,'getItem'>):OpportunityEvidenceDossier|null{
 const raw=storage.getItem(OPPORTUNITY_EVIDENCE_STORAGE_KEY);if(!raw)return null;
 try{
  const parsed=JSON.parse(raw) as OpportunityEvidenceInput;
  return buildOpportunityEvidenceDossier(parsed);
 }catch{return null}
}
