export type ExperimentCostTruth={experimentId:'EXP-001';amountGbp:number;evidenceRef:string;observedAt:string};
export const EXPERIMENT_COST_STORAGE_KEY='tiktok-profit-agent:experiment-cost:v1';
function validate(x:ExperimentCostTruth){if(x.experimentId!=='EXP-001'||!Number.isFinite(x.amountGbp)||x.amountGbp<0||!x.evidenceRef.trim()||!Number.isFinite(Date.parse(x.observedAt)))throw new Error('Invalid observed experiment cost truth');return Object.freeze(structuredClone(x))}
export function saveExperimentCost(storage:Pick<Storage,'setItem'>,x:ExperimentCostTruth){const safe=validate(x);storage.setItem(EXPERIMENT_COST_STORAGE_KEY,JSON.stringify(safe));return safe}
export function loadExperimentCost(storage:Pick<Storage,'getItem'>){const raw=storage.getItem(EXPERIMENT_COST_STORAGE_KEY);if(!raw)return null;try{return validate(JSON.parse(raw) as ExperimentCostTruth)}catch{return null}}
