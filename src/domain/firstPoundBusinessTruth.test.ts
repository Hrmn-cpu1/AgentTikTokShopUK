import {describe,expect,it} from 'vitest';
import {deriveFirstPoundFromBusinessTruth} from './firstPoundBusinessTruth';
import {saveFrozenExp001} from './frozenExp001Store';
import {saveExperimentCost} from './experimentCostTruth';
import {saveLaunchPacket} from './launchPacketStore';
import {saveCreativeEvidencePack} from './creativeEvidencePackStore';
import {approveCreative,saveCreativeApproval} from './creativeApproval';
import {BrowserBusinessTruthStore} from './businessTruthStore';
import {RealResultIngestor} from './realResultIngestor';
import type {FrozenExp001Candidate} from './realExp001Freeze';
import type {CreativeEvidencePack} from './creativeEvidencePack';

const time='2026-09-27T13:00:00Z';
function storage():Storage{
 const map=new Map<string,string>();
 return {getItem:k=>map.get(k)??null,setItem:(k,v)=>{map.set(k,v)},removeItem:k=>{map.delete(k)},clear:()=>{map.clear()},key:i=>[...map.keys()][i]??null,get length(){return map.size}};
}
const frozen:FrozenExp001Candidate={
 experiment:{experimentId:'EXP-001',decisionId:'DEC-001',opportunityId:'p1',hypothesis:'test',variableUnderTest:'hook',controlDescription:'control',treatmentDescription:'demo',primaryMetric:'settled_realized_contribution_gbp',capitalLimit:4,lossLimit:2,durationHours:72,successThreshold:0.01,failureThreshold:0,minimumEvidence:1},
 product:{productId:'p1',listingRef:'listing:p1',productName:'Product',sellerName:'Seller',observedAt:time,priceGbp:5,commissionRate:0.1,available:true,source:'MANUAL_VERIFIED',market:'UK',currency:'GBP'},
 opportunityScore:80,decisionConfidence:80,allocationScore:80,expectedRealizedProfitGbp:2,evidenceRefs:['listing:p1'],decisionTruth:{allocationDecision:'ALLOCATE',marketEligibility:'ELIGIBLE',policyAllowed:true},frozenAt:time,
};
const creative:CreativeEvidencePack={packId:'CEP-EXP-001',experimentId:'EXP-001',decisionId:'DEC-001',productId:'p1',listingRef:'listing:p1',hypothesis:'test',variableUnderTest:'hook',strategy:{hypothesis:'test',hook:'hook',firstFrame:'frame',demo:'demo',proof:'proof',objection:'objection',offer:'offer',cta:'cta',shotList:['shot'],script:['script'],mutation:{parentCreativeId:null,variableChanged:'hook',rationale:'test'},claimsUsed:[]},claimEvidence:[],humanApprovalRequired:true,publishable:false,createdAt:time};
function prepared(){
 const s=storage();saveFrozenExp001(s,frozen);saveCreativeEvidencePack(s,creative);saveCreativeApproval(s,approveCreative(creative,time));
 saveLaunchPacket(s,{packetId:'LP-EXP-001-CEP-EXP-001',decisionId:'DEC-001',experimentId:'EXP-001',creativeId:'CEP-EXP-001',productId:'p1',listingRef:'listing:p1',creativePackId:creative.packId,idempotencyKey:'publish:EXP-001:CEP-EXP-001',manualSteps:['PUBLISH_MANUALLY'],evidenceRefs:['listing:p1'],readyForManualPublish:true,blockedReasons:[],externalPublicationId:null,createdAt:time});
 saveExperimentCost(s,{experimentId:'EXP-001',amountGbp:0,evidenceRef:'cost-receipt:0',observedAt:time});
 const ingestor=new RealResultIngestor(new BrowserBusinessTruthStore(s));
 const event=(id:string,type:'PUBLISHED'|'ORDER_CREATED'|'DELIVERED'|'COMMISSION_SETTLED'|'REFUNDED',amountGbp:number|null)=>ingestor.ingest({source:'MANUAL_VERIFIED',externalEventId:id,experimentId:'EXP-001',actionId:'LP-EXP-001-CEP-EXP-001',type,occurredAt:time,amountGbp,evidenceRef:'proof:'+id});
 return {s,event};
}
describe('first pound fact derivation',()=>{
 it('returns null without a validated publication trace',()=>{const {s,event}=prepared();event('settlement', 'COMMISSION_SETTLED',2);expect(deriveFirstPoundFromBusinessTruth(s,time)).toBeNull()});
 it('revokes proof after a refund, also after reload',()=>{const {s,event}=prepared();event('video','PUBLISHED',null);event('order','ORDER_CREATED',null);event('delivery','DELIVERED',null);event('settlement','COMMISSION_SETTLED',2);expect(deriveFirstPoundFromBusinessTruth(s,time)?.status).toBe('PROVEN');event('refund','REFUNDED',1.01);expect(deriveFirstPoundFromBusinessTruth(s,time)).toMatchObject({status:'NOT_PROVEN',realizedContributionGbp:0.99,creativeId:'CEP-EXP-001',provenAt:time})});
 it('rejects a tampered publication packet identity',()=>{const {s,event}=prepared();event('video','PUBLISHED',null);event('order','ORDER_CREATED',null);event('delivery','DELIVERED',null);event('settlement','COMMISSION_SETTLED',2);const snapshot=new BrowserBusinessTruthStore(s).load();snapshot.events[0].actionId='different-packet';new BrowserBusinessTruthStore(s).save(snapshot);expect(deriveFirstPoundFromBusinessTruth(s,time)).toBeNull()});
});
