import type { CommerceEvent } from './actionEventLedger';

export type RewardStage =
  | 'NO_SIGNAL' | 'ATTENTION' | 'INTENT' | 'ORDER'
  | 'DELIVERY' | 'SETTLEMENT' | 'REFUND';

export type RewardMaturity = 'EARLY' | 'PARTIAL' | 'MATURE' | 'FINAL';

export type RewardResolution = {
  stage: RewardStage;
  maturity: RewardMaturity;
  proxyReward: number | null;
  settledCommissionGbp: number;
  grossSettledCommissionGbp: number;
  refundedAmountGbp: number;
  refunded: boolean;
  economicTruthKnown: boolean;
};

const stageRank: Record<RewardStage, number> = {
  NO_SIGNAL: 0, ATTENTION: 1, INTENT: 2, ORDER: 3,
  DELIVERY: 4, SETTLEMENT: 5, REFUND: 6,
};

function eventStage(event: CommerceEvent): RewardStage {
  switch (event.type) {
    case 'IMPRESSION': return 'ATTENTION';
    case 'CLICK': return 'INTENT';
    case 'ORDER_CREATED':
    case 'COMMISSION_EXPECTED': return 'ORDER';
    case 'DELIVERED': return 'DELIVERY';
    case 'COMMISSION_SETTLED': return 'SETTLEMENT';
    case 'REFUNDED': return 'REFUND';
    default: return 'NO_SIGNAL';
  }
}

export function resolveReward(events: CommerceEvent[]): RewardResolution {
  let stage: RewardStage = 'NO_SIGNAL';
  let grossSettledCommissionGbp = 0;
  let refundedAmountGbp = 0;
  let impressions = 0;
  let clicks = 0;
  let orders = 0;
  let refunded = false;

  for (const event of events) {
    const next = eventStage(event);
    if (stageRank[next] > stageRank[stage]) stage = next;
    if (event.type === 'IMPRESSION') impressions += 1;
    if (event.type === 'CLICK') clicks += 1;
    if (event.type === 'ORDER_CREATED') orders += 1;
    if (event.type === 'COMMISSION_SETTLED') grossSettledCommissionGbp += event.amountGbp ?? 0;
    if (event.type === 'REFUNDED') { refunded = true; refundedAmountGbp += event.amountGbp ?? 0; }
  }

  grossSettledCommissionGbp = Math.round(grossSettledCommissionGbp * 100) / 100;
  refundedAmountGbp = Math.round(refundedAmountGbp * 100) / 100;
  const settledCommissionGbp=Math.max(0,Math.round((grossSettledCommissionGbp-refundedAmountGbp)*100)/100);

  const proxyReward =
    orders > 0 ? orders :
    clicks > 0 ? clicks :
    impressions > 0 ? impressions :
    null;

  if (refunded) {
    return {
      stage: 'REFUND', maturity: 'FINAL', proxyReward,
      settledCommissionGbp, grossSettledCommissionGbp, refundedAmountGbp, refunded: true, economicTruthKnown: true,
    };
  }

  if (settledCommissionGbp > 0 || events.some((event) => event.type === 'COMMISSION_SETTLED')) {
    return {
      stage: 'SETTLEMENT', maturity: 'FINAL', proxyReward,
      settledCommissionGbp, grossSettledCommissionGbp, refundedAmountGbp, refunded: false, economicTruthKnown: true,
    };
  }

  if (stage === 'DELIVERY') {
    return { stage, maturity: 'MATURE', proxyReward, settledCommissionGbp: 0, grossSettledCommissionGbp:0, refundedAmountGbp:0, refunded: false, economicTruthKnown: false };
  }
  if (stage === 'ORDER') {
    return { stage, maturity: 'PARTIAL', proxyReward, settledCommissionGbp: 0, refunded: false, economicTruthKnown: false };
  }
  return { stage, maturity: 'EARLY', proxyReward, settledCommissionGbp: 0, refunded: false, economicTruthKnown: false };
}
