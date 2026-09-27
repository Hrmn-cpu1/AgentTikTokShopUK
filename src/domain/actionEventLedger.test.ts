import { describe, expect, it } from 'vitest';
import { ActionEventLedger, type CommerceEvent } from './actionEventLedger';

const event = (overrides: Partial<CommerceEvent> = {}): CommerceEvent => ({
  eventId: 'EV-1', source: 'manual', externalEventId: 'ext-1',
  experimentId: 'EXP-001', actionId: 'ACT-1', type: 'ORDER_CREATED',
  occurredAt: '2026-09-27T10:00:00Z', amountGbp: null, evidenceRef:'creator-center:event:ext-1', ...overrides,
});

describe('action and event ledger', () => {
  it('deduplicates actions by idempotency key', () => {
    const ledger = new ActionEventLedger();
    const action = { actionId: 'ACT-1', decisionId: 'DEC-1', experimentId: 'EXP-001', idempotencyKey: 'publish:EXP-001:creative-1', status: 'PROPOSED' as const, externalId: null };
    expect(ledger.recordAction(action).duplicate).toBe(false);
    expect(ledger.recordAction(action).duplicate).toBe(true);
    expect(() => ledger.recordAction({ ...action, actionId: 'ACT-2' })).toThrow('Conflicting action idempotency key');
  });

  it('deduplicates external events by source plus externalEventId', () => {
    const ledger = new ActionEventLedger();
    expect(ledger.recordEvent(event()).duplicate).toBe(false);
    expect(ledger.recordEvent(event()).duplicate).toBe(true);
    expect(() => ledger.recordEvent(event({ eventId: 'EV-2', amountGbp: 9 }))).toThrow('Conflicting external event id');
  });

  it('keeps events traceable to the experiment even when arrival order is odd', () => {
    const ledger = new ActionEventLedger();
    ledger.recordEvent(event({ eventId: 'EV-2', externalEventId: 'settle', type: 'COMMISSION_SETTLED', occurredAt: '2026-09-29T10:00:00Z', amountGbp: 4.5 }));
    ledger.recordEvent(event({ eventId: 'EV-1', externalEventId: 'order', occurredAt: '2026-09-27T10:00:00Z' }));
    expect(ledger.eventsForExperiment('EXP-001').map((x) => x.type)).toEqual(['ORDER_CREATED', 'COMMISSION_SETTLED']);
  });

  it('never counts an order or expected commission as settled money', () => {
    const ledger = new ActionEventLedger();
    ledger.recordEvent(event({ externalEventId: 'order', type: 'ORDER_CREATED' }));
    ledger.recordEvent(event({ eventId: 'EV-2', externalEventId: 'expected', type: 'COMMISSION_EXPECTED', amountGbp: 9 }));
    expect(ledger.settledCommissionGbp('EXP-001')).toBe(0);
  });

  it('counts only deduplicated settlement events as economic truth', () => {
    const ledger = new ActionEventLedger();
    ledger.recordEvent(event({ externalEventId: 'settle-1', type: 'COMMISSION_SETTLED', amountGbp: 4.5 }));
    ledger.recordEvent(event({ externalEventId: 'settle-1', type: 'COMMISSION_SETTLED', amountGbp: 4.5 }));
    ledger.recordEvent(event({ eventId: 'EV-3', externalEventId: 'settle-2', type: 'COMMISSION_SETTLED', amountGbp: 2.25 }));
    expect(ledger.settledCommissionGbp('EXP-001')).toBe(6.75);
  });

  it('does not mix economic events across experiments', () => {
    const ledger = new ActionEventLedger();
    ledger.recordEvent(event({ externalEventId: 'a', type: 'COMMISSION_SETTLED', amountGbp: 5 }));
    ledger.recordEvent(event({ eventId: 'EV-2', externalEventId: 'b', experimentId: 'EXP-002', type: 'COMMISSION_SETTLED', amountGbp: 20 }));
    expect(ledger.settledCommissionGbp('EXP-001')).toBe(5);
  });

  it('rejects malformed negative money events', () => {
    const ledger = new ActionEventLedger();
    expect(() => ledger.recordEvent(event({ amountGbp: -1 }))).toThrow();
  });
});
