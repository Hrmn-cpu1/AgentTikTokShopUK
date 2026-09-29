import type { WinnerDiagnosis } from './failureWinnerEngine';

export type LearningOutcome = 'PROFIT' | 'LOSS' | 'BREAK_EVEN' | 'REFUND' | 'IMMATURE';

export type LearningInput = {
  learningId: string;
  decisionId: string;
  experimentId: string;
  opportunityId: string;
  creativeId: string;
  hypothesis: string;
  variableUnderTest: string;
  market: 'UK';
  settledCommissionGbp: number | null;
  realizedContributionGbp: number | null;
  refunded: boolean;
  rewardMature: boolean;
  diagnosis: WinnerDiagnosis;
  evidenceRefs: string[];
};

export type LearningRecord = {
  learningId: string;
  trace: {
    decisionId: string;
    experimentId: string;
    opportunityId: string;
    creativeId: string;
  };
  hypothesis: string;
  variableUnderTest: string;
  market: 'UK';
  outcome: LearningOutcome;
  realizedContributionGbp: number | null;
  winnerStage: WinnerDiagnosis['winnerStage'];
  nextDecision: WinnerDiagnosis['decision'];
  reusable: boolean;
  evidenceRefs: string[];
};

export function deriveLearning(input: LearningInput): LearningRecord {
  if (!input.learningId || !input.decisionId || !input.experimentId || !input.opportunityId || !input.creativeId) {
    throw new Error('Learning requires complete trace ids');
  }
  if (input.evidenceRefs.length === 0) throw new Error('Learning requires evidence provenance');

  let outcome: LearningOutcome = 'IMMATURE';
  if (input.refunded) outcome = 'REFUND';
  else if (input.rewardMature && input.realizedContributionGbp !== null) {
    if (input.realizedContributionGbp > 0) outcome = 'PROFIT';
    else if (input.realizedContributionGbp < 0) outcome = 'LOSS';
    else outcome = 'BREAK_EVEN';
  }

  const reusable =
    input.rewardMature &&
    !input.refunded &&
    input.realizedContributionGbp !== null &&
    input.diagnosis.winnerStage === 'REPEATABILITY_VALIDATED';

  return {
    learningId: input.learningId,
    trace: {
      decisionId: input.decisionId,
      experimentId: input.experimentId,
      opportunityId: input.opportunityId,
      creativeId: input.creativeId,
    },
    hypothesis: input.hypothesis,
    variableUnderTest: input.variableUnderTest,
    market: input.market,
    outcome,
    realizedContributionGbp: input.realizedContributionGbp,
    winnerStage: input.diagnosis.winnerStage,
    nextDecision: input.diagnosis.decision,
    reusable,
    evidenceRefs: [...input.evidenceRefs],
  };
}

export interface LearningStore{load():LearningRecord[];save(records:LearningRecord[]):void}
export const LEARNING_STORAGE_KEY='tiktok-profit-agent:learning:v1';
function assertLearning(value:unknown):asserts value is LearningRecord{
 const r=value as LearningRecord;
 if(!r||typeof r.learningId!=='string'||!r.learningId.trim()||!r.trace||
  [r.trace.decisionId,r.trace.experimentId,r.trace.opportunityId,r.trace.creativeId].some(id=>typeof id!=='string'||!id.trim())||
  r.market!=='UK'||!['PROFIT','LOSS','BREAK_EVEN','REFUND','IMMATURE'].includes(r.outcome)||
  !(r.realizedContributionGbp===null||(typeof r.realizedContributionGbp==='number'&&Number.isFinite(r.realizedContributionGbp)))||
  (r.outcome==='PROFIT'&&(r.realizedContributionGbp===null||r.realizedContributionGbp<=0))||
  !Array.isArray(r.evidenceRefs)||!r.evidenceRefs.length||r.evidenceRefs.some(ref=>typeof ref!=='string'||!ref.trim())||
  typeof r.reusable!=='boolean'||(r.reusable&&(r.outcome!=='PROFIT'||r.winnerStage!=='REPEATABILITY_VALIDATED')))
  throw new Error('Invalid persisted learning record');
}
function assertLearnings(value:unknown):asserts value is LearningRecord[]{
 if(!Array.isArray(value))throw new Error('Corrupted learning store');
 const ids=new Set<string>();for(const record of value){assertLearning(record);if(ids.has(record.learningId))throw new Error('Duplicate persisted learning identity');ids.add(record.learningId)}
}
export class BrowserLearningStore implements LearningStore{constructor(private readonly storage:Pick<Storage,'getItem'|'setItem'>){}load(){const raw=this.storage.getItem(LEARNING_STORAGE_KEY);if(!raw)return [];const x:unknown=JSON.parse(raw);assertLearnings(x);return structuredClone(x)}save(records:LearningRecord[]){assertLearnings(records);this.storage.setItem(LEARNING_STORAGE_KEY,JSON.stringify(records))}}
export class LearningMemory {
  private readonly records = new Map<string, LearningRecord>();
  constructor(private readonly store?:LearningStore){const loaded=store?.load()??[];assertLearnings(loaded);for(const r of loaded)this.records.set(r.learningId,structuredClone(r))}

  remember(record: LearningRecord): { record: LearningRecord; duplicate: boolean } {
    assertLearning(record);
    const existing = this.records.get(record.learningId);
    if (existing){if(JSON.stringify(existing)!==JSON.stringify(record))throw new Error('Conflicting learning identity');return { record: structuredClone(existing), duplicate: true }}
    this.records.set(record.learningId, structuredClone(record));
    try{this.store?.save([...this.records.values()].map(r=>structuredClone(r)))}catch(error){this.records.delete(record.learningId);throw error}
    return { record: structuredClone(record), duplicate: false };
  }

  all(): LearningRecord[] { return [...this.records.values()].map((record) => structuredClone(record)); }

  reusableLearnings(): LearningRecord[] {
    return [...this.records.values()].filter((record) => record.reusable).map((record) => structuredClone(record));
  }
}
