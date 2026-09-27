import { orchestrateReadiness, type ReadinessDecision } from './realityReadinessOrchestrator';
import { RealityEvidenceRegistry, type RealityState, type RealitySubject } from './realityEvidenceRegistry';

export type RealityManifest = {
  manifestId: string;
  generatedAt: string;
  executionEnabled: boolean;
  states: RealityState[];
  readiness: ReadinessDecision['action'];
  launchReadiness: ReadinessDecision['launch']['readiness'];
  nextSubject: RealitySubject | null;
  blockers: string[];
  unknowns: string[];
};

const SUBJECTS: RealitySubject[] = [
  'UK_ACCOUNT_ELIGIBILITY','IDENTITY_KYC','AFFILIATE_ACCESS','PAYOUT_METHOD',
  'REAL_PRODUCT','PRODUCT_FRESHNESS','SUPPLY','CREATIVE_APPROVAL',
  'PRODUCT_CLAIMS','CAPITAL_BOUND','LOSS_BOUND',
];

export function buildRealityManifest(
  manifestId: string,
  registry: RealityEvidenceRegistry,
  generatedAt: string,
  executionEnabled: boolean,
): RealityManifest {
  if (!manifestId || !Number.isFinite(Date.parse(generatedAt))) {
    throw new Error('Manifest requires id and valid generatedAt');
  }
  const states = SUBJECTS.map((subject) => registry.resolve(subject, generatedAt));
  const decision = orchestrateReadiness(registry, generatedAt, executionEnabled);
  return {
    manifestId,
    generatedAt,
    executionEnabled,
    states,
    readiness: decision.action,
    launchReadiness: decision.launch.readiness,
    nextSubject: decision.nextProbe?.subject ?? null,
    blockers: [...decision.launch.blockers],
    unknowns: [...decision.launch.unknowns],
  };
}

export function replayManifest(manifest: RealityManifest): {
  verified: RealitySubject[];
  blocked: RealitySubject[];
  unknown: RealitySubject[];
  readyToLaunch: boolean;
} {
  return {
    verified: manifest.states.filter((s) => s.state === 'VERIFIED').map((s) => s.subject),
    blocked: manifest.states.filter((s) => s.state === 'BLOCKED').map((s) => s.subject),
    unknown: manifest.states.filter((s) => s.state === 'UNKNOWN').map((s) => s.subject),
    readyToLaunch: manifest.readiness === 'READY_TO_LAUNCH' && manifest.launchReadiness === 'READY',
  };
}
