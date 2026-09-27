import { useEffect, useState } from 'react';
import { getPortfolio, type Portfolio } from './apiClient';

type Tab='home'|'experiments'|'money';
const gbp=(amount:string|null)=>amount===null?'UNKNOWN':`£${amount}`;

export default function ServerWorkspace(){
  const [tab,setTab]=useState<Tab>('home');
  const [portfolio,setPortfolio]=useState<Portfolio|null>(null);
  const [error,setError]=useState('');
  const refresh=async()=>{
    try{setPortfolio(await getPortfolio());setError('')}
    catch(e){setPortfolio(null);setError(e instanceof Error?e.message:'BACKEND UNAVAILABLE')}
  };
  useEffect(()=>{void refresh();const timer=window.setInterval(()=>{void refresh()},60_000);
    return ()=>window.clearInterval(timer)},[]);
  if(error)return <section className="server-workspace" role="alert"><h2>BACKEND UNAVAILABLE</h2><p>{error}</p>
    <p>Stored browser drafts are not business truth. Money and actions are blocked until the server responds.</p>
    <button onClick={()=>{void refresh()}}>Retry</button></section>;
  if(!portfolio)return <section className="server-workspace"><p>Loading durable business truth…</p></section>;
  const latest=portfolio.experiments.at(-1);
  return <section className="server-workspace"><nav aria-label="Workspace">
    {(['home','experiments','money'] as const).map(item=><button key={item} aria-current={tab===item?'page':undefined}
      onClick={()=>setTab(item)}>{item==='home'?'Home':item==='experiments'?'Experiments':'Money'}</button>)}
  </nav><p className="server-note">POSTGRES OBSERVATIONS · MANUAL ASSERTIONS · NO AUTOMATIC PUBLISHING</p>
    {tab==='home'&&<><h2>What is true?</h2><div className="connection-card"><span>Latest realized contribution</span>
      <strong>{gbp(latest?.realizedContributionGbp??null)}</strong>
      <small>Settled commission net of refunds and observed cost; unknown inputs stay UNKNOWN.</small></div>
      <p>Commercial proof: <b>NOT PROVEN</b></p>
      <p className="connection-warning">Capital, product claims, creative approval and launch authority are not yet governed by this server. New launches are blocked in the mobile workspace.</p></>}
    {tab==='experiments'&&<><h2>Durable experiments</h2>{portfolio.experiments.length===0?<p>No experiment has been recorded in PostgreSQL.</p>:
      portfolio.experiments.map(item=><div className="connection-card" key={item.experimentId}>
        <strong>{item.experimentId}</strong><small>Decision: {item.decisionId} · Product: {item.productId} · Creative: {item.creativeId}</small>
        <span>Publication observed: {item.publicationObserved?'YES · MANUAL ASSERTION':'UNKNOWN'}</span></div>)}
      <p className="server-note">Browser drafts cannot freeze an experiment or authorize publication here.</p></>}
    {tab==='money'&&<><h2>Money path</h2>{portfolio.experiments.length===0?<p>Settlement and cost are UNKNOWN.</p>:
      portfolio.experiments.map(item=><div className="connection-card" key={item.experimentId}>
        <strong>{item.experimentId}</strong><span>Net settled: {gbp(item.netSettledGbp)}</span>
        <span>Observed cost: {gbp(item.observedCostGbp)}</span>
        <span>Realized contribution: {gbp(item.realizedContributionGbp)}</span>
        <small>First £: NOT PROVEN{item.firstPoundCandidate?' · local manual observation candidate':''}</small></div>)}
      <p>Bank arrival: UNKNOWN · Withdrawal: MANUAL</p></>}
  </section>;
}
