import { RealityEvidenceRegistry, type EvidenceSource, type RealitySubject } from './realityEvidenceRegistry';
import type { LaunchCheckState } from './exp001LaunchGate';

export type OperatorEvidenceInput = {
  evidenceId: string;
  subject: RealitySubject;
  state: LaunchCheckState;
  source: EvidenceSource;
  observedAt: string;
  validUntil?: string | null;
  reference: string;
  note?: string;
};

const FORBIDDEN = [
  /password/i, /passcode/i, /token/i, /secret/i, /private[_ -]?key/i,
  /passport\s*(number|no\.?|#)/i, /bank\s*(account|password|login)/i,
  /sort\s*code/i, /card\s*(number|cvv|cvc)/i, /iban\s*[:=]/i,
];

function assertSafeText(value: string): void {
  if (FORBIDDEN.some((pattern) => pattern.test(value))) {
    throw new Error('Evidence intake rejected possible credential or sensitive financial/identity data');
  }
}

export function ingestOperatorEvidence(
  registry: RealityEvidenceRegistry,
  input: OperatorEvidenceInput,
): ReturnType<RealityEvidenceRegistry['record']> {
  assertSafeText(input.reference);
  if (input.note) assertSafeText(input.note);

  if (input.source !== 'TIKTOK_UI' && input.source !== 'TIKTOK_OFFICIAL' && input.source !== 'OPERATOR_VERIFIED' && input.source !== 'SYSTEM_DERIVED') {
    throw new Error('Unsupported evidence source');
  }

  return registry.record({
    evidenceId: input.evidenceId,
    subject: input.subject,
    state: input.state,
    source: input.source,
    observedAt: input.observedAt,
    validUntil: input.validUntil ?? null,
    reference: input.reference,
    containsSensitiveData: false,
  });
}
