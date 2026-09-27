import {describe,expect,it} from 'vitest';
import {RealityEvidenceRegistry} from './realityEvidenceRegistry';
import {resolveOpportunityAuthority} from './opportunityAuthority';
const ctx={executionEnabled:false,claimsValid:true,humanApproved:false,withinCapitalLimit:true,withinLossLimit:true};
const record=(r:RealityEvidenceRegistry,subject:any,state:any='VERIFIED')=>r.record({evidenceId:'e-'+subject,subject,state,source:'OPERATOR_VERIFIED',observedAt:'2026-09-27T10:00:00Z',validUntil:null,reference:'screen-'+subject,containsSensitiveData:false});
describe('opportunity authority',()=>{
 it('fails closed when reality evidence is absent',()=>expect(resolveOpportunityAuthority(new RealityEvidenceRegistry(),'2026-09-27T11:00:00Z',ctx).marketEligible).toBe(false));
 it('requires account KYC and affiliate evidence',()=>{const r=new RealityEvidenceRegistry();record(r,'UK_ACCOUNT_ELIGIBILITY');record(r,'IDENTITY_KYC');record(r,'AFFILIATE_ACCESS');expect(resolveOpportunityAuthority(r,'2026-09-27T11:00:00Z',ctx).marketEligible).toBe(true)});
 it('UNKNOWN never grants account authority',()=>{const r=new RealityEvidenceRegistry();record(r,'UK_ACCOUNT_ELIGIBILITY');record(r,'IDENTITY_KYC');record(r,'AFFILIATE_ACCESS','UNKNOWN');expect(resolveOpportunityAuthority(r,'2026-09-27T11:00:00Z',ctx).accountRiskAcceptable).toBe(false)});
});
