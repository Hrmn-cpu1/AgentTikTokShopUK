import type {LearningRecord} from './learningLoop';
export type RepeatabilityVerdict={status:'NOT_PROVEN'|'PROVEN';profitableExperimentIds:string[];repeatableWinnerProven:boolean;scaleEligible:boolean;reason:string};
export function evaluateRepeatability(records:readonly LearningRecord[]):RepeatabilityVerdict{
 const profitable=new Set<string>();
 for(const r of records){
  if(r.outcome==='PROFIT'&&r.realizedContributionGbp!==null&&r.realizedContributionGbp>0&&r.evidenceRefs.length>0)profitable.add(r.trace.experimentId);
 }
 const ids=[...profitable].sort(),proven=ids.length>=2;
 return Object.freeze({status:proven?'PROVEN':'NOT_PROVEN',profitableExperimentIds:ids,repeatableWinnerProven:proven,scaleEligible:proven,reason:proven?'Positive realized economics are evidenced across at least two distinct experiments.':'Repeatability requires positive realized economics from at least two distinct experiments.'});
}
