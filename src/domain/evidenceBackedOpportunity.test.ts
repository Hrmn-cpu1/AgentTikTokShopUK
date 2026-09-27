import {describe,expect,it} from 'vitest';
import {evaluateEvidenceBackedOpportunity} from './evidenceBackedOpportunity';
import {buildOpportunityEvidenceDossier} from './opportunityEvidenceDossier';
const authority:any={marketEligible:true,policyAllowed:true,accountRiskAcceptable:true,evidenceIds:['e1'],blockers:[]};
const capital:any={limits:{availableCapital:20,capitalLimit:10,lossLimit:5,minimumAllocationScore:0},approvedAt:'2026-09-27T04:00:00Z',evidenceRef:'operator-budget:1'};
const p:any={productId:'P1',listingRef:'L1',productName:'P',sellerName:'S',observedAt:'2026-09-27T12:00:00Z',priceGbp:20,commissionRate:.2,available:true,source:'MANUAL_VERIFIED',market:'UK',currency:'GBP'};
const b:any={expectedOrders:1,settlementProbability:.8,experimentCostGbp:0,capitalRequiredGbp:0,timeToCashDays:5,creativePotential:70,supplyReliability:80,informationValue:80,opportunityWindow:60,riskPenalty:10,urgency:50,confidence:{sourceReliability:80,sampleStrength:50,freshness:100,crossSourceAgreement:60,attributionQuality:70},evidenceRefs:['L1']};
describe('evidence backed opportunity',()=>{
 it('refuses scoring incomplete dossiers',()=>expect(evaluateEvidenceBackedOpportunity(p,buildOpportunityEvidenceDossier({...b,expectedOrders:null}), '2026-09-27T13:00:00Z',authority,capital)).toBeNull());
 it('uses deterministic pipeline when dossier is complete',()=>{const r=evaluateEvidenceBackedOpportunity(p,buildOpportunityEvidenceDossier(b), '2026-09-27T13:00:00Z',authority,capital);expect(r?.productId).toBe('P1');expect(r?.economics.commissionPerOrder).toBe(4)});
 it('refuses allocation when capital authority is absent',()=>expect(evaluateEvidenceBackedOpportunity(p,buildOpportunityEvidenceDossier(b),'2026-09-27T13:00:00Z',authority)).toBeNull());
 it('refuses scoring when authority is absent',()=>expect(evaluateEvidenceBackedOpportunity(p,buildOpportunityEvidenceDossier(b),'2026-09-27T13:00:00Z')).toBeNull());
});
