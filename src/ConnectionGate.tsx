import { useEffect, useState } from 'react';
import { Capacitor } from '@capacitor/core';
import { App as NativeApp } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { apiJson as json, operatorCsrf } from './apiClient';
import GrowthStudio from './GrowthStudio';

type Capability = 'AVAILABLE' | 'REQUIRES_APPROVAL' | 'BLOCKED' | 'UNKNOWN';
type Connection = { connectionId:string; providerUserId:string; displayName:string|null;
  status:'ACTIVE'|'EXPIRED'|'REVOKED'|'REFRESH_FAILED'|'UNKNOWN'; tokenStatus:string;
  connectedAt:string; lastValidatedAt:string; grantedScopes:string[]; manualVerification?:{
    source:string;ukMarketEvidenceRef:string|null;affiliateEvidenceRef:string|null;observedAt:string|null;valid:boolean} };
type State = { connection:Connection|null; capabilities:Record<string,Capability>; mode:'LIMITED'|'BLOCKED'|'MANUAL_VERIFIED'; authorizationConfigured?:boolean };

const labels:Record<string,string> = {IDENTITY:'Identidade',TIKTOK_SHOP:'Loja',AFFILIATE:'Afiliado',
  PRODUCT_DISCOVERY:'Produtos',CONTENT_PUBLISHING:'Publicação',ORDER_READ:'Pedidos',
  COMMISSION_READ:'Comissão',SETTLEMENT_READ:'Liquidação'};
const statusText:Record<Capability,string> = {AVAILABLE:'DISPONÍVEL',REQUIRES_APPROVAL:'EXIGE APROVAÇÃO',BLOCKED:'BLOQUEADO',UNKNOWN:'DESCONHECIDO'};

