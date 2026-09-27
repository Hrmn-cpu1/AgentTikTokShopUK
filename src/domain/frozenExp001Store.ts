import type {FrozenExp001Candidate} from './realExp001Freeze';
export const FROZEN_EXP001_STORAGE_KEY='tiktok-profit-agent:frozen-exp001:v1';

function validate(x:FrozenExp001Candidate):FrozenExp001Candidate{
 if(x.experiment.experimentId!=='EXP-001'||x.experiment.decisionId!=='DEC-001')throw new Error('Invalid EXP-001 identity');
 if(!x.product.productId||x.experiment.opportunityId!==x.product.productId)throw new Error('Frozen product trace mismatch');
 if(!Number.isFinite(Date.parse(x.frozenAt)))throw new Error('Invalid frozenAt');
 if(x.evidenceRefs.length===0)throw new Error('Frozen evidence required');
 return Object.freeze(structuredClone(x));
}
export function saveFrozenExp001(storage:Pick<Storage,'setItem'>,frozen:FrozenExp001Candidate){const safe=validate(frozen);storage.setItem(FROZEN_EXP001_STORAGE_KEY,JSON.stringify(safe));return safe}
export function loadFrozenExp001(storage:Pick<Storage,'getItem'>):FrozenExp001Candidate|null{const raw=storage.getItem(FROZEN_EXP001_STORAGE_KEY);if(!raw)return null;try{return validate(JSON.parse(raw) as FrozenExp001Candidate)}catch{return null}}
