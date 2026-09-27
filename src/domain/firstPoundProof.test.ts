import {describe,expect,it} from 'vitest';
import {proveFirstPound} from './firstPoundProof';
import type {DecisionMoneyTrace} from './decisionMoney';
import type {PublishedLaunch} from './publishedResultCapture';

const publication:PublishedLaunch={packetId:'LP-1',experimentId:'EXP-001',creativeId:'CR-001',externalPublicationId:'video-123',publishedAt:'2026-09-27T19:00:00Z',evidenceRef:'video-proof'};
const trace=(settled:number|null,cost=0,executable=true):DecisionMoneyTrace=>({decisionTruth:{decisionId:'DEC-001',experimentId:'EXP-001',opportunityId:'P1',allocationDecision:'ALLOCATE',executable},executionTruth:{observedEvents:settled===null?1:2,highestStage:settled===null?'ORDER':'SETTLEMENT',rewardMaturity:settled===null?'PARTIAL':'FINAL',economicTruthKnown:settled!==null},economicTruth:{settledCommissionGbp:settled,experimentCostsGbp:cost,realizedContributionGbp:settled===null?null:Math.round((settled-cost)*100)/100},outcome:{winnerStage:'PROFIT_VALIDATED',failureDomain:'NONE',nextDecision:'WAIT',reason:'single profitable cycle'}});

describe('first pound proof',()=>{
 it('proves at least one pound of realized contribution after settlement',()=>{const p=proveFirstPound(trace(4.25,1),publication,['settlement-proof'],'2026-09-28T21:00:00Z');expect(p.status).toBe('PROVEN');expect(p.realizedContributionGbp).toBe(3.25)});
 it('does not prove money from an order without settlement',()=>expect(proveFirstPound(trace(null),publication,['order-proof'],'2026-09-28T21:00:00Z').status).toBe('NOT_PROVEN'));
 it('does not call sub-pound positive contribution the first pound',()=>{const p=proveFirstPound(trace(0.75,0),publication,['settlement-proof'],'2026-09-28T21:00:00Z');expect(p.status).toBe('NOT_PROVEN');expect(p.positiveContributionProven).toBe(true)});
 it('does not prove break-even settlement',()=>expect(proveFirstPound(trace(1,1),publication,['settlement-proof'],'2026-09-28T21:00:00Z').status).toBe('NOT_PROVEN'));
 it('does not prove a loss despite settled commission',()=>expect(proveFirstPound(trace(1,2),publication,['settlement-proof'],'2026-09-28T21:00:00Z').status).toBe('NOT_PROVEN'));
 it('requires executable decision truth',()=>expect(proveFirstPound(trace(4.25,0,false),publication,['settlement-proof'],'2026-09-28T21:00:00Z').status).toBe('NOT_PROVEN'));
 it('rejects cross-experiment publication trace',()=>expect(()=>proveFirstPound(trace(4.25),{...publication,experimentId:'EXP-002'},['proof'],'2026-09-28T21:00:00Z')).toThrow());
 it('never upgrades one profitable cycle to repeatable winner',()=>expect(proveFirstPound(trace(4.25),publication,['proof'],'2026-09-28T21:00:00Z').repeatableWinnerProven).toBe(false));
});
