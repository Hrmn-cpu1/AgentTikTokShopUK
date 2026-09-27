import type { LaunchCheckState } from './exp001LaunchGate';

export type RealitySubject =
  | 'UK_ACCOUNT_ELIGIBILITY' | 'IDENTITY_KYC' | 'AFFILIATE_ACCESS' | 'PAYOUT_METHOD' | 'ACCOUNT_RISK'
  | 'REAL_PRODUCT' | 'PRODUCT_FRESHNESS' | 'SUPPLY' | 'CREATIVE_APPROVAL'
  | 'PRODUCT_CLAIMS' | 'CAPITAL_BOUND' | 'LOSS_BOUND';

export type EvidenceSource = 'TIKTOK_UI' | 'TIKTOK_OFFICIAL' | 'OPERATOR_VERIFIED' | 'SYSTEM_DERIVED';

export type RealityEvidence = {
  evidenceId: string;
  subject: RealitySubject;
  state: LaunchCheckState;
  source: EvidenceSource;
  observedAt: string;
  validUntil: string | null;
  reference: string;
  containsSensitiveData: false;
};

export type RealityState = {
  subject: RealitySubject;
  state: LaunchCheckState;
  evidenceId: string | null;
  reason: string;
};

function validTimestamp(value: string): boolean {
  return Number.isFinite(Date.parse(value));
}

export class RealityEvidenceRegistry {
  private readonly evidence = new Map<string, RealityEvidence>();
  private readonly latestBySubject = new Map<RealitySubject, RealityEvidence>();

  record(item: RealityEvidence): { evidence: RealityEvidence; duplicate: boolean } {
    if (!item.evidenceId || !item.reference || !validTimestamp(item.observedAt)) {
      throw new Error('Evidence requires id, reference and valid observedAt');
    }
    if (item.validUntil !== null && !validTimestamp(item.validUntil)) throw new Error('validUntil must be a valid timestamp');
    if (item.containsSensitiveData !== false) throw new Error('Sensitive KYC or payout data must not be stored');

    const existing = this.evidence.get(item.evidenceId);
    if (existing) return { evidence: structuredClone(existing), duplicate: true };

    this.evidence.set(item.evidenceId, structuredClone(item));
    const current = this.latestBySubject.get(item.subject);
    if (!current || item.observedAt >= current.observedAt) this.latestBySubject.set(item.subject, structuredClone(item));
    return { evidence: structuredClone(item), duplicate: false };
  }

  resolve(subject: RealitySubject, nowIso: string): RealityState {
    if (!validTimestamp(nowIso)) throw new Error('nowIso must be a valid timestamp');
    const item = this.latestBySubject.get(subject);
    if (!item) return { subject, state: 'UNKNOWN', evidenceId: null, reason: 'No evidence recorded.' };

    if (item.validUntil !== null && Date.parse(nowIso) > Date.parse(item.validUntil)) {
      return { subject, state: 'UNKNOWN', evidenceId: item.evidenceId, reason: 'Evidence expired; re-verification required.' };
    }

    return { subject, state: item.state, evidenceId: item.evidenceId, reason: 'State backed by recorded evidence.' };
  }

  allEvidence(): RealityEvidence[] {
    return [...this.evidence.values()]
      .sort((a,b)=>a.observedAt.localeCompare(b.observedAt)||a.evidenceId.localeCompare(b.evidenceId))
      .map(item=>structuredClone(item));
  }

  unresolved(subjects: RealitySubject[], nowIso: string): RealityState[] {
    return subjects.map((subject) => this.resolve(subject, nowIso)).filter((x) => x.state !== 'VERIFIED');
  }
}
