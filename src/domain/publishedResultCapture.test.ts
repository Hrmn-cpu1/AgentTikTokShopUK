import {describe,expect,it} from 'vitest';
import {bindRealPublication,PublishedResultCapture} from './publishedResultCapture';

const packet={packetId:'LP-EXP-001-CR-001',experimentId:'EXP-001',creativeId:'CR-001',readyForManualPublish:true};
const pub=bindRealPublication(packet,'video-123','2026-09-27T19:00:00Z','creator-center/video-123');

describe('published result capture',()=>{
 it('binds a real external publication to EXP-001',()=>expect(pub.externalPublicationId).toBe('video-123'));
 it('refuses publication binding before launch approval',()=>expect(()=>bindRealPublication({...packet,readyForManualPublish:false},'v','2026-09-27T19:00:00Z','ref')).toThrow());
 it('captures an order without calling it economic truth',()=>{const c=new PublishedResultCapture(pub);const r=c.capture({source:'TIKTOK_CREATOR_CENTER',externalEventId:'order-1',type:'ORDER_CREATED',occurredAt:'2026-09-27T20:00:00Z',amountGbp:null,evidenceRef:'order-screen'});expect(r.reward.economicTruthKnown).toBe(false)});
 it('deduplicates retry of the same external event',()=>{const c=new PublishedResultCapture(pub);const e={source:'MANUAL_VERIFIED' as const,externalEventId:'settle-1',type:'COMMISSION_SETTLED' as const,occurredAt:'2026-09-28T20:00:00Z',amountGbp:4.25,evidenceRef:'earnings-screen'};expect(c.capture(e).duplicate).toBe(false);expect(c.capture(e).duplicate).toBe(true)});
 it('settlement creates observed economic truth',()=>{const c=new PublishedResultCapture(pub);const r=c.capture({source:'MANUAL_VERIFIED',externalEventId:'settle-2',type:'COMMISSION_SETTLED',occurredAt:'2026-09-28T20:00:00Z',amountGbp:4.25,evidenceRef:'earnings-screen'});expect(r.reward.economicTruthKnown).toBe(true);expect(r.reward.settledCommissionGbp).toBe(4.25)});
 it('refund remains distinct from settlement',()=>{const c=new PublishedResultCapture(pub);c.capture({source:'MANUAL_VERIFIED',externalEventId:'settle-3',type:'COMMISSION_SETTLED',occurredAt:'2026-09-28T20:00:00Z',amountGbp:4.25,evidenceRef:'earnings'});const r=c.capture({source:'MANUAL_VERIFIED',externalEventId:'refund-1',type:'REFUNDED',occurredAt:'2026-09-29T20:00:00Z',amountGbp:4.25,evidenceRef:'refund'});expect(r.reward.refunded).toBe(true)});
});
