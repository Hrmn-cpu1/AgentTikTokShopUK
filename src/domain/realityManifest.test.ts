import { describe, expect, it } from 'vitest';
import { buildRealityManifest, replayManifest } from './realityManifest';
import { RealityEvidenceRegistry, type RealitySubject } from './realityEvidenceRegistry';

const now='2026-09-27T15:00:00Z';
const subjects: RealitySubject[]=[
 'UK_ACCOUNT_ELIGIBILITY','IDENTITY_KYC','AFFILIATE_ACCESS','PAYOUT_METHOD','REAL_PRODUCT',
 'PRODUCT_FRESHNESS','SUPPLY','CREATIVE_APPROVAL','PRODUCT_CLAIMS','CAPITAL_BOUND','LOSS_BOUND'
];
function record(r:RealityEvidenceRegistry, subject:RealitySubject, state:'VERIFIED'|'BLOCKED'|'UNKNOWN', id:string) {
 r.record({evidenceId:id,subject,state,source:'OPERATOR_VERIFIED',observedAt:'2026-09-27T14:00:00Z',validUntil:null,reference:`status:${subject}`,containsSensitiveData:false});
}

describe('reality manifest',()=>{
 it('creates a replayable checkpoint with every launch subject',()=>{
   const r=new RealityEvidenceRegistry(); record(r,'AFFILIATE_ACCESS','VERIFIED','E1');
   const m=buildRealityManifest('MAN-001',r,now,true);
   expect(m.states).toHaveLength(11);
   expect(replayManifest(m).verified).toContain('AFFILIATE_ACCESS');
 });
 it('preserves unknowns rather than serializing them as false',()=>{
   const m=buildRealityManifest('MAN-001',new RealityEvidenceRegistry(),now,true);
   expect(replayManifest(m).unknown).toHaveLength(11);
   expect(m.nextSubject).not.toBeNull();
 });
 it('preserves hard blockers in the checkpoint',()=>{
   const r=new RealityEvidenceRegistry(); record(r,'UK_ACCOUNT_ELIGIBILITY','BLOCKED','B1');
   const m=buildRealityManifest('MAN-001',r,now,true);
   expect(m.readiness).toBe('RESOLVE_BLOCKER');
   expect(replayManifest(m).blocked).toContain('UK_ACCOUNT_ELIGIBILITY');
 });
 it('captures the deterministic next verification subject',()=>{
   const m=buildRealityManifest('MAN-001',new RealityEvidenceRegistry(),now,true);
   expect(m.readiness).toBe('VERIFY_NEXT');
   expect(m.nextSubject).toBeTruthy();
 });
 it('marks launch ready only when all evidence is verified and execution enabled',()=>{
   const r=new RealityEvidenceRegistry(); subjects.forEach((s,i)=>record(r,s,'VERIFIED',`E${i}`));
   const m=buildRealityManifest('MAN-READY',r,now,true);
   expect(replayManifest(m).readyToLaunch).toBe(true);
 });
 it('snapshot cannot bypass the execution kill switch',()=>{
   const r=new RealityEvidenceRegistry(); subjects.forEach((s,i)=>record(r,s,'VERIFIED',`E${i}`));
   const m=buildRealityManifest('MAN-KILL',r,now,false);
   expect(replayManifest(m).readyToLaunch).toBe(false);
   expect(m.blockers).toContain('Execution kill switch');
 });
});
