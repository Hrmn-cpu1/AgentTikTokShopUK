import { useEffect, useState, type FormEvent } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { operatorCsrf } from './apiClient';

const TikTokShare = registerPlugin<{ shareVideo(options:{base64:string}):Promise<void> }>('TikTokShare');

export default function GrowthStudio() {
  const [photo,setPhoto]=useState<File|null>(null);
  const [headline,setHeadline]=useState('');
  const [message,setMessage]=useState('');
  const [callToAction,setCallToAction]=useState('');
  const [video,setVideo]=useState('');
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [followers,setFollowers]=useState('');
  const [agentBusy,setAgentBusy]=useState(false);
  const [agentResult,setAgentResult]=useState<{topic:string; source:string; score:number; evidence:string}|null>(null);
  const [deliveryMessage,setDeliveryMessage]=useState('');
  useEffect(()=>()=>{if(video)URL.revokeObjectURL(video)},[video]);

  const generate=async(event:FormEvent)=>{
    event.preventDefault();
    if(!photo)return;
    setError('');setBusy(true);
    const data=new FormData();
    data.set('photo',photo);data.set('headline',headline);data.set('message',message);
    data.set('call_to_action',callToAction);
    try {
      const response=await fetch('/v1/creator-video',{method:'POST',headers:{'X-CSRF-Token':operatorCsrf()},body:data,credentials:'same-origin'});
      if(!response.ok)throw new Error(response.status===401?'Entre novamente no aplicativo':
        response.status===413?'A foto deve ter até 3 MB':'Não foi possível gerar o vídeo; revise a foto e os textos');
      const clip=await response.blob();
      setVideo(URL.createObjectURL(clip));
    }catch(cause){setError(cause instanceof Error?cause.message:'Erro ao produzir o vídeo')}
    finally{setBusy(false)}
  };
  const shareClip=async(clip:Blob)=>{
    if(Capacitor.getPlatform()!=='web'){
      const bytes=new Uint8Array(await clip.arrayBuffer());
      let binary='';
      for(let offset=0;offset<bytes.length;offset+=0x8000)binary+=String.fromCharCode(...bytes.subarray(offset,offset+0x8000));
      await TikTokShare.shareVideo({base64:btoa(binary)});
      setDeliveryMessage('TikTok aberto para revisão. O compositor ainda exige que você revise e conclua a publicação; o app não mede os toques feitos dentro do TikTok.');
      return;
    }
    const file=new File([clip],'agent-tiktok-shop.mp4',{type:'video/mp4'});
    if(!navigator.canShare?.({files:[file]}))throw new Error('Compartilhamento de vídeo indisponível neste celular; tente Baixar vídeo');
    await navigator.share({files:[file],title:'Vídeo original'});
    setDeliveryMessage('Folha de compartilhamento aberta. Escolha TikTok e conclua a publicação dentro do TikTok.');
  };
  const runAgent=async()=>{
    setError('');setAgentBusy(true);
    try {
      const response=await fetch('/v1/growth/run',{method:'POST',headers:{'X-CSRF-Token':operatorCsrf()},credentials:'same-origin'});
      if(!response.ok)throw new Error(response.status===401?'Entre novamente no aplicativo':
        response.status===503?'Fonte pública indisponível agora; tente novamente mais tarde':'Não foi possível executar o experimento');
      const result=await response.json();
      const media=await fetch(result.videoUrl,{credentials:'same-origin'});
      if(!media.ok)throw new Error('O plano foi criado, mas o render MP4 falhou');
      const clip=await media.blob();
      setVideo(URL.createObjectURL(clip));
      setAgentResult({topic:result.selected.topic,source:result.source,score:result.selected.score,evidence:result.plan.sourceEvidence.evidence});
      if(Capacitor.getPlatform()!=='web')await shareClip(clip);
    }catch(cause){setError(cause instanceof Error?cause.message:'Erro no experimento')}
    finally{setAgentBusy(false)}
  };
  const share=async()=>{
    if(!video)return;
    try {
      const clip=await (await fetch(video,{credentials:'same-origin'})).blob();
      await shareClip(clip);
    }catch(cause){if(cause instanceof Error && cause.name!=='AbortError')setError(cause.message)}
  };
  const number=Number(followers);
  return <section className="growth-studio"><h2>Brasil · crescer até 1.000 seguidores</h2>
    <p>Crie um vídeo vertical original com uma foto que você tem direito de usar. Revise o conteúdo e publique no TikTok pela conta autorizada.</p>
    <div className="growth-agent-run">
      <h3>Experimento automático com sinal público do Brasil</h3>
      <p>Busca sinais públicos atuais no Brasil, seleciona um tema, cria cinco cenas gráficas originais com movimento e locução pt-BR quando disponível, e renderiza MP4 9:16 sem foto fornecida por você. Android abre o TikTok para revisão no fim; isso não publica automaticamente. Google Trends não é métrica do TikTok.</p>
      <button type="button" disabled={agentBusy} onClick={()=>{void runAgent()}}>{agentBusy?'Descobrindo, criando e preparando…':Capacitor.getPlatform()!=='web'?'Gerar e enviar ao TikTok para revisão':'Descobrir e produzir vídeo original'}</button>
      {agentResult&&<p>Selecionado: <strong>{agentResult.topic}</strong> · fonte: {agentResult.source} · score de busca: {agentResult.score}. Métricas TikTok: desconhecidas. {agentResult.evidence}</p>}
      {video&&agentResult&&<><video controls playsInline src={video} aria-label="Prévia do vídeo do experimento" />
        <a href={video} download="agent-tiktok-experiment.mp4">Baixar vídeo do experimento</a>
        <button type="button" onClick={()=>{void share()}}>Enviar ao TikTok pelo compartilhamento</button>
        <p>{deliveryMessage||'O TikTok abrirá para revisão. Confirme a publicação no TikTok; o app só registra envio ao compositor até haver prova do post.'}</p></>}
    </div>
    <label>Seguidores atuais (informado por você)
      <input inputMode="numeric" value={followers} onChange={event=>setFollowers(event.target.value.replace(/\D/g,''))} placeholder="Ex.: 120" />
    </label>
    {followers&&<p>Faltam {Math.max(0,1000-number).toLocaleString('pt-BR')} seguidores para o requisito inicial. Isso não confirma aprovação na Shop.</p>}
    <form onSubmit={event=>{void generate(event)}}>
      <label>Foto original do produto ou tema
        <input type="file" accept="image/jpeg,image/png,image/webp" required onChange={event=>setPhoto(event.target.files?.[0]??null)}/>
      </label>
      <label>1 · Chamada inicial<input maxLength={95} required value={headline} onChange={event=>setHeadline(event.target.value)} placeholder="Ex.: Como escolher um acessório útil?" /></label>
      <label>2 · Informação verdadeira<input maxLength={95} required value={message} onChange={event=>setMessage(event.target.value)} placeholder="Ex.: Veja os detalhes e confira antes de comprar." /></label>
      <label>3 · Convite<input maxLength={95} required value={callToAction} onChange={event=>setCallToAction(event.target.value)} placeholder="Ex.: Siga para ver mais comparações honestas." /></label>
      <button disabled={busy||!photo}>{busy?'Produzindo vídeo…':'Produzir vídeo MP4'}</button>
    </form>
    {video&&<><video controls playsInline src={video} aria-label="Prévia do vídeo"/>
      <a href={video} download="agent-tiktok-shop.mp4">Baixar vídeo</a>
      <button type="button" onClick={()=>{void share()}}>Compartilhar vídeo</button></>}
    {error&&<p role="alert" className="connection-warning">{error}</p>}
    <p className="connection-note">Vídeo criado para revisão humana. Este recurso não posta no TikTok, não adiciona produto à Shop e não cria seguidores automaticamente.</p>
  </section>;
}
