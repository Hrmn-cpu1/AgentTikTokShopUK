import {describe,expect,it} from 'vitest';
import {buildOpportunityEvidenceDossier} from './opportunityEvidenceDossier';
const base={expectedOrders:1,settlementProbability:.8,experimentCostGbp:0,capitalRequiredGbp:0,timeToCashDays:5,creativePotential:70,supplyReliability:80,informationValue:80,opportunityWindow:60,riskPenalty:10,urgency:50,confidence:{sourceReliability:80,sampleStrength:50,freshness:100,crossSourceAgreement:60,attributionQuality:70},evidenceRefs:['listing-1','seller-1']};
describe('opportunity evidence dossier',()=>{
 it('is READY only with complete evidence inputs',()=>expect(buildOpportunityEvidenceDossier(base).state).toBe('READY'));
 it('keeps unknown economics as missing rather than zero',()=>{const d=buildOpportunityEvidenceDossier({...base,expectedOrders:null});expect(d.state).toBe('INCOMPLETE');expect(d.missing).toContain('expectedOrders')});
 it('keeps unknown confidence explicit',()=>expect(buildOpportunityEvidenceDossier({...base,confidence:{...base.confidence,sampleStrength:null}}).missing).toContain('confidence.sampleStrength'));
 it('requires provenance',()=>expect(()=>buildOpportunityEvidenceDossier({...base,evidenceRefs:[]})).toThrow());
 it('rejects impossible probability',()=>expect(()=>buildOpportunityEvidenceDossier({...base,settlementProbability:1.2})).toThrow());
 it('deduplicates evidence references',()=>expect(buildOpportunityEvidenceDossier({...base,evidenceRefs:['listing-1','listing-1']}).evidenceRefs).toEqual(['listing-1']));
});
