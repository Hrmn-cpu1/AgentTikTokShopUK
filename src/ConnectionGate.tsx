import { useEffect, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { App as NativeApp } from '@capacitor/app';
import { Browser } from '@capacitor/browser';

type Capability = 'AVAILABLE' | 'REQUIRES_APPROVAL' | 'BLOCKED' | 'UNKNOWN';
type Connection = { connectionId:string; providerUserId:string; displayName:string|null;
  status:'ACTIVE'|'EXPIRED'|'REVOKED'|'REFRESH_FAILED'|'UNKNOWN'; tokenStatus:string;
  connectedAt:string; lastValidatedAt:string; grantedScopes:string[]; manualVerification?:{
    source:string;ukMarketEvidenceRef:string|null;affiliateEvidenceRef:string|null;observedAt:string|null;valid:boolean} };
type State = { connection:Connection|null; capabilities:Record<string,Capability>; mode:'LIMITED'|'BLOCKED'|'MANUAL_VERIFIED'; authorizationConfigured?:boolean };

const labels:Record<string,string> = {IDENTITY:'Identity',TIKTOK_SHOP:'Shop',AFFILIATE:'Affiliate',
  PRODUCT_DISCOVERY:'Products',CONTENT_PUBLISHING:'Publishing',ORDER_READ:'Orders',
  COMMISSION_READ:'Commission',SETTLEMENT_READ:'Settlement'};

async function json<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch(path, {credentials:'same-origin',...init});
  if (!response.ok) throw new Error(response.status===401?'Operator session expired':
    response.status===503?'Server configuration required':`Connection check failed (${response.status})`);
  return response.json() as Promise<T>;
}

