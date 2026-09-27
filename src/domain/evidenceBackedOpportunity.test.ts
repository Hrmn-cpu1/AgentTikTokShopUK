import {describe,expect,it} from 'vitest';
import {evaluateEvidenceBackedOpportunity} from './evidenceBackedOpportunity';
import {buildOpportunityEvidenceDossier} from './opportunityEvidenceDossier';
const p:any={productId:'P1',listingRef:'L1',productName:'P',sellerName:'S',observedAt:'2026-09-27T12:00:00Z',priceGbp:20,commissionRate:.2,available:true,source:'MANUAL_VERIFIED',market:'UK',currency:'GBP'};
const b:any={expectedOrders:1,settlementProbability:.8,experimentCostGbp:0,capitalRequiredGbp:0,timeToCashDays:5,creativePotential:70,supplyReliability:80,informationValue:80,opportunityWindow:60,riskPenalty:10,urgency:50,confidence:{sourceReliability:80,sampleStrength:50,freshness:100,crossSourceAgreement:60,attributionQuality:70},evidenceRefs:['L1']};
describe('evidence backed opportunity',()=>{
 it('refuses scoring incomplete dossiers',()=>expect(evaluateEvidenceBackedOpportunity(p,buildOpportunityEvidenceDossier({...b,expectedOrders:null}),'2026-09-27T13:00:00Z')).toBeNull());
 it('uses deterministic pipeline when dossier is complete',()=>{const r=evaluateEvidenceBackedOpportunity(p,buildOpportunityEvidenceDossier(b),'2026-09-27T13:00:00Z');expect(r?.productId).toBe('P1');expect(r?.economics.commissionPerOrder).toBe(4)});
});
