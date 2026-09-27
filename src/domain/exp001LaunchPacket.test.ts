import { describe, expect, it } from 'vitest';
import { buildLaunchPacket } from './exp001LaunchPacket';

const frozen:any={experiment:{experimentId:'EXP-001',decisionId:'DEC-001'},product:{productId:'P1',listingRef:'listing-1'},evidenceRefs:['listing-1']};
const creative:any={packId:'CEP-EXP-001',experimentId:'EXP-001',decisionId:'DEC-001',productId:'P1',listingRef:'listing-1',claimEvidence:[{claim:'fact',sourceRefs:['listing-1']}]};
const execution={marketEligibility:'ELIGIBLE' as const,experimentReady:true,claimsValid:true,humanApproved:true,executionEnabled:true,withinCapitalLimit:true,withinLossLimit:true,accountRiskAcceptable:true};

describe('EXP-001 launch packet',()=>{
 it('preserves decision experiment product and creative trace',()=>{const p=buildLaunchPacket(frozen,creative,'CR-001',execution,'2026-09-27T18:20:00Z');expect([p.decisionId,p.experimentId,p.productId,p.creativeId]).toEqual(['DEC-001','EXP-001','P1','CR-001'])});
 it('reuses assisted execution idempotency',()=>expect(buildLaunchPacket(frozen,creative,'CR-001',execution,'2026-09-27T18:20:00Z').idempotencyKey).toBe('publish:EXP-001:CR-001'));
 it('remains manual and has no fabricated publication id',()=>{const p=buildLaunchPacket(frozen,creative,'CR-001',execution,'2026-09-27T18:20:00Z');expect(p.manualSteps).toContain('PUBLISH_MANUALLY');expect(p.externalPublicationId).toBeNull()});
 it('fails closed when approval is missing',()=>expect(buildLaunchPacket(frozen,creative,'CR-001',{...execution,humanApproved:false},'2026-09-27T18:20:00Z').readyForManualPublish).toBe(false));
 it('rejects cross-product trace mismatch',()=>expect(()=>buildLaunchPacket(frozen,{...creative,productId:'P2'},'CR-001',execution,'2026-09-27T18:20:00Z')).toThrow());
});
