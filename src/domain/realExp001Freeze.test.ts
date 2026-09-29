import {describe,expect,it} from 'vitest';
import {evaluateRealOpportunity,type RealOpportunityInput} from './realOpportunityPipeline';
import {freezeRealExp001} from './realExp001Freeze';
import type {RealProductRecord} from './realProductIntake';

const product:RealProductRecord={productId:'P1',listingRef:'listing-real-1',productName:'Real Product',sellerName:'Seller',observedAt:'2026-09-27T17:00:00Z',priceGbp:20,commissionRate:.2,available:true,source:'TIKTOK_CREATOR_CENTER',market:'UK',currency:'GBP'};
const base:RealOpportunityInput={product,nowIso:'2026-09-27T18:00:00Z',economics:{expectedOrders:3,settlementProbability:.8,experimentCost:0,capitalRequired:0,timeToCashDays:4},confidence:{sourceReliability:90,sampleStrength:60,freshness:100,crossSourceAgreement:70,attributionQuality:80},creativePotential:75,supplyReliability:80,informationValue:85,opportunityWindow:80,riskPenalty:5,urgency:70,marketEligible:true,policyAllowed:true,accountRiskAcceptable:true,expectedLoss:0,limits:{availableCapital:8,capitalLimit:8,lossLimit:8,minimumAllocationScore:0}};

describe('real EXP-001 freeze',()=>{
 it('freezes an allocated real product into EXP-001',()=>{const r=evaluateRealOpportunity(base);const f=freezeRealExp001(base,r,'2026-09-27T18:01:00Z');expect(f.experiment.experimentId).toBe('EXP-001');expect(f.product.productId).toBe('P1')});
 it('preserves listing evidence and economic decision snapshot',()=>{const r=evaluateRealOpportunity(base);const f=freezeRealExp001(base,r,'2026-09-27T18:01:00Z');expect(f.evidenceRefs).toEqual(['listing-real-1']);expect(f.expectedRealizedProfitGbp).toBe(r.economics.expectedRealizedProfit)});
 it('keeps one creative variable under test',()=>{const f=freezeRealExp001(base,evaluateRealOpportunity(base),'2026-09-27T18:01:00Z');expect(f.experiment.variableUnderTest).toBe('hook')});
 it('keeps settlement contribution as primary metric',()=>{const f=freezeRealExp001(base,evaluateRealOpportunity(base),'2026-09-27T18:01:00Z');expect(f.experiment.primaryMetric).toBe('settled_realized_contribution_gbp')});
 it('refuses a NO_ACTION candidate',()=>{const blocked={...base,marketEligible:false};expect(()=>freezeRealExp001(blocked,evaluateRealOpportunity(blocked),'2026-09-27T18:01:00Z')).toThrow()});
 it('refuses stale evidence',()=>{const stale={...base,nowIso:'2026-09-30T18:00:00Z'};expect(()=>freezeRealExp001(stale,evaluateRealOpportunity(stale),'2026-09-30T18:01:00Z')).toThrow()});
 it('snapshots the product so later input mutation cannot rewrite it',()=>{const input=structuredClone(base);const f=freezeRealExp001(input,evaluateRealOpportunity(input),'2026-09-27T18:01:00Z');input.product.productName='Changed';expect(f.product.productName).toBe('Real Product')});
});
