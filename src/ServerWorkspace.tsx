import { useEffect, useState } from 'react';
import { getCapital, getLearning, getPortfolio, type CapitalState, type LearningState, type Portfolio } from './apiClient';
import OperatorIntake from './OperatorIntake';

type Tab='home'|'experiments'|'money'|'operate';
const gbp=(amount:string|null)=>amount===null?'UNKNOWN':`£${amount}`;

export default function ServerWorkspace(){
  const [tab,setTab]=useState<Tab>('home');
  const [portfolio,setPortfolio]=useState<Portfolio|null>(null);
  const [capital,setCapital]=useState<CapitalState|null>(null);
  const [learning,setLearning]=useState<LearningState|null>(null);
  const [error,setError]=useState('');
  const refresh=async()=>{
    try{const [nextPortfolio,nextCapital,nextLearning]=await Promise.all([getPortfolio(),getCapital(),getLearning()]);
      setPortfolio(nextPortfolio);setCapital(nextCapital);setLearning(nextLearning);setError('')}
    catch(e){setPortfolio(null);setCapital(null);setLearning(null);setError(e instanceof Error?e.message:'BACKEND UNAVAILABLE')}
  };
  useEffect(()=>{void refresh();const timer=window.setInterval(()=>{void refresh()},60_000);
    return ()=>window.clearInterval(timer)},[]);
  if(error)return <section className="server-workspace" role="alert"><h2>BACKEND UNAVAILABLE</h2><p>{error}</p>
    <p>Stored browser drafts are not business truth. Money and actions are blocked until the server responds.</p>
    <button onClick={()=>{void refresh()}}>Retry</button></section>;
  if(!portfolio)return <section className="server-workspace"><p>Loading durable business truth…</p></section>;
  const latest=portfolio.experiments.at(-1);
  return <section className="server-workspace"><nav aria-label="Workspace">
    {(['home','experiments','money','operate'] as const).map(item=><button key={item} aria-current={tab===item?'page':undefined}
      onClick={()=>setTab(item)}>{item==='home'?'Home':item==='experiments'?'Experiments':item==='money'?'Money':'Operate'}</button>)}
  </nav><p className="server-note">POSTGRES OBSERVATIONS · MANUAL ASSERTIONS · NO AUTOMATIC PUBLISHING</p>
    {tab==='home'&&<><h2>What is true?</h2><div className="connection-card"><span>Latest realized contribution</span>
      <strong>{gbp(latest?.realizedContributionGbp??null)}</strong>
      <small>Settled commission net of refunds and observed cost; unknown inputs stay UNKNOWN.</small></div>
      <p>Commercial proof: <b>NOT PROVEN</b></p>
      <p>Capital authority: <b>{capital?.status==='ACTIVE'?`ACTIVE · limit ${gbp(capital.capitalLimitGbp)} · loss ${gbp(capital.lossLimitGbp)}`:'UNKNOWN'}</b></p>
      <p className="connection-warning">Shop, Affiliate and commerce API capabilities remain independently UNKNOWN without provider evidence. Manual records do not prove real TikTok income.</p></>}
    {tab==='experiments'&&<><h2>Durable experiments</h2>{portfolio.experiments.length===0?<p>No experiment has been recorded in PostgreSQL.</p>:
      portfolio.experiments.map(item=><div className="connection-card" key={item.experimentId}>
        <strong>{item.experimentId}</strong><small>Decision: {item.decisionId} · Product: {item.productId} · Creative: {item.creativeId}</small>
        <span>Publication observed: {item.publicationObserved?'YES · MANUAL ASSERTION':'UNKNOWN'}</span></div>)}
      <p className="server-note">Use Operate to record operator observations. Server authority checks each step.</p></>}
    {tab==='money'&&<><h2>Money path</h2>{portfolio.experiments.length===0?<p>Settlement and cost are UNKNOWN.</p>:
      portfolio.experiments.map(item=><div className="connection-card" key={item.experimentId}>
        <strong>{item.experimentId}</strong><span>Net settled: {gbp(item.netSettledGbp)}</span>
        <span>Observed cost: {gbp(item.observedCostGbp)}</span>
        <span>Realized contribution: {gbp(item.realizedContributionGbp)}</span>
        <small>First £: NOT PROVEN{item.firstPoundCandidate?' · local manual observation candidate':''}</small></div>)}
      <p>Bank arrival: UNKNOWN · Withdrawal: MANUAL</p>
      <p>Learning records: {learning?.records.length??0} · Stale: {learning?.records.filter(record=>!record.current).length??0}</p></>}
    {tab==='operate'&&<OperatorIntake onRecorded={()=>{void refresh()}}/>}
  </section>;
}
