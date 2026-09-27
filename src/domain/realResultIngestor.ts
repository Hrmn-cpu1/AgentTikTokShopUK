import { ActionEventLedger, type CommerceEvent, type EventType } from './actionEventLedger';
import { resolveReward } from './rewardResolver';
import type { BusinessTruthStore } from './businessTruthStore';

export type RealResultInput = {
  source: 'TIKTOK_CREATOR_CENTER' | 'MANUAL_VERIFIED';
  externalEventId: string;
  experimentId: string;
  actionId: string | null;
  type: EventType;
  occurredAt: string;
  amountGbp: number | null;
  evidenceRef: string;
};

export type RealResultReceipt = {
  accepted: boolean;
  duplicate: boolean;
  event: CommerceEvent;
  reward: ReturnType<typeof resolveReward>;
  evidenceRef: string;
};

function validate(input: RealResultInput) {
  if (!input.externalEventId || !input.experimentId || !input.evidenceRef) {
    throw new Error('externalEventId, experimentId and evidenceRef are required');
  }
  if (!Number.isFinite(Date.parse(input.occurredAt))) throw new Error('occurredAt must be a valid timestamp');
  if (input.amountGbp !== null && (!Number.isFinite(input.amountGbp) || input.amountGbp < 0)) {
    throw new Error('amountGbp must be finite and non-negative');
  }
  if (input.type === 'COMMISSION_SETTLED' && input.amountGbp === null) {
    throw new Error('settled commission requires an observed GBP amount');
  }
}

export class RealResultIngestor {
  private readonly ledger:ActionEventLedger;
  constructor(store?:BusinessTruthStore){this.ledger=new ActionEventLedger(store)}

  ingest(input: RealResultInput): RealResultReceipt {
    validate(input);
    const key = `${input.source}::${input.externalEventId}`;

    const recorded = this.ledger.recordEvent({
      eventId: key,
      source: input.source,
      externalEventId: input.externalEventId,
      experimentId: input.experimentId,
      actionId: input.actionId,
      type: input.type,
      occurredAt: input.occurredAt,
      amountGbp: input.amountGbp,
      evidenceRef: input.evidenceRef,
    });

    return {
      accepted: true,
      duplicate: recorded.duplicate,
      event: recorded.record,
      reward: resolveReward(this.ledger.eventsForExperiment(input.experimentId)),
      evidenceRef: recorded.record.evidenceRef ?? input.evidenceRef,
    };
  }

  rewardForExperiment(experimentId: string) {
    return resolveReward(this.ledger.eventsForExperiment(experimentId));
  }
}
