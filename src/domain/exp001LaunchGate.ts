export type LaunchCheckState = 'VERIFIED' | 'BLOCKED' | 'UNKNOWN';

export type Exp001LaunchEvidence = {
  ukAccountEligibility: LaunchCheckState;
  identityKyc: LaunchCheckState;
  affiliateAccess: LaunchCheckState;
  payoutMethod: LaunchCheckState;
  realProductSelected: LaunchCheckState;
  productEvidenceFresh: LaunchCheckState;
  supplyAvailable: LaunchCheckState;
  creativeApproved: LaunchCheckState;
  productClaimsValid: LaunchCheckState;
  capitalBounded: LaunchCheckState;
  lossBounded: LaunchCheckState;
  executionEnabled: boolean;
};

export type LaunchReadiness = 'READY' | 'BLOCKED' | 'NOT_PROVEN';

export type Exp001LaunchGate = {
  readiness: LaunchReadiness;
  verified: string[];
  blockers: string[];
  unknowns: string[];
  mayPublishManually: boolean;
};

export function evaluateExp001Launch(e: Exp001LaunchEvidence): Exp001LaunchGate {
  const checks: [string, LaunchCheckState][] = [
    ['UK account eligibility', e.ukAccountEligibility],
    ['Identity/KYC', e.identityKyc],
    ['Affiliate access', e.affiliateAccess],
    ['Payout method', e.payoutMethod],
    ['Real product selected', e.realProductSelected],
    ['Product evidence freshness', e.productEvidenceFresh],
    ['Supply availability', e.supplyAvailable],
    ['Creative approval', e.creativeApproved],
    ['Product claims', e.productClaimsValid],
    ['Capital bound', e.capitalBounded],
    ['Loss bound', e.lossBounded],
  ];

  const verified = checks.filter(([, state]) => state === 'VERIFIED').map(([name]) => name);
  const blockers = checks.filter(([, state]) => state === 'BLOCKED').map(([name]) => name);
  const unknowns = checks.filter(([, state]) => state === 'UNKNOWN').map(([name]) => name);

  if (!e.executionEnabled) blockers.push('Execution kill switch');

  const readiness: LaunchReadiness =
    blockers.length > 0 ? 'BLOCKED' :
    unknowns.length > 0 ? 'NOT_PROVEN' :
    'READY';

  return {
    readiness,
    verified,
    blockers,
    unknowns,
    mayPublishManually: readiness === 'READY',
  };
}
