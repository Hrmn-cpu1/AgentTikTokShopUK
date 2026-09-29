export type EligibilityState = 'ELIGIBLE' | 'CONDITIONAL' | 'BLOCKED' | 'UNKNOWN';
export type RequirementState = 'VERIFIED' | 'BLOCKED' | 'UNKNOWN';

export type EligibilityRequirement =
  | 'account_location'
  | 'identity_kyc'
  | 'affiliate_access'
  | 'payout_method';

export type EligibilitySnapshot = Record<EligibilityRequirement, RequirementState>;

export const eligibilityLabels: Record<EligibilityRequirement, string> = {
  account_location: 'UK account/location eligible',
  identity_kyc: 'Identity / KYC verified',
  affiliate_access: 'TikTok Shop Affiliate active',
  payout_method: 'UK payout method accepted',
};

export const defaultEligibility: EligibilitySnapshot = {
  account_location: 'UNKNOWN',
  identity_kyc: 'UNKNOWN',
  affiliate_access: 'UNKNOWN',
  payout_method: 'UNKNOWN',
};

export function resolveEligibility(input: EligibilitySnapshot): EligibilityState {
  const states = Object.values(input);
  if (states.includes('BLOCKED')) return 'BLOCKED';
  if (states.every((state) => state === 'VERIFIED')) return 'ELIGIBLE';
  if (states.every((state) => state === 'UNKNOWN')) return 'UNKNOWN';
  return 'CONDITIONAL';
}

export function canExecuteExternally(input: EligibilitySnapshot): boolean {
  return resolveEligibility(input) === 'ELIGIBLE';
}

export function nextRequirementState(current: RequirementState): RequirementState {
  if (current === 'UNKNOWN') return 'VERIFIED';
  if (current === 'VERIFIED') return 'BLOCKED';
  return 'UNKNOWN';
}
