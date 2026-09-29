import {describe,expect,it} from 'vitest';
import {buildRealControlPlaneState} from './realControlPlane';
const ok={marketEligible:true,accountRiskAcceptable:true,policyAllowed:true,evidenceIds:['e'],blockers:[]};
const cap={limits:{availableCapital:20,capitalLimit:8,lossLimit:5,minimumAllocationScore:65},approvedAt:'2026-09-27T05:00:00Z',evidenceRef:'operator-budget:1'};
describe('real control plane',()=>{
 it('fails closed without capital authority',()=>{const x=buildRealControlPlaneState(ok,null);expect(x.readyForOpportunityEvaluation).toBe(false);expect(x.blockers).toContain('CAPITAL_AUTHORITY:MISSING')});
 it('requires independent account risk authority',()=>expect(buildRealControlPlaneState({...ok,accountRiskAcceptable:false,blockers:['ACCOUNT_RISK:UNKNOWN']},cap).readyForOpportunityEvaluation).toBe(false));
 it('becomes evaluation-ready only when all authorities pass',()=>expect(buildRealControlPlaneState(ok,cap).readyForOpportunityEvaluation).toBe(true));
});
