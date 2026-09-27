import type { ActionRecord, CommerceEvent } from './actionEventLedger';

export type LedgerSnapshot={actions:ActionRecord[];events:CommerceEvent[]};
export interface BusinessTruthStore{load():LedgerSnapshot;save(snapshot:LedgerSnapshot):void}

export const BUSINESS_TRUTH_STORAGE_KEY='tiktok-profit-agent:business-truth:v1';

export class BrowserBusinessTruthStore implements BusinessTruthStore{
 constructor(private readonly storage:Pick<Storage,'getItem'|'setItem'>){}
 load():LedgerSnapshot{
  const raw=this.storage.getItem(BUSINESS_TRUTH_STORAGE_KEY);
  if(!raw) return {actions:[],events:[]};
  try{
   const x=JSON.parse(raw) as Partial<LedgerSnapshot>;
   return {actions:Array.isArray(x.actions)?x.actions:[],events:Array.isArray(x.events)?x.events:[]};
  }catch{return {actions:[],events:[]}}
 }
 save(snapshot:LedgerSnapshot):void{this.storage.setItem(BUSINESS_TRUTH_STORAGE_KEY,JSON.stringify(snapshot))}
}

export class MemoryBusinessTruthStore implements BusinessTruthStore{
 private snapshot:LedgerSnapshot={actions:[],events:[]};
 load(){return structuredClone(this.snapshot)}
 save(snapshot:LedgerSnapshot){this.snapshot=structuredClone(snapshot)}
}
