import { useEffect, useState, type FormEvent } from 'react';
import { operatorCsrf } from './apiClient';

export default function GrowthStudio() {
  const [photo,setPhoto]=useState<File|null>(null);
  const [headline,setHeadline]=useState('');
  const [message,setMessage]=useState('');
  const [callToAction,setCallToAction]=useState('');
  const [video,setVideo]=useState('');
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [followers,setFollowers]=useState('');
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
  const share=async()=>{
    if(!video)return;
    try {
      const clip=await (await fetch(video)).blob();
      const file=new File([clip],'agent-tiktok-shop.mp4',{type:'video/mp4'});
      if(!navigator.canShare?.({files:[file]}))throw new Error('Compartilhamento de vídeo indisponível neste celular; tente Baixar vídeo');
      await navigator.share({files:[file],title:'Vídeo original'});
    }catch(cause){if(cause instanceof Error && cause.name!=='AbortError')setError(cause.message)}
  };
  const number=Number(followers);
  return <section className="growth-studio"><h2>Brasil · crescer até 1.000 seguidores</h2>
    <p>Crie um vídeo vertical original com uma foto que você tem direito de usar. Revise o conteúdo e publique no TikTok pela conta autorizada.</p>
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
