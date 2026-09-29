import {describe,expect,it} from 'vitest';
import {executionCutoverState,readExecutionEnabled,writeExecutionEnabled,EXECUTION_STORAGE_KEY} from './realityCutoverGuard';

describe('reality cutover guard',()=>{
 it('defaults execution to false when no operator setting exists',()=>expect(readExecutionEnabled({getItem:()=>null})).toBe(false));
 it('only accepts exact persisted true',()=>expect(readExecutionEnabled({getItem:()=> 'TRUE'})).toBe(false));
 it('persists explicit operator enablement',()=>{let value:string|null=null;writeExecutionEnabled({setItem:(k,v)=>{expect(k).toBe(EXECUTION_STORAGE_KEY);value=v}},true);expect(value).toBe('true')});
 it('safe mode never grants external execution',()=>expect(executionCutoverState(false).externalExecutionAllowed).toBe(false));
 it('operator-enabled readiness still does not grant external effects',()=>expect(executionCutoverState(true).externalExecutionAllowed).toBe(false));
});
