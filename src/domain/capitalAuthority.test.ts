import {describe,expect,it} from 'vitest';
import {createCapitalAuthority,loadCapitalAuthority,saveCapitalAuthority} from './capitalAuthority';
const a={limits:{availableCapital:20,capitalLimit:8,lossLimit:5,minimumAllocationScore:65},approvedAt:'2026-09-27T04:00:00Z',evidenceRef:'operator-budget:1'};
describe('capital authority',()=>{
 it('preserves explicit operator limits',()=>expect(createCapitalAuthority(a).limits).toEqual(a.limits));
 it('rejects invalid limits',()=>expect(()=>createCapitalAuthority({...a,limits:{...a.limits,lossLimit:-1}})).toThrow());
 it('fails closed when absent',()=>expect(loadCapitalAuthority({getItem:()=>null})).toBeNull());
 it('round trips durable authority',()=>{let raw:string|null=null;const s={getItem:()=>raw,setItem:(_k:string,v:string)=>{raw=v}};saveCapitalAuthority(s,a);expect(loadCapitalAuthority(s)).toEqual(a)});
});
