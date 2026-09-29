import { MemoryBusinessTruthStore } from './businessTruthStore';
import { describe, expect, it } from 'vitest';
import { RealResultIngestor, type RealResultInput } from './realResultIngestor';

const base: RealResultInput = {
  source: 'TIKTOK_CREATOR_CENTER', externalEventId: 'order-1', experimentId: 'EXP-001',
  actionId: 'ACT-1', type: 'ORDER_CREATED', occurredAt: '2026-09-27T12:00:00Z',
  amountGbp: null, evidenceRef: 'creator-center:affiliate-order:order-1',
};

describe('real result ingestor', () => {
  it('accepts a traceable first real commerce signal without calling it money', () => {
    const receipt = new RealResultIngestor().ingest(base);
    expect(receipt.accepted).toBe(true);
    expect(receipt.reward).toMatchObject({ stage: 'ORDER', economicTruthKnown: false });
  });

  it('deduplicates retries by source and external event id', () => {
    const ingestor = new RealResultIngestor();
    expect(ingestor.ingest(base).duplicate).toBe(false);
    expect(ingestor.ingest(base).duplicate).toBe(true);
  });

  it('requires provenance for every real result', () => {
    expect(() => new RealResultIngestor().ingest({ ...base, evidenceRef: '' })).toThrow();
  });

  it('requires an observed amount before settlement can become economic truth', () => {
    expect(() => new RealResultIngestor().ingest({ ...base, type: 'COMMISSION_SETTLED', amountGbp: null })).toThrow();
  });

  it('turns a verified settlement into economic truth', () => {
    const ingestor = new RealResultIngestor();
    ingestor.ingest(base);
    const receipt = ingestor.ingest({ ...base, externalEventId: 'settle-1', type: 'COMMISSION_SETTLED', amountGbp: 4.25, evidenceRef: 'creator-center:earnings:settle-1' });
    expect(receipt.reward).toMatchObject({ stage: 'SETTLEMENT', maturity: 'FINAL', settledCommissionGbp: 4.25, economicTruthKnown: true });
  });

  it('lets a refund supersede earlier optimistic lifecycle evidence', () => {
    const ingestor = new RealResultIngestor();
    ingestor.ingest(base);
    expect(() => ingestor.ingest({ ...base, externalEventId: 'refund-1', type: 'REFUNDED', evidenceRef: 'creator-center:affiliate-order:refund-1' })).toThrow();
    const receipt = ingestor.ingest({ ...base, externalEventId: 'refund-1', type: 'REFUNDED', amountGbp:0, evidenceRef: 'creator-center:affiliate-order:refund-1' });
    expect(receipt.reward).toMatchObject({ stage: 'REFUND', refunded: true, economicTruthKnown: false });
  });

  it('keeps experiments isolated when real results arrive interleaved', () => {
    const ingestor = new RealResultIngestor();
    ingestor.ingest(base);
    ingestor.ingest({ ...base, externalEventId: 'settle-x', experimentId: 'EXP-999', type: 'COMMISSION_SETTLED', amountGbp: 99, evidenceRef: 'creator-center:earnings:settle-x' });
    expect(ingestor.rewardForExperiment('EXP-001').economicTruthKnown).toBe(false);
  });

  it('recovers settled economic truth after ingestor reconstruction',()=>{
    const store=new MemoryBusinessTruthStore();
    const first=new RealResultIngestor(store);
    const input={source:'TIKTOK_CREATOR_CENTER' as const,externalEventId:'settle-restart-1',experimentId:'EXP-RECOVER',actionId:null,type:'COMMISSION_SETTLED' as const,occurredAt:'2026-09-27T12:00:00Z',amountGbp:4.25,evidenceRef:'creator-center:settlement:1'};
    expect(first.ingest(input).duplicate).toBe(false);
    const recovered=new RealResultIngestor(store);
    expect(recovered.rewardForExperiment('EXP-RECOVER').settledCommissionGbp).toBe(4.25);
    expect(recovered.ingest(input).duplicate).toBe(true);
  });
});
