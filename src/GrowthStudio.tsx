import { useEffect, useState, type FormEvent } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { operatorCsrf } from './apiClient';

const TikTokShare = registerPlugin<{ shareVideo(options:{base64:string}):Promise<{state:'TIKTOK_INTENT_STARTED'|'SHARE_CHOOSER_OPENED'}> }>('TikTokShare');

/** Operator supplied creative export. Kept separate from the automatic content pipeline. */
export default function GrowthStudio(){
  const [photo,setPhoto]=useState<File|null>(null);const [headline,setHeadline]=useState('');const [message,setMessage]=useState('');const [callToAction,setCallToAction]=useState('');
  const [video,setVideo]=useState('');const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [sent,setSent]=useState('');
  useEffect(()=>()=>{if(video)URL.revokeObjectURL(video)},[video]);
  const generate=async(event:FormEvent)=>{event.preventDefault();if(!photo)return;setError('');setBusy(true);const data=new FormData();data.set('photo',photo);data.set('headline',headline);data.set('message',message);data.set('call_to_action',callToAction);
    try{const response=await fetch('/v1/creator-video',{method:'POST',headers:{'X-CSRF-Token':operatorCsrf()},body:data,credentials:'same-origin'});if(!response.ok)throw new Error(response.status===401?'Entre novamente no aplicativo':response.status===413?'A foto deve ter até 3 MB':'Não foi possível gerar o vídeo');setVideo(URL.createObjectURL(await response.blob()));setSent('')}catch(e){setError(e instanceof Error?e.message:'Erro ao produzir o vídeo')}finally{setBusy(false)}};
  const share=async()=>{try{const clip=await(await fetch(video)).blob();let handoffState:'TIKTOK_INTENT_STARTED'|'SHARE_CHOOSER_OPENED'|'SHARE_SHEET_OPENED'='SHARE_SHEET_OPENED';if(Capacitor.getPlatform()!=='web'){const bytes=new Uint8Array(await clip.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));handoffState=(await TikTokShare.shareVideo({base64:btoa(binary)})).state}else{const file=new File([clip],'manual-agent-video.mp4',{type:'video/mp4'});if(!navigator.canShare?.({files:[file]}))throw new Error('Compartilhamento indisponível');await navigator.share({files:[file],title:'Vídeo manual'})}setSent(handoffState==='TIKTOK_INTENT_STARTED'?'Intent direcionado ao TikTok iniciado; importação e publicação não foram confirmadas.':handoffState==='SHARE_CHOOSER_OPENED'?'Seletor de compartilhamento aberto; escolha TikTok. Importação e publicação não foram confirmadas.':'Folha de compartilhamento aberta; destino e publicação não foram confirmados.') }catch(e){if(e instanceof Error&&e.name!=='AbortError')setError(e.message)}};
  return <section className="growth-studio"><p className="gw-manual-tag">MANUAL MODE · Você escolhe a imagem e escreve o conteúdo</p><form onSubmit={event=>void generate(event)}>
    <label>Imagem licenciada<input type="file" accept="image/jpeg,image/png,image/webp" required onChange={event=>setPhoto(event.target.files?.[0]??null)}/></label>
    <label>Hook<input maxLength={95} required value={headline} onChange={event=>setHeadline(event.target.value)} placeholder="Chamada inicial"/></label>
    <label>Mensagem<input maxLength={95} required value={message} onChange={event=>setMessage(event.target.value)} placeholder="Informação verdadeira"/></label>
    <label>CTA<input maxLength={95} required value={callToAction} onChange={event=>setCallToAction(event.target.value)} placeholder="Convite final"/></label>
    <button disabled={busy||!photo}>{busy?'Renderizando…':'Renderizar MP4 manual'}</button>
  </form>{video&&<><video controls playsInline src={video} aria-label="Prévia de vídeo manual"/><a href={video} download="agent-tiktok-manual.mp4">Baixar MP4</a><button type="button" onClick={()=>void share()}>Enviar ao TikTok para revisão</button>{sent&&<p>{sent}</p>}</>}{error&&<p role="alert" className="connection-warning">{error}</p>}</section>;
}
