import {buildDecisionMoneyTrace} from './decisionMoney';import {proveFirstPound,type FirstPoundProof} from './firstPoundProof';import {loadFrozenExp001} from './frozenExp001Store';import {loadExperimentCost} from './experimentCostTruth';import {BrowserBusinessTruthStore} from './businessTruthStore';import type {PublishedLaunch} from './publishedResultCapture';
export const FIRST_POUND_STORAGE_KEY='tiktok-profit-agent:first-pound-proof:v1';
export function deriveFirstPoundFromBusinessTruth(storage:Storage,now:string):FirstPoundProof|null{
 const frozen=loadFrozenExp001(storage),cost=loadExperimentCost(storage);if(!frozen||!cost)return null;
 const events=new BrowserBusinessTruthStore(storage).load().events.filter(e=>e.experimentId==='EXP-001');
 const pub=events.find(e=>e.type==='PUBLISHED');if(!pub||!pub.externalEventId||!pub.evidenceRef)return null;
 const publication:PublishedLaunch={packetId:pub.actionId??'',experimentId:'EXP-001',creativeId:'CREATIVE-001',externalPublicationId:pub.externalEventId,publishedAt:pub.occurredAt,evidenceRef:pub.evidenceRef};
 const trace=buildDecisionMoneyTrace({decisionId:'DEC-001',experimentId:'EXP-001',opportunityId:frozen.product.productId,allocationDecision:'ALLOCATE',marketEligibility:'ELIGIBLE',policyAllowed:true,experimentCostsGbp:cost.amountGbp,events,performance:{attentionValidated:null,intentValidated:null,conversionValidated:events.some(e=>e.type==='ORDER_CREATED')?true:null,fulfillmentValidated:events.some(e=>e.type==='DELIVERED')?true:null,repeatedProfitableCycles:0,supplyAvailable:true,creativeFatigued:false}});
 const refs=[cost.evidenceRef,...events.map(e=>e.evidenceRef).filter((x):x is string=>Boolean(x))];
 return proveFirstPound(trace,publication,refs,now);
}
export function saveFirstPoundProof(storage:Pick<Storage,'setItem'>,proof:FirstPoundProof){storage.setItem(FIRST_POUND_STORAGE_KEY,JSON.stringify(proof));return Object.freeze(structuredClone(proof))}
export function loadFirstPoundProof(storage:Pick<Storage,'getItem'>):FirstPoundProof|null{const raw=storage.getItem(FIRST_POUND_STORAGE_KEY);if(!raw)return null;try{return Object.freeze(JSON.parse(raw) as FirstPoundProof)}catch{return null}}
