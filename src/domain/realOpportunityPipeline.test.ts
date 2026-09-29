import {describe,expect,it} from 'vitest';
import {evaluateRealOpportunity,type RealOpportunityInput} from './realOpportunityPipeline';
import type {RealProductRecord} from './realProductIntake';

const product:RealProductRecord={productId:'P1',listingRef:'listing-1',productName:'Real',sellerName:'Seller',observedAt:'2026-09-27T17:00:00Z',priceGbp:20,commissionRate:.2,available:true,source:'TIKTOK_CREATOR_CENTER',market:'UK',currency:'GBP'};
const base:RealOpportunityInput={product,nowIso:'2026-09-27T18:00:00Z',economics:{expectedOrders:3,settlementProbability:.8,experimentCost:0,capitalRequired:0,timeToCashDays:4},confidence:{sourceReliability:90,sampleStrength:60,freshness:100,crossSourceAgreement:null,attributionQuality:80},creativePotential:75,supplyReliability:80,informationValue:85,opportunityWindow:80,riskPenalty:5,urgency:70,marketEligible:true,policyAllowed:true,accountRiskAcceptable:true,expectedLoss:0,limits:{availableCapital:8,capitalLimit:8,lossLimit:8,minimumAllocationScore:0}};

describe('real opportunity pipeline',()=>{
 it('uses real product price and commission in economics',()=>{const r=evaluateRealOpportunity(base);expect(r.economics.commissionPerOrder).toBe(4)});
 it('penalizes partial confidence instead of inventing missing evidence',()=>{const r=evaluateRealOpportunity(base);expect(r.confidence.state).toBe('PARTIAL');expect(r.decisionConfidence).toBeLessThan(r.confidence.score!)});
 it('produces a deterministic opportunity score',()=>expect(evaluateRealOpportunity(base).opportunityScore).toBeGreaterThan(0));
 it('allocates only after deterministic gates pass',()=>expect(evaluateRealOpportunity(base).allocation.decision).toBe('ALLOCATE'));
 it('returns NO_ACTION when market eligibility is not proven',()=>expect(evaluateRealOpportunity({...base,marketEligible:false}).allocation.decision).toBe('NO_ACTION'));
 it('returns NO_ACTION for unavailable supply',()=>expect(evaluateRealOpportunity({...base,product:{...product,available:false}}).allocation.decision).toBe('NO_ACTION'));
 it('returns NO_ACTION when listing evidence is stale',()=>expect(evaluateRealOpportunity({...base,nowIso:'2026-09-29T18:00:00Z'}).allocation.decision).toBe('NO_ACTION'));
});
