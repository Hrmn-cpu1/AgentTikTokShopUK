import { describe, expect, it } from 'vitest';
import { resolveReward } from './rewardResolver';
import type { CommerceEvent } from './actionEventLedger';

const e = (type: CommerceEvent['type'], externalEventId: string, amountGbp: number | null = null): CommerceEvent => ({
  eventId: externalEventId, source: 'manual', externalEventId, experimentId: 'EXP-001',
  actionId: null, type, occurredAt: '2026-09-27T10:00:00Z', amountGbp,
});

describe('reward resolver', () => {
  it('treats impressions and clicks only as early proxy reward', () => {
    const r = resolveReward([e('IMPRESSION','i'), e('CLICK','c')]);
    expect(r).toMatchObject({ stage: 'INTENT', maturity: 'EARLY', economicTruthKnown: false, settledCommissionGbp: 0 });
  });

  it('treats an order as partial evidence, never realized money', () => {
    const r = resolveReward([e('ORDER_CREATED','o'), e('COMMISSION_EXPECTED','x',9)]);
    expect(r).toMatchObject({ stage: 'ORDER', maturity: 'PARTIAL', settledCommissionGbp: 0, economicTruthKnown: false });
  });

  it('treats delivery as mature commerce evidence but not economic truth', () => {
    expect(resolveReward([e('DELIVERED','d')])).toMatchObject({ stage: 'DELIVERY', maturity: 'MATURE', economicTruthKnown: false });
  });

  it('uses settlement as final economic truth even when events arrive out of order', () => {
    const r = resolveReward([e('COMMISSION_SETTLED','s',4.5), e('ORDER_CREATED','o')]);
    expect(r).toMatchObject({ stage: 'SETTLEMENT', maturity: 'FINAL', settledCommissionGbp: 4.5, economicTruthKnown: true });
  });

  it('distinguishes a zero-value settlement from missing settlement', () => {
    const r = resolveReward([e('COMMISSION_SETTLED','s',0)]);
    expect(r).toMatchObject({ stage: 'SETTLEMENT', maturity: 'FINAL', settledCommissionGbp: 0, economicTruthKnown: true });
  });

  it('makes a refund final negative lifecycle evidence instead of hiding it behind prior settlement', () => {
    const r = resolveReward([e('COMMISSION_SETTLED','s',4.5), e('REFUNDED','r')]);
    expect(r).toMatchObject({ stage: 'REFUND', maturity: 'FINAL', refunded: true, economicTruthKnown: true });
  });

  it('keeps no evidence distinct from a measured zero economic result', () => {
    const r = resolveReward([]);
    expect(r).toMatchObject({ stage: 'NO_SIGNAL', maturity: 'EARLY', economicTruthKnown: false });
    expect(r.proxyReward).toBeNull();
  });
});
