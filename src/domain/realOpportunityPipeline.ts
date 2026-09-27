import { calculateEconomics, type EconomicsInput } from './economics';
import { calculateConfidence, confidenceForDecision, type ConfidenceInput } from './confidence';
import { scoreOpportunity, type OpportunitySignals } from './opportunityRanker';
import { allocateNextShot, type AllocationLimits, type AllocationDecision } from './shotAllocator';
import { isFreshProduct, type RealProductRecord } from './realProductIntake';

export type RealOpportunityInput = {
 product: RealProductRecord;
 nowIso: string;
 economics: Omit<EconomicsInput,'paidPrice'|'commissionRate'>;
 confidence: ConfidenceInput;
 creativePotential: number;
 supplyReliability: number;
 informationValue: number;
 opportunityWindow: number;
 riskPenalty: number;
 urgency: number;
 marketEligible: boolean;
 policyAllowed: boolean;
 accountRiskAcceptable: boolean;
 expectedLoss: number;
 limits: AllocationLimits;
};

export type RealOpportunityResult = {
 productId:string;
 economics:ReturnType<typeof calculateEconomics>;
 confidence:ReturnType<typeof calculateConfidence>;
 decisionConfidence:number;
 signals:OpportunitySignals;
 opportunityScore:number;
 allocation:AllocationDecision;
 fresh:boolean;
};

const clamp100=(v:number)=>Math.max(0,Math.min(100,v));
const positiveToScore=(v:number)=>clamp100(v<=0?0:Math.round((1-Math.exp(-v/10))*10000)/100);

export function evaluateRealOpportunity(input:RealOpportunityInput):RealOpportunityResult {
 const fresh=isFreshProduct(input.product,input.nowIso);
 const economics=calculateEconomics({...input.economics,paidPrice:input.product.priceGbp,commissionRate:input.product.commissionRate});
 const confidence=calculateConfidence(input.confidence);
 const decisionConfidence=confidenceForDecision(confidence);
 const signals:OpportunitySignals={
  economicPotential:positiveToScore(economics.expectedRealizedProfit),
  cashVelocity:positiveToScore(economics.cashVelocity),
  decisionConfidence,
  creativePotential:input.creativePotential,
  supplyReliability:input.supplyReliability,
  informationValue:input.informationValue,
  opportunityWindow:fresh?input.opportunityWindow:0,
  riskPenalty:input.riskPenalty,
 };
 const opportunityScore=scoreOpportunity(signals);
 const allocation=allocateNextShot([{
  id:input.product.productId,opportunityScore,confidence:decisionConfidence,informationValue:input.informationValue,urgency:input.urgency,
  capitalRequired:input.economics.capitalRequired,expectedLoss:input.expectedLoss,marketEligible:input.marketEligible,
  policyAllowed:input.policyAllowed,supplyAcceptable:input.product.available&&fresh,accountRiskAcceptable:input.accountRiskAcceptable,
 }],input.limits);
 return {productId:input.product.productId,economics,confidence,decisionConfidence,signals,opportunityScore,allocation,fresh};
}
