import type { AllocationLimits } from './shotAllocator';

export const CAPITAL_AUTHORITY_STORAGE_KEY='tiktok-profit-agent:capital-authority:v1';

export type CapitalAuthority={
 limits:AllocationLimits;
 approvedAt:string;
 evidenceRef:string;
};

function money(name:string,v:number){if(!Number.isFinite(v)||v<0)throw new Error(name+' must be finite and non-negative')}
function score(v:number){if(!Number.isFinite(v)||v<0||v>100)throw new Error('minimumAllocationScore must be between 0 and 100')}

export function createCapitalAuthority(input:CapitalAuthority):CapitalAuthority{
 money('availableCapital',input.limits.availableCapital);
 money('capitalLimit',input.limits.capitalLimit);
 money('lossLimit',input.limits.lossLimit);
 score(input.limits.minimumAllocationScore);
 if(!Number.isFinite(Date.parse(input.approvedAt)))throw new Error('approvedAt must be a valid timestamp');
 if(input.evidenceRef.trim().length<6)throw new Error('evidenceRef is required');
 return Object.freeze(structuredClone(input));
}

export function saveCapitalAuthority(storage:Pick<Storage,'setItem'>,authority:CapitalAuthority):void{
 storage.setItem(CAPITAL_AUTHORITY_STORAGE_KEY,JSON.stringify(createCapitalAuthority(authority)));
}

export function loadCapitalAuthority(storage:Pick<Storage,'getItem'>):CapitalAuthority|null{
 const raw=storage.getItem(CAPITAL_AUTHORITY_STORAGE_KEY); if(!raw)return null;
 try{return createCapitalAuthority(JSON.parse(raw) as CapitalAuthority)}catch{return null}
}