export default function ConnectionGate({children}:{children:React.ReactNode}) {
  const native=Capacitor.isNativePlatform();
  const nativeBackendConfigured=window.location.protocol==='https:' && window.location.hostname!=='localhost';
  const [phase,setPhase] = useState<'loading'|'login'|'connection'|'error'>('loading');
  const [connection,setConnection] = useState<State|null>(null);
  const [accessKey,setAccessKey] = useState('');
  const [message,setMessage] = useState('');
  const [limitedOpen,setLimitedOpen] = useState(false);
  const [ukReference,setUkReference] = useState('');
  const [affiliateReference,setAffiliateReference] = useState('');
  const refresh = async () => {
    try {
      await json('/v1/operator/session');
    } catch (error) {
      if (error instanceof Error && error.message==='Operator session expired') {setPhase('login');return;}
      setMessage(error instanceof Error?error.message:'Server unavailable');setPhase('error');return;
    }
    try {setConnection(await json<State>('/v1/tiktok/connection'));setPhase('connection');}
    catch (error) {setMessage(error instanceof Error?error.message:'Server unavailable');setPhase('error');}
  };
  useEffect(()=>{
    if(native && !nativeBackendConfigured)return;
    void refresh();
    const timer=window.setInterval(()=>{void refresh()},60_000);
    const visible=()=>{if(document.visibilityState==='visible')void refresh()};
    document.addEventListener('visibilitychange',visible);
    return ()=>{window.clearInterval(timer);document.removeEventListener('visibilitychange',visible)};
  },[]);

  useEffect(()=>{
    if(!native || !nativeBackendConfigured)return;
    const back=NativeApp.addListener('backButton',()=>{
      if(limitedOpen)setLimitedOpen(false);
      else void NativeApp.minimizeApp();
    });
    const link=NativeApp.addListener('appUrlOpen',({url})=>{
      if(url==='com.tiktokshopprofitagent.app://oauth-return')void refresh();
    });
    const active=NativeApp.addListener('appStateChange',({isActive})=>{if(isActive)void refresh()});
    return ()=>{void Promise.all([back,link,active]).then(handles=>handles.forEach(handle=>void handle.remove()))};
  },[native,nativeBackendConfigured,limitedOpen]);

  const startTikTok = async () => {
    setMessage('');
    try {
      if(native){
        const response=await json<{authorizationUrl:string}>('/v1/tiktok/authorize-native');
        const url=new URL(response.authorizationUrl);
        if(url.origin!=='https://www.tiktok.com' || url.pathname!=='/v2/auth/authorize/')throw new Error('TikTok authorization address is invalid');
        await Browser.open({url:url.href});
      }else window.location.assign('/v1/tiktok/authorize');
    }catch(error){setMessage(error instanceof Error?error.message:'TikTok authorization unavailable')}
  };

  if(native && !nativeBackendConfigured)return <div className="connection-shell"><h1>TikTok Shop Profit Agent 🇬🇧</h1>
    <p>Connect your TikTok account to start.</p><button className="connection-primary" disabled>Continue with TikTok</button>
    <p className="connection-warning">BACKEND UNAVAILABLE · This APK has no production HTTPS backend configured. Login and TikTok connection are disabled.</p>
    <p className="connection-note">This is an installable Android test build. No account or commercial result is connected.</p></div>;

  const login = async (event:React.FormEvent) => {
    event.preventDefault();setMessage('');
    try {
      await json('/v1/operator/login',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({access_key:accessKey})});
      setAccessKey('');await refresh();
    } catch (error) {setMessage(error instanceof Error?error.message:'Login failed');}
  };
  const disconnect = async () => {
    if (!window.confirm('Disconnect TikTok? Historical experiments and money records will remain.')) return;
    setMessage('');
    try {
      const csrf = decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('operator_csrf='))?.split('=')[1]??'');
      await json('/v1/tiktok/disconnect',{method:'POST',headers:{'X-CSRF-Token':csrf}});
    } catch (error) {setMessage(error instanceof Error?error.message:'Disconnect needs reconciliation');}
    setLimitedOpen(false);await refresh();
  };
  const verifyManually = async (event:React.FormEvent) => {
    event.preventDefault();setMessage('');
    try {
      const csrf = decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('operator_csrf='))?.split('=')[1]??'');
      setConnection(await json<State>('/v1/tiktok/manual-verification',{method:'POST',
        headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
        body:JSON.stringify({uk_market_evidence_ref:ukReference,affiliate_evidence_ref:affiliateReference})}));
      setUkReference('');setAffiliateReference('');
    } catch (error) {setMessage(error instanceof Error?error.message:'Evidence was not recorded');}
  };
  if (phase==='loading') return <div className="connection-shell"><h1>TikTok Shop Profit Agent 🇬🇧</h1><p>Checking your connection…</p></div>;
  if (phase==='error') return <div className="connection-shell"><h1>Connection check unavailable</h1><p>{message}</p><button onClick={()=>{setPhase('loading');void refresh()}}>Retry</button></div>;
  if (phase==='login') return <div className="connection-shell"><h1>TikTok Shop Profit Agent 🇬🇧</h1>
    <p>Sign in as the operator to continue.</p><form onSubmit={event=>{void login(event)}}>
      <label>Operator access key<input type="password" autoComplete="current-password" value={accessKey}
        onChange={event=>setAccessKey(event.target.value)} required/></label><button className="connection-primary">Continue</button>
    </form>{message&&<p role="alert">{message}</p>}</div>;
  if (!connection?.connection || connection.connection.status==='REVOKED') return <div className="connection-shell">
    <h1>TikTok Shop Profit Agent 🇬🇧</h1><p>Connect your TikTok account to start.</p>
    {connection?.authorizationConfigured?<button className="connection-primary" onClick={()=>{void startTikTok()}}>Continue with TikTok</button>:
      <><button className="connection-primary" disabled>Continue with TikTok</button><p>Official TikTok developer app credentials and server encryption are required before connecting.</p></>}
    <p className="connection-note">The agent only operates with permissions explicitly granted by your TikTok account. Connecting does not grant Shop, Affiliate or publishing access.</p>
    {message&&<p role="alert">{message}</p>}</div>;
  const active=connection.connection.status==='ACTIVE' && connection.capabilities.IDENTITY==='AVAILABLE';
  return <div className="connection-shell"><h1>TikTok Shop Profit Agent 🇬🇧</h1>
    <div className="connection-card"><strong>TikTok · {connection.connection.displayName??'Account'}</strong>
      <span>{active?'CONNECTED':'CONNECTION NEEDS ATTENTION'}</span><small>Identity: {connection.connection.providerUserId}</small></div>
    <h2>Account capabilities</h2><div className="capability-list">
      {Object.entries(labels).map(([key,label])=><div key={key}><span>{label}</span>
        <b className={connection.capabilities[key]==='AVAILABLE'?'known':''}>{connection.capabilities[key]??'UNKNOWN'}</b></div>)}
    </div><p className="connection-note">Shop, Affiliate, orders and settlement need their own evidence. TikTok Login Kit only verifies identity. Market and UK Shop status are still unknown.</p>
    {active?<><p className="connection-warning">{connection.mode==='MANUAL_VERIFIED'?'MANUAL VERIFIED MODE · Account and affiliate evidence is operator asserted, not verified through a TikTok Shop API.':'LIMITED MODE · UK Shop and Affiliate access still require evidence.'}</p>
      {connection.mode!=='MANUAL_VERIFIED'&&<form onSubmit={event=>{void verifyManually(event)}}>
        <label>UK Shop or market status evidence reference<input value={ukReference} onChange={event=>setUkReference(event.target.value)} minLength={6} required/></label>
        <label>Affiliate access evidence reference<input value={affiliateReference} onChange={event=>setAffiliateReference(event.target.value)} minLength={6} required/></label>
        <p className="connection-note">Record references to what you personally checked in TikTok Shop. Do not enter credentials or identity documents. These are manual assertions valid for 30 days.</p>
        <button>Record manual verification</button></form>}
      {connection.mode==='MANUAL_VERIFIED'&&<><p className="connection-note">UK: {connection.connection.manualVerification?.ukMarketEvidenceRef} · Affiliate: {connection.connection.manualVerification?.affiliateEvidenceRef}</p>
        <button onClick={()=>setLimitedOpen(true)}>Open manual workspace</button></>}
    </>:<button className="connection-primary" onClick={()=>{void startTikTok()}}>Reconnect TikTok</button>}
    <button className="connection-secondary" onClick={()=>{void disconnect()}}>Disconnect TikTok</button>
    {message&&<p role="alert">{message}</p>}
    {limitedOpen&&active&&connection.mode==='MANUAL_VERIFIED'&&<div className="limited-workspace"><button onClick={()=>setLimitedOpen(false)}>Back to account status</button>{children}</div>}
  </div>;
}
