import {describe,expect,it} from 'vitest';
import {loadRealOpportunityProjection} from './domain/realOpportunityProjection';

function storage(){const m=new Map<string,string>();return {getItem:(k:string)=>m.get(k)??null,setItem:(k:string,v:string)=>{m.set(k,v)},removeItem:(k:string)=>m.delete(k),clear:()=>m.clear(),key:()=>null,get length(){return m.size}} as Storage}

describe('reality UI cutover',()=>{
 it('projects no opportunity score when persisted business truth is absent',()=>{
  const projection=loadRealOpportunityProjection(storage(),'2026-09-27T06:00:00Z');
  expect(projection.product).toBeNull();
  expect(projection.result).toBeNull();
  expect(projection.blockers).toContain('REAL_PRODUCT:MISSING');
 });
});
