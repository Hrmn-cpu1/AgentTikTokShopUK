import { describe, expect, it } from 'vitest';
import { BrowserRealityEvidenceStore, hydrateRealityRegistry, persistRealityEvidence, REALITY_STORAGE_KEY } from './realityPersistence';
import { RealityEvidenceRegistry, type RealityEvidence } from './realityEvidenceRegistry';

const item:RealityEvidence={evidenceId:'E1',subject:'AFFILIATE_ACCESS',state:'VERIFIED',source:'TIKTOK_UI',observedAt:'2026-09-27T17:00:00Z',validUntil:null,reference:'creator-center:affiliate',containsSensitiveData:false};
function storage(initial:string|null=null){let value=initial;return {getItem:()=>value,setItem:(_k:string,v:string)=>{value=v},value:()=>value};}

describe('reality persistence',()=>{
 it('round-trips evidence across a fresh registry',()=>{
  const s=storage(); const store=new BrowserRealityEvidenceStore(s);
  persistRealityEvidence(store,[item]);
  const r=hydrateRealityRegistry(store);
  expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T17:01:00Z').state).toBe('VERIFIED');
 });
 it('uses a versioned storage key',()=>{expect(REALITY_STORAGE_KEY).toContain(':v1')});
 it('fails closed on malformed JSON',()=>{
  const r=hydrateRealityRegistry(new BrowserRealityEvidenceStore(storage('{bad')));
  expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T17:01:00Z').state).toBe('UNKNOWN');
 });
 it('fails closed on invalid or unsafe stored evidence',()=>{
  const unsafe=JSON.stringify([{...item,containsSensitiveData:true}]);
  const r=hydrateRealityRegistry(new BrowserRealityEvidenceStore(storage(unsafe)));
  expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T17:01:00Z').state).toBe('UNKNOWN');
 });
 it('preserves freshness semantics after reload',()=>{
  const exp={...item,validUntil:'2026-09-27T17:30:00Z'}; const s=storage(JSON.stringify([exp]));
  const r=hydrateRealityRegistry(new BrowserRealityEvidenceStore(s));
  expect(r.resolve('AFFILIATE_ACCESS','2026-09-27T18:00:00Z').state).toBe('UNKNOWN');
 });

  it('preserves original provenance across persistence and hydration',()=>{
    const original={evidenceId:'ev-prov-1',subject:'AFFILIATE_ACCESS' as const,state:'VERIFIED' as const,source:'TIKTOK_OFFICIAL' as const,observedAt:'2026-09-27T01:00:00Z',validUntil:'2026-09-28T01:00:00Z',reference:'official-screen:affiliate-access',containsSensitiveData:false as const};
    const memory:{raw:string|null}={raw:null};
    const store=new BrowserRealityEvidenceStore({getItem:()=>memory.raw,setItem:(_k,v)=>{memory.raw=v}});
    const registry=new RealityEvidenceRegistry(); registry.record(original);
    persistRealityEvidence(store,registry.allEvidence());
    const recovered=hydrateRealityRegistry(store);
    expect(recovered.allEvidence()).toEqual([original]);
  });
});
