import type {CreativeEvidencePack} from './creativeEvidencePack';
export const CREATIVE_EVIDENCE_STORAGE_KEY='tiktok-profit-agent:creative-evidence-pack:v1';
function validate(x:CreativeEvidencePack):CreativeEvidencePack{
 if(x.experimentId!=='EXP-001'||x.decisionId!=='DEC-001'||!x.productId?.trim())throw new Error('Invalid creative trace');
 if(x.publishable!==false||x.humanApprovalRequired!==true)throw new Error('Creative authority escalation rejected');
 if(!Number.isFinite(Date.parse(x.createdAt)))throw new Error('Invalid createdAt');
 for(const item of x.claimEvidence)if(!item.claim.trim()||item.sourceRefs.length===0)throw new Error('Claim evidence required');
 return Object.freeze(structuredClone(x));
}
export function saveCreativeEvidencePack(storage:Pick<Storage,'setItem'>,pack:CreativeEvidencePack){const safe=validate(pack);storage.setItem(CREATIVE_EVIDENCE_STORAGE_KEY,JSON.stringify(safe));return safe}
export function loadCreativeEvidencePack(storage:Pick<Storage,'getItem'>):CreativeEvidencePack|null{const raw=storage.getItem(CREATIVE_EVIDENCE_STORAGE_KEY);if(!raw)return null;try{return validate(JSON.parse(raw) as CreativeEvidencePack)}catch{return null}}
