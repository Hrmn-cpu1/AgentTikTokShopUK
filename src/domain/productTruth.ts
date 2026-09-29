export type TruthState = 'VERIFIED' | 'SUPPORTED' | 'UNKNOWN' | 'BLOCKED';

export type TruthClaim = {
  text: string;
  state: TruthState;
  sourceRefs: string[];
};

export type ProductTruthRecord = {
  productId: string;
  claims: TruthClaim[];
};

export function resolveClaim(record: ProductTruthRecord, text: string): TruthState {
  const matches = record.claims.filter((claim) => claim.text === text);
  if (matches.some((claim) => claim.state === 'BLOCKED')) return 'BLOCKED';
  if (matches.some((claim) => claim.state === 'VERIFIED')) return 'VERIFIED';
  if (matches.some((claim) => claim.state === 'SUPPORTED')) return 'SUPPORTED';
  return 'UNKNOWN';
}

export function assertPublishableClaims(record: ProductTruthRecord, claims: string[]): void {
  for (const claim of claims) {
    const state = resolveClaim(record, claim);
    if (state === 'UNKNOWN') throw new Error(`Unknown claim cannot be published: ${claim}`);
    if (state === 'BLOCKED') throw new Error(`Blocked claim cannot be published: ${claim}`);
  }
}
