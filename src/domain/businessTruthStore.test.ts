import {describe,expect,it} from 'vitest';
import {BrowserBusinessTruthStore,MemoryBusinessTruthStore} from './businessTruthStore';
describe('business truth store',()=>{
 it('memory store survives consumer reconstruction',()=>{const s=new MemoryBusinessTruthStore();s.save({actions:[],events:[{eventId:'e',source:'x',externalEventId:'1',experimentId:'EXP',actionId:null,type:'ORDER_CREATED',occurredAt:'2026-09-27T10:00:00Z',amountGbp:null,evidenceRef:'proof:e'}]});expect(s.load().events).toHaveLength(1)});
 it('browser store fails closed on corrupt JSON',()=>expect(()=>new BrowserBusinessTruthStore({getItem:()=>'{bad',setItem:()=>{}}).load()).toThrow());
 it('rejects a persisted settlement without a real amount or evidence',()=>expect(()=>new BrowserBusinessTruthStore({getItem:()=>JSON.stringify({actions:[],events:[{eventId:'e',source:'manual',externalEventId:'s1',experimentId:'EXP-001',actionId:null,type:'COMMISSION_SETTLED',occurredAt:'2026-09-27T10:00:00Z',amountGbp:null}]}),setItem:()=>{}}).load()).toThrow());
});
