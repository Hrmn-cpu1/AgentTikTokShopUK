import type {ProductTruthRecord,TruthState} from './productTruth';
export const PRODUCT_TRUTH_STORAGE_KEY='tiktok-profit-agent:product-truth:v1';
const allowed=new Set<TruthState>(['VERIFIED','SUPPORTED','UNKNOWN','BLOCKED']);
function validate(x:ProductTruthRecord):ProductTruthRecord{
 if(!x.productId?.trim())throw new Error('productId required');
 for(const c of x.claims){if(!c.text?.trim()||!allowed.has(c.state))throw new Error('Invalid truth claim');if((c.state==='VERIFIED'||c.state==='SUPPORTED')&&c.sourceRefs.filter(Boolean).length===0)throw new Error('Evidence required for supported claim')}
 return Object.freeze(structuredClone(x));
}
export function saveProductTruth(storage:Pick<Storage,'setItem'>,truth:ProductTruthRecord){const safe=validate(truth);storage.setItem(PRODUCT_TRUTH_STORAGE_KEY,JSON.stringify(safe));return safe}
export function loadProductTruth(storage:Pick<Storage,'getItem'>):ProductTruthRecord|null{const raw=storage.getItem(PRODUCT_TRUTH_STORAGE_KEY);if(!raw)return null;try{return validate(JSON.parse(raw) as ProductTruthRecord)}catch{return null}}
