import type { BusinessTruthStore } from './businessTruthStore';
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
  evidenceRef?: string;
};

const eventTypes:EventType[]=['PUBLISHED','IMPRESSION','CLICK','ORDER_CREATED','DELIVERED','REFUNDED','COMMISSION_EXPECTED','COMMISSION_SETTLED'];
const actionStatuses:ActionStatus[]=['PROPOSED','APPROVED','EXECUTING','SUCCEEDED','FAILED','UNKNOWN'];
const nonempty=(value:unknown):value is string=>typeof value==='string'&&value.trim().length>0;
const validMoney=(value:unknown)=>value===null||(typeof value==='number'&&Number.isFinite(value)&&value>=0&&Number.isSafeInteger(Math.round(value*100))&&Math.abs(value*100-Math.round(value*100))<1e-7);
function assertAction(value:unknown):asserts value is ActionRecord{
 const a=value as ActionRecord;
 if(!a||!nonempty(a.actionId)||!nonempty(a.decisionId)||!nonempty(a.experimentId)||!nonempty(a.idempotencyKey)||!actionStatuses.includes(a.status)||!(a.externalId===null||nonempty(a.externalId)))throw new Error('Invalid persisted action');
}
function assertEvent(value:unknown):asserts value is CommerceEvent{
 const e=value as CommerceEvent;
 if(!e||!nonempty(e.eventId)||!nonempty(e.source)||!nonempty(e.externalEventId)||!nonempty(e.experimentId)||!(e.actionId===null||nonempty(e.actionId))||!eventTypes.includes(e.type)||!nonempty(e.occurredAt)||!Number.isFinite(Date.parse(e.occurredAt))||!validMoney(e.amountGbp)||!nonempty(e.evidenceRef)||((e.type==='COMMISSION_SETTLED'||e.type==='REFUNDED')&&e.amountGbp===null))throw new Error('Invalid persisted commerce event');
}
export function assertLedgerSnapshot(value:unknown):asserts value is {actions:ActionRecord[];events:CommerceEvent[]}{
 const x=value as {actions:unknown;events:unknown};
 if(!x||!Array.isArray(x.actions)||!Array.isArray(x.events))throw new Error('Invalid business truth snapshot');
 const actions=new Set<string>(),events=new Set<string>();
 for(const action of x.actions){assertAction(action);if(actions.has(action.idempotencyKey))throw new Error('Duplicate persisted action');actions.add(action.idempotencyKey)}
 for(const event of x.events){assertEvent(event);const key=`${event.source}::${event.externalEventId}`;if(events.has(key))throw new Error('Duplicate persisted commerce event');events.add(key)}
}

export class ActionEventLedger {
  private actionsByIdempotency = new Map<string, ActionRecord>();
  private eventsBySourceKey = new Map<string, CommerceEvent>();
  constructor(private readonly store?:BusinessTruthStore){
    const snapshot=store?.load();
    snapshot?.actions.forEach(a=>this.actionsByIdempotency.set(a.idempotencyKey,structuredClone(a)));
    snapshot?.events.forEach(e=>this.eventsBySourceKey.set(`${e.source}::${e.externalEventId}`,structuredClone(e)));
  }
  private persist(){this.store?.save({actions:[...this.actionsByIdempotency.values()],events:[...this.eventsBySourceKey.values()]})}

  recordAction(action: ActionRecord): { record: ActionRecord; duplicate: boolean } {
    assertAction(action);
    const existing = this.actionsByIdempotency.get(action.idempotencyKey);
    if (existing){if(JSON.stringify(existing)!==JSON.stringify(action))throw new Error('Conflicting action idempotency key');return { record: structuredClone(existing), duplicate: true }}
    this.actionsByIdempotency.set(action.idempotencyKey, structuredClone(action));
    try{this.persist()}catch(error){this.actionsByIdempotency.delete(action.idempotencyKey);throw error}
    return { record: structuredClone(action), duplicate: false };
  }

  recordEvent(event: CommerceEvent): { record: CommerceEvent; duplicate: boolean } {
    assertEvent(event);
    const key = `${event.source}::${event.externalEventId}`;
    const existing = this.eventsBySourceKey.get(key);
    if (existing){if(JSON.stringify(existing)!==JSON.stringify(event))throw new Error('Conflicting external event id');return { record: structuredClone(existing), duplicate: true }}
    this.eventsBySourceKey.set(key, structuredClone(event));
    try{this.persist()}catch(error){this.eventsBySourceKey.delete(key);throw error}
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
