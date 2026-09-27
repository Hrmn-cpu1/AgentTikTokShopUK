import type {CreativeEvidencePack} from './creativeEvidencePack';
export type CreativeApproval={approvalId:string;creativePackId:string;experimentId:string;productId:string;approvedAt:string;approvedBy:'OPERATOR';};
export const CREATIVE_APPROVAL_STORAGE_KEY='tiktok-profit-agent:creative-approval:v1';
export function approveCreative(pack:CreativeEvidencePack,approvedAt:string):CreativeApproval{
 if(pack.publishable!==false||pack.humanApprovalRequired!==true)throw new Error('Creative pack authority contract invalid');
 if(!Number.isFinite(Date.parse(approvedAt)))throw new Error('approvedAt must be valid');
 return Object.freeze({approvalId:'APP-'+pack.packId,creativePackId:pack.packId,experimentId:pack.experimentId,productId:pack.productId,approvedAt,approvedBy:'OPERATOR'});
}
function validate(x:CreativeApproval){if(!x.approvalId||!x.creativePackId||x.experimentId!=='EXP-001'||!x.productId||x.approvedBy!=='OPERATOR'||!Number.isFinite(Date.parse(x.approvedAt)))throw new Error('Invalid creative approval');return Object.freeze(structuredClone(x))}
export function saveCreativeApproval(storage:Pick<Storage,'setItem'>,x:CreativeApproval){const safe=validate(x);storage.setItem(CREATIVE_APPROVAL_STORAGE_KEY,JSON.stringify(safe));return safe}
export function loadCreativeApproval(storage:Pick<Storage,'getItem'>,pack?:CreativeEvidencePack){const raw=storage.getItem(CREATIVE_APPROVAL_STORAGE_KEY);if(!raw)return null;try{const x=validate(JSON.parse(raw) as CreativeApproval);if(pack&&(x.creativePackId!==pack.packId||x.experimentId!==pack.experimentId||x.productId!==pack.productId))return null;return x}catch{return null}}
