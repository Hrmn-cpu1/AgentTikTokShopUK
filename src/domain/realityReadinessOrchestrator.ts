import { evaluateExp001Launch, type Exp001LaunchEvidence } from './exp001LaunchGate';
import { planEvidenceAcquisition } from './evidenceAcquisitionPlanner';
import { RealityEvidenceRegistry, type RealitySubject } from './realityEvidenceRegistry';

export type ReadinessAction = 'VERIFY_NEXT' | 'RESOLVE_BLOCKER' | 'READY_TO_LAUNCH' | 'NO_ACTION';

export type ReadinessDecision = {
  action: ReadinessAction;
  launch: ReturnType<typeof evaluateExp001Launch>;
  nextProbe: ReturnType<typeof planEvidenceAcquisition>['next'];
  message: string;
};

const SUBJECTS: RealitySubject[] = [
  'UK_ACCOUNT_ELIGIBILITY', 'IDENTITY_KYC', 'AFFILIATE_ACCESS', 'PAYOUT_METHOD',
  'REAL_PRODUCT', 'PRODUCT_FRESHNESS', 'SUPPLY', 'CREATIVE_APPROVAL',
  'PRODUCT_CLAIMS', 'CAPITAL_BOUND', 'LOSS_BOUND',
];

function launchEvidence(registry: RealityEvidenceRegistry, nowIso: string, executionEnabled: boolean): Exp001LaunchEvidence {
  const state = (subject: RealitySubject) => registry.resolve(subject, nowIso).state;
  return {
    ukAccountEligibility: state('UK_ACCOUNT_ELIGIBILITY'),
    identityKyc: state('IDENTITY_KYC'),
    affiliateAccess: state('AFFILIATE_ACCESS'),
    payoutMethod: state('PAYOUT_METHOD'),
    realProductSelected: state('REAL_PRODUCT'),
    productEvidenceFresh: state('PRODUCT_FRESHNESS'),
    supplyAvailable: state('SUPPLY'),
    creativeApproved: state('CREATIVE_APPROVAL'),
    productClaimsValid: state('PRODUCT_CLAIMS'),
    capitalBounded: state('CAPITAL_BOUND'),
    lossBounded: state('LOSS_BOUND'),
    executionEnabled,
  };
}

export function orchestrateReadiness(
  registry: RealityEvidenceRegistry,
  nowIso: string,
  executionEnabled: boolean,
): ReadinessDecision {
  const states = SUBJECTS.map((subject) => registry.resolve(subject, nowIso));
  const launch = evaluateExp001Launch(launchEvidence(registry, nowIso, executionEnabled));

  if (launch.readiness === 'READY') {
    return { action: 'READY_TO_LAUNCH', launch, nextProbe: null, message: 'EXP-001 reality prerequisites are verified; manual launch may proceed.' };
  }

  const acquisition = planEvidenceAcquisition(states);
  if (acquisition.blocked.length > 0 || launch.readiness === 'BLOCKED') {
    return {
      action: 'RESOLVE_BLOCKER',
      launch,
      nextProbe: null,
      message: acquisition.blocked[0]?.reason ?? launch.blockers[0] ?? 'Resolve the launch blocker before more evidence work.',
    };
  }

  if (acquisition.next) {
    return { action: 'VERIFY_NEXT', launch, nextProbe: acquisition.next, message: acquisition.next.instruction };
  }

  return { action: 'NO_ACTION', launch, nextProbe: null, message: 'No safe readiness action is currently available.' };
}
