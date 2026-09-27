import {describe,expect,it} from 'vitest';
import {BrowserBusinessTruthStore,MemoryBusinessTruthStore} from './businessTruthStore';
describe('business truth store',()=>{
 it('memory store survives consumer reconstruction',()=>{const s=new MemoryBusinessTruthStore();s.save({actions:[],events:[{eventId:'e',source:'x',externalEventId:'1',experimentId:'EXP',actionId:null,type:'ORDER_CREATED',occurredAt:'2026-09-27T10:00:00Z',amountGbp:null}]});expect(s.load().events).toHaveLength(1)});
 it('browser store fails closed on corrupt JSON',()=>expect(new BrowserBusinessTruthStore({getItem:()=>'{bad',setItem:()=>{}}).load()).toEqual({actions:[],events:[]}));
});
