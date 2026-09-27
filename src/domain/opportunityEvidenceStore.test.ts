import {describe,expect,it} from 'vitest';
import {loadOpportunityEvidence,saveOpportunityEvidence} from './opportunityEvidenceStore';
const input={expectedOrders:2,settlementProbability:.8,experimentCostGbp:3,capitalRequiredGbp:3,timeToCashDays:7,creativePotential:70,supplyReliability:80,informationValue:75,opportunityWindow:60,riskPenalty:10,urgency:50,confidence:{sourceReliability:90,sampleStrength:60,freshness:90,crossSourceAgreement:70,attributionQuality:80},evidenceRefs:['listing:123','seller:123']};
describe('opportunity evidence store',()=>{
 it('round trips a ready evidence dossier',()=>{let raw:string|null=null;const s={getItem:()=>raw,setItem:(_k:string,v:string)=>{raw=v}};saveOpportunityEvidence(s,input);expect(loadOpportunityEvidence(s)?.state).toBe('READY');expect(loadOpportunityEvidence(s)?.evidenceRefs).toEqual(input.evidenceRefs)});
 it('preserves UNKNOWN as incomplete instead of zero',()=>{let raw:string|null=null;const s={getItem:()=>raw,setItem:(_k:string,v:string)=>{raw=v}};saveOpportunityEvidence(s,{...input,expectedOrders:null});expect(loadOpportunityEvidence(s)?.missing).toContain('expectedOrders')});
 it('fails closed on corrupt storage',()=>expect(loadOpportunityEvidence({getItem:()=>'{bad'})).toBeNull());
});