export default function ConnectionGate() {
  const native=Capacitor.isNativePlatform();
  const nativeBackendConfigured=window.location.protocol==='https:' && window.location.hostname!=='localhost';
  const [phase,setPhase] = useState<'loading'|'login'|'connection'|'error'>('loading');
  const [connection,setConnection] = useState<State|null>(null);
  const [accessKey,setAccessKey] = useState('');
  const [message,setMessage] = useState('');
  const refresh = async () => {
    try {
      await json('/v1/operator/session');
    } catch (error) {
      if (error instanceof Error && error.message==='Operator session expired') {setPhase('login');return;}
      setMessage(error instanceof Error?error.message:'Servidor indisponível');setPhase('error');return;
    }
    try {setConnection(await json<State>('/v1/tiktok/connection'));setPhase('connection');}
    catch (error) {setMessage(error instanceof Error?error.message:'Servidor indisponível');setPhase('error');}
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
      void NativeApp.minimizeApp();
    });
    const active=NativeApp.addListener('appStateChange',({isActive})=>{if(isActive)void refresh()});
    return ()=>{void Promise.all([back,active]).then(handles=>handles.forEach(handle=>void handle.remove()))};
  },[native,nativeBackendConfigured]);

  useEffect(()=>{
    if(!native)return;
    let disposed=false;
    let browserListener:{remove:()=>Promise<void>}|undefined;
    void Browser.addListener('browserFinished',()=>{if(!disposed)void refresh()}).then(handle=>{
      if(disposed)void handle.remove();
      else browserListener=handle;
    });
    return ()=>{disposed=true;if(browserListener)void browserListener.remove()};
  },[native]);

  const startTikTok = async () => {
    setMessage('');
    try {
      if(native){
        const response=await json<{authorizationUrl:string}>('/v1/tiktok/native-web-intent',
          {method:'POST',headers:{'X-CSRF-Token':operatorCsrf()}});
        await Browser.open({url:response.authorizationUrl});
      }else window.location.assign('/v1/tiktok/authorize');
    }catch(error){setMessage(error instanceof Error?error.message:'Autorização do TikTok indisponível')}
  };

  if(native && !nativeBackendConfigured)return <div className="connection-shell"><h1>AgentTikTok Shop</h1>
    <p>Conecte sua conta TikTok para começar.</p><button className="connection-primary" disabled>Continuar com TikTok</button>
    <p className="connection-warning">SERVIDOR INDISPONÍVEL · Este APK não tem servidor HTTPS configurado.</p>
    <p className="connection-note">Versão de teste Android. Não há conta nem receita conectada.</p></div>;

  const login = async (event:React.FormEvent) => {
    event.preventDefault();setMessage('');
    try {
      await json('/v1/operator/login',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({access_key:accessKey})});
      setAccessKey('');await refresh();
    } catch (error) {setMessage(error instanceof Error?error.message:'Falha ao entrar');}
  };
  const disconnect = async () => {
    if (!window.confirm('Desconectar TikTok? Os registros históricos serão preservados.')) return;
    setMessage('');
    try {
      const csrf = operatorCsrf();
      await json('/v1/tiktok/disconnect',{method:'POST',headers:{'X-CSRF-Token':csrf}});
    } catch (error) {setMessage(error instanceof Error?error.message:'Não foi possível desconectar');}
    await refresh();
  };
  const legal = <footer className="connection-note"><a href="/terms.html">Termos de Serviço</a> · <a href="/privacy.html">Política de Privacidade</a></footer>;
  if (phase==='loading') return <div className="connection-shell"><h1>AgentTikTok Shop</h1><p>Plataforma para criar, gerenciar e publicar conteúdo em vídeo com autorização do usuário.</p><p>Verificando conexão…</p>{legal}</div>;
  if (phase==='error') return <div className="connection-shell"><h1>Conexão indisponível</h1><p>{message}</p><button onClick={()=>{setPhase('loading');void refresh()}}>Tentar novamente</button></div>;
  if (phase==='login') return <div className="connection-shell"><h1>AgentTikTok Shop</h1>
    <p>Entre como operador para continuar.</p><form onSubmit={event=>{void login(event)}}>
      <label>Chave de acesso do operador<input type="password" autoComplete="current-password" value={accessKey}
        onChange={event=>setAccessKey(event.target.value)} required/></label><button className="connection-primary">Continuar</button>
    </form>{message&&<p role="alert">{message}</p>}</div>;
  if (!connection?.connection || connection.connection.status==='REVOKED') return <div className="connection-shell">
    <h1>AgentTikTok Shop</h1><p>Conecte sua conta TikTok para começar.</p>
    {connection?.authorizationConfigured?<button className="connection-primary" onClick={()=>{void startTikTok()}}>Continuar com TikTok</button>:
      <><button className="connection-primary" disabled>Continuar com TikTok</button><p>É necessário configurar o aplicativo oficial de desenvolvedor e a criptografia no servidor.</p></>}
    <p className="connection-note">A conexão verifica a identidade. A publicação usa apenas as permissões autorizadas pelo próprio usuário.</p>{legal}
    <GrowthStudio />
    {message&&<p role="alert">{message}</p>}</div>;
  const active=connection.connection.status==='ACTIVE' && connection.capabilities.IDENTITY==='AVAILABLE';
  return <div className="connection-shell"><h1>AgentTikTok Shop</h1>
    <div className="connection-card"><strong>TikTok · {connection.connection.displayName??'Conta'}</strong>
      <span>{active?'CONECTADO':'CONEXÃO PRECISA DE ATENÇÃO'}</span><small>Identidade: {connection.connection.providerUserId}</small></div>
    <h2>Permissões da conta</h2><div className="capability-list">
      {Object.entries(labels).map(([key,label])=><div key={key}><span>{label}</span>
        <b className={connection.capabilities[key]==='AVAILABLE'?'known':''}>{statusText[connection.capabilities[key]]??'DESCONHECIDO'}</b></div>)}
    </div><p className="connection-note">O Login Kit confirma identidade, mas não aprova Shop, afiliação, publicação ou saque.</p>
    {active?<><p className="connection-warning">Brasil · Operação de afiliado ainda bloqueada: o servidor mantém registros históricos em GBP. A migração de dados e a aprovação da conta precisam ser comprovadas antes de registrar vendas em R$.</p>
      <GrowthStudio />
    </>:<button className="connection-primary" onClick={()=>{void startTikTok()}}>Reconectar TikTok</button>}
    <button className="connection-secondary" onClick={()=>{void disconnect()}}>Desconectar TikTok</button>
    {message&&<p role="alert">{message}</p>}{legal}
  </div>;
}
