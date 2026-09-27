export type ActionStatus = 'PROPOSED' | 'APPROVED' | 'EXECUTING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN';
export type EventType =
  | 'PUBLISHED' | 'IMPRESSION' | 'CLICK' | 'ORDER_CREATED'
  | 'DELIVERED' | 'REFUNDED' | 'COMMISSION_EXPECTED' | 'COMMISSION_SETTLED';

export type ActionRecord = {
  actionId: string;
  decisionId: string;
  experimentId: string;
  idempotencyKey: string;
  status: ActionStatus;
  externalId: string | null;
};

export type CommerceEvent = {
  eventId: string;
  source: string;
  externalEventId: string;
  experimentId: string;
  actionId: string | null;
  type: EventType;
  occurredAt: string;
  amountGbp: number | null;
};

export class ActionEventLedger {
  private actionsByIdempotency = new Map<string, ActionRecord>();
  private eventsBySourceKey = new Map<string, CommerceEvent>();

  recordAction(action: ActionRecord): { record: ActionRecord; duplicate: boolean } {
    if (!action.actionId || !action.decisionId || !action.experimentId || !action.idempotencyKey) {
      throw new Error('Action requires actionId, decisionId, experimentId and idempotencyKey');
    }
    const existing = this.actionsByIdempotency.get(action.idempotencyKey);
    if (existing) return { record: structuredClone(existing), duplicate: true };
    this.actionsByIdempotency.set(action.idempotencyKey, structuredClone(action));
    return { record: structuredClone(action), duplicate: false };
  }

  recordEvent(event: CommerceEvent): { record: CommerceEvent; duplicate: boolean } {
    if (!event.eventId || !event.source || !event.externalEventId || !event.experimentId) {
      throw new Error('Event requires eventId, source, externalEventId and experimentId');
    }
    if (event.amountGbp !== null && (!Number.isFinite(event.amountGbp) || event.amountGbp < 0)) {
      throw new Error('amountGbp must be null or finite and non-negative');
    }
    const key = `${event.source}::${event.externalEventId}`;
    const existing = this.eventsBySourceKey.get(key);
    if (existing) return { record: structuredClone(existing), duplicate: true };
    this.eventsBySourceKey.set(key, structuredClone(event));
    return { record: structuredClone(event), duplicate: false };
  }

  eventsForExperiment(experimentId: string): CommerceEvent[] {
    return [...this.eventsBySourceKey.values()]
      .filter((event) => event.experimentId === experimentId)
      .sort((a, b) => a.occurredAt.localeCompare(b.occurredAt) || a.eventId.localeCompare(b.eventId))
      .map((event) => structuredClone(event));
  }

  settledCommissionGbp(experimentId: string): number {
    return Math.round(this.eventsForExperiment(experimentId)
      .filter((event) => event.type === 'COMMISSION_SETTLED')
      .reduce((sum, event) => sum + (event.amountGbp ?? 0), 0) * 100) / 100;
  }
}
