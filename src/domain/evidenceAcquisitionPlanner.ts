import type { RealityState, RealitySubject } from './realityEvidenceRegistry';

export type EvidenceProbe = {
  subject: RealitySubject;
  dependencyTier: 1 | 2 | 3;
  estimatedMinutes: number;
  capitalCostGbp: number;
  informationValue: number;
  accountRisk: number;
  instruction: string;
};

export type EvidenceAcquisitionPlan = {
  next: EvidenceProbe | null;
  ordered: EvidenceProbe[];
  blocked: RealityState[];
};

const PROBES: Record<RealitySubject, EvidenceProbe> = {
  UK_ACCOUNT_ELIGIBILITY: { subject: 'UK_ACCOUNT_ELIGIBILITY', dependencyTier: 1, estimatedMinutes: 3, capitalCostGbp: 0, informationValue: 100, accountRisk: 0, instruction: 'Verify the account country/Shop eligibility in TikTok UI; record status only.' },
  IDENTITY_KYC: { subject: 'IDENTITY_KYC', dependencyTier: 1, estimatedMinutes: 5, capitalCostGbp: 0, informationValue: 100, accountRisk: 0, instruction: 'Verify KYC status in TikTok UI; never copy identity documents into the agent.' },
  AFFILIATE_ACCESS: { subject: 'AFFILIATE_ACCESS', dependencyTier: 1, estimatedMinutes: 3, capitalCostGbp: 0, informationValue: 100, accountRisk: 0, instruction: 'Verify Affiliate Center access and record status/reference.' },
  ACCOUNT_RISK: { subject: 'ACCOUNT_RISK', dependencyTier: 1, estimatedMinutes: 3, capitalCostGbp: 0, informationValue: 100, accountRisk: 0, instruction: 'Verify current account standing/risk status from authoritative TikTok UI; record status only, never infer it from eligibility.' },
  PAYOUT_METHOD: { subject: 'PAYOUT_METHOD', dependencyTier: 1, estimatedMinutes: 4, capitalCostGbp: 0, informationValue: 100, accountRisk: 0, instruction: 'Verify payout readiness/status only; never store bank credentials.' },
  REAL_PRODUCT: { subject: 'REAL_PRODUCT', dependencyTier: 2, estimatedMinutes: 10, capitalCostGbp: 0, informationValue: 85, accountRisk: 0, instruction: 'Select one currently available UK affiliate product with traceable source.' },
  PRODUCT_FRESHNESS: { subject: 'PRODUCT_FRESHNESS', dependencyTier: 2, estimatedMinutes: 3, capitalCostGbp: 0, informationValue: 80, accountRisk: 0, instruction: 'Re-check product evidence timestamp and current listing.' },
  SUPPLY: { subject: 'SUPPLY', dependencyTier: 2, estimatedMinutes: 4, capitalCostGbp: 0, informationValue: 85, accountRisk: 0, instruction: 'Verify current availability/seller supply evidence.' },
  PRODUCT_CLAIMS: { subject: 'PRODUCT_CLAIMS', dependencyTier: 2, estimatedMinutes: 5, capitalCostGbp: 0, informationValue: 80, accountRisk: 0, instruction: 'Map every factual creative claim to ProductTruth evidence.' },
  CREATIVE_APPROVAL: { subject: 'CREATIVE_APPROVAL', dependencyTier: 3, estimatedMinutes: 5, capitalCostGbp: 0, informationValue: 65, accountRisk: 0, instruction: 'Review and explicitly approve the EXP-001 creative.' },
  CAPITAL_BOUND: { subject: 'CAPITAL_BOUND', dependencyTier: 3, estimatedMinutes: 2, capitalCostGbp: 0, informationValue: 70, accountRisk: 0, instruction: 'Confirm experiment capital remains inside the deterministic limit.' },
  LOSS_BOUND: { subject: 'LOSS_BOUND', dependencyTier: 3, estimatedMinutes: 2, capitalCostGbp: 0, informationValue: 70, accountRisk: 0, instruction: 'Confirm maximum experiment loss remains inside the deterministic limit.' },
};

function score(p: EvidenceProbe): number {
  return p.informationValue / Math.max(1, p.estimatedMinutes + p.capitalCostGbp * 10 + p.accountRisk * 20);
}

export function planEvidenceAcquisition(states: RealityState[]): EvidenceAcquisitionPlan {
  const blocked = states.filter((s) => s.state === 'BLOCKED');
  if (blocked.length > 0) return { next: null, ordered: [], blocked };

  const unknownSubjects = new Set(states.filter((s) => s.state === 'UNKNOWN').map((s) => s.subject));
  const candidates = [...unknownSubjects].map((subject) => PROBES[subject]);
  if (candidates.length === 0) return { next: null, ordered: [], blocked: [] };

  const earliestTier = Math.min(...candidates.map((p) => p.dependencyTier));
  const ordered = candidates
    .filter((p) => p.dependencyTier === earliestTier)
    .sort((a, b) => score(b) - score(a) || a.subject.localeCompare(b.subject));

  return { next: ordered[0] ?? null, ordered, blocked: [] };
}
