import type { EvidenceProbe } from './evidenceAcquisitionPlanner';
import type { RealitySubject } from './realityEvidenceRegistry';

export type OnboardingStep = {
  subject: RealitySubject;
  title: string;
  instruction: string;
  referenceHint: string;
  accepts: readonly ['VERIFIED','BLOCKED'];
};

const HINTS: Record<RealitySubject,string> = {
 UK_ACCOUNT_ELIGIBILITY:'e.g. TikTok UI > account/Shop region screen',
 IDENTITY_KYC:'e.g. TikTok UI > verification status screen (status only)',
 AFFILIATE_ACCESS:'e.g. Creator Center > Affiliate Center access screen',
 PAYOUT_METHOD:'e.g. TikTok earnings/payout status screen (no bank details)',
 ACCOUNT_RISK:'e.g. TikTok account standing/status screen showing current restrictions or good standing',
 REAL_PRODUCT:'e.g. TikTok Shop UK product listing URL or listing ID',
 PRODUCT_FRESHNESS:'e.g. listing rechecked at timestamp',
 SUPPLY:'e.g. current listing availability/seller screen',
 CREATIVE_APPROVAL:'e.g. EXP-001 creative review checkpoint',
 PRODUCT_CLAIMS:'e.g. product listing/spec source supporting claims',
 CAPITAL_BOUND:'e.g. EXP-001 deterministic capital calculation',
 LOSS_BOUND:'e.g. EXP-001 deterministic maximum-loss calculation',
};
const TITLES: Record<RealitySubject,string> = {
 UK_ACCOUNT_ELIGIBILITY:'Verify UK account eligibility', IDENTITY_KYC:'Verify identity/KYC status',
 AFFILIATE_ACCESS:'Verify Affiliate access', PAYOUT_METHOD:'Verify payout readiness', ACCOUNT_RISK:'Verify current account risk status',
 REAL_PRODUCT:'Select one real UK product', PRODUCT_FRESHNESS:'Re-check product freshness',
 SUPPLY:'Verify product supply', CREATIVE_APPROVAL:'Approve EXP-001 creative',
 PRODUCT_CLAIMS:'Verify ProductTruth claims', CAPITAL_BOUND:'Confirm capital bound', LOSS_BOUND:'Confirm loss bound',
};

export function buildOnboardingStep(probe:EvidenceProbe):OnboardingStep {
 return {subject:probe.subject,title:TITLES[probe.subject],instruction:probe.instruction,referenceHint:HINTS[probe.subject],accepts:['VERIFIED','BLOCKED']};
}

export function validateEvidenceReference(reference:string):string {
 const value=reference.trim();
 if(value.length<6) throw new Error('Evidence reference must identify where the status was actually observed');
 if(/^operator-check:/i.test(value)) throw new Error('Synthetic operator references are not acceptable reality evidence');
 return value;
}
