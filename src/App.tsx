import { useState } from 'react';
import { Bell, Bot, Check, ChevronRight, CircleDollarSign, FlaskConical, Home, Radar, Settings2, ShieldCheck, Sparkles, TrendingUp, WalletCards, X } from 'lucide-react';
import { defaultEligibility, eligibilityLabels, nextRequirementState, resolveEligibility, type EligibilityRequirement, type EligibilitySnapshot } from './domain/eligibility';

type Page = 'home'|'radar'|'opportunity'|'tests'|'money'|'setup';
const products = [
 {id:1,name:'Viral Beauty Gadget',cat:'Beauty',price:24.99,commission:18,score:86,confidence:74,profit:31.20,trend:'+32%',emoji:'✨'},
 {id:2,name:'Smart LED Lamp',cat:'Home & Living',price:19.99,commission:15,score:81,confidence:68,profit:22.40,trend:'+18%',emoji:'💡'},
 {id:3,name:'Mini Massage Gun',cat:'Fitness',price:34.99,commission:12,score:78,confidence:71,profit:19.80,trend:'+11%',emoji:'⚡'},
];

function Header({title='TikTok Shop UK'}:{title?:string}) {
 return <header><div className="brand"><div className="logo">♪</div><div><b>{title}</b><small>🇬🇧 United Kingdom · GBP</small></div></div><div className="head-actions"><Bell size={19}/><button className="avatar">HN</button></div></header>
}
function Pill({children,tone='blue'}:{children:React.ReactNode,tone?:string}){return <span className={'pill '+tone}>{children}</span>}
function Metric({label,value,sub}:{label:string,value:string,sub?:string}){return <div className="metric"><small>{label}</small><strong>{value}</strong>{sub&&<span>{sub}</span>}</div>}
function Nav({page,setPage}:{page:Page,setPage:(p:Page)=>void}) {
 const items:[Page,React.ReactNode,string][]=[['home',<Home size={20}/>,'Home'],['radar',<Radar size={20}/>,'Radar'],['tests',<FlaskConical size={20}/>,'Tests'],['money',<WalletCards size={20}/>,'Money']];
 return <nav>{items.map(([p,i,l])=><button key={p} className={page===p?'active':''} onClick={()=>setPage(p)}>{i}<span>{l}</span></button>)}</nav>
}
function HomePage({go}:{go:(p:Page)=>void}){
 return <><Header/><main><div className="demo">DEMO DATA · NOT CONNECTED TO TIKTOK YET</div><section className="hero"><div><span>Realized profit</span><h1>£0.00</h1><p>Goal: first settled profitable experiment</p></div><TrendingUp size={42}/></section>
 <div className="grid3"><Metric label="Expected" value="£73.40" sub="3 shortlisted"/><Metric label="Pending" value="£0.00"/><Metric label="Capital at risk" value="£0.00"/></div>
 <div className="section-title"><h2>🔥 Top opportunities</h2><button onClick={()=>go('radar')}>View radar</button></div>
 {products.slice(0,2).map((p,n)=><article className="product" key={p.id} onClick={()=>go('opportunity')}><div className="thumb">{p.emoji}</div><div className="grow"><div className="row"><Pill>#{n+1}</Pill><Pill tone="green">{p.trend}</Pill></div><h3>{p.name}</h3><p>{p.cat} · £{p.price} · {p.commission}% commission</p><div className="score"><b>Score {p.score}</b><span>Confidence {p.confidence}%</span><strong>+£{p.profit.toFixed(2)}</strong></div></div><ChevronRight/></article>)}
 <div className="section-title"><h2>🧪 Active experiments</h2></div><article className="empty"><FlaskConical/><div><b>No live experiment yet</b><p>EXP-001 will appear here after UK eligibility and product selection.</p></div></article>
 <button className="setup-link" onClick={()=>go('setup')}><ShieldCheck/> UK money-path setup <ChevronRight/></button>
 </main></>
}
function RadarPage({go}:{go:(p:Page)=>void}){return <><Header title="UK Product Radar"/><main><div className="demo">DEMO OPPORTUNITIES</div><div className="filters"><button className="selected">Top score</button><button>Commission</button><button>Confidence</button><button>Cash velocity</button></div>{products.map((p,n)=><article className="product radar-card" key={p.id} onClick={()=>go('opportunity')}><div className="thumb">{p.emoji}</div><div className="grow"><div className="row"><Pill>#{n+1}</Pill><Pill tone="green">{p.trend}</Pill></div><h3>{p.name}</h3><p>{p.cat}</p><div className="radar-metrics"><Metric label="Price" value={'£'+p.price}/><Metric label="Commission" value={p.commission+'%'}/><Metric label="Score" value={String(p.score)}/></div><div className="progress"><i style={{width:p.confidence+'%'}}/></div><small>Confidence {p.confidence}% · expected +£{p.profit.toFixed(2)}</small></div></article>)}</main></>}
function OpportunityPage({go}:{go:(p:Page)=>void}){const p=products[0];return <><Header title="Opportunity"/><main><button className="back" onClick={()=>go('radar')}>‹ UK Radar</button><section className="op-head"><div className="thumb big">{p.emoji}</div><div><Pill>Score {p.score}</Pill><h2>{p.name}</h2><p>{p.cat} · UK</p></div></section><div className="grid3"><Metric label="Price" value="£24.99"/><Metric label="Commission" value="18%"/><Metric label="Est./order" value="£4.50"/></div>
 <section className="card"><h3>💷 Economic hypothesis</h3><div className="money-line"><span>Expected realized contribution</span><strong>+£31.20</strong></div><div className="money-line"><span>Confidence</span><b>74%</b></div><div className="money-line"><span>Expected time-to-cash</span><b>~4 days</b></div><div className="money-line"><span>Capital required</span><b>£0–£8</b></div></section>
 <section className="card"><h3>🤖 Opportunity Analyst</h3><p>High demonstrability and meaningful commission create a testable commerce hypothesis. Seller, return rate and current supply still require direct evidence before execution.</p><div className="tags"><Pill tone="green">Demo-friendly</Pill><Pill tone="yellow">Supply unknown</Pill><Pill tone="yellow">Returns unknown</Pill></div></section>
 <button className="primary" onClick={()=>go('tests')}><FlaskConical/> Create EXP-001</button></main></>}
function TestsPage(){return <><Header title="Experiments"/><main><div className="demo">SAFE MODE · EXTERNAL EXECUTION OFF</div><section className="card experiment"><div className="row"><Pill>EXP-001</Pill><Pill tone="yellow">DRAFT</Pill></div><h2>Demo-first creative test</h2><p>Hypothesis: showing the product result in the first 2 seconds will create stronger commerce intent than a problem-first opening.</p><div className="steps"><div className="done"><Check/>Opportunity selected</div><div className="done"><Check/>Economics calculated</div><div><Sparkles/>Creative strategy pending</div><div><ShieldCheck/>Human approval required</div></div><div className="limit"><Metric label="Capital limit" value="£8.00"/><Metric label="Loss limit" value="£8.00"/></div><button className="primary"><Sparkles/> Generate creative strategy</button></section></main></>}
function MoneyPage(){return <><Header title="Money"/><main><div className="demo">DEMO LEDGER · WITHDRAWAL REMAINS MANUAL</div><section className="hero money"><div><span>Realized contribution</span><h1>£0.00</h1><p>Settled commission − experiment costs</p></div><CircleDollarSign size={42}/></section><div className="grid3"><Metric label="Expected" value="£0.00"/><Metric label="Pending" value="£0.00"/><Metric label="Settled" value="£0.00"/></div><section className="card"><h3>Decision → Money trace</h3><div className="timeline"><b>Experiment</b><i/><b>Order</b><i/><b>Delivery</b><i/><b>Settlement</b><i/><b>Profit</b></div><p className="muted">No economic event recorded yet. Orders will never be counted as realized profit before settlement.</p></section><section className="card"><h3>Available for withdrawal</h3><div className="withdraw"><strong>£0.00</strong><Pill tone="blue">MANUAL</Pill></div><p>The agent never withdraws, transfers or changes payout destinations in V0.</p></section></main></>}
function SetupPage(){
 const [eligibility,setEligibility]=useState<EligibilitySnapshot>(defaultEligibility);
 const requirements=Object.keys(eligibilityLabels) as EligibilityRequirement[];
 const overall=resolveEligibility(eligibility);
 const tone=overall==='ELIGIBLE'?'green':overall==='BLOCKED'?'blocked':'yellow';
 const update=(key:EligibilityRequirement)=>setEligibility(current=>({...current,[key]:nextRequirementState(current[key])}));
 const unresolved=requirements.filter(key=>eligibility[key]!=='VERIFIED');
 const next=unresolved[0];
 const verified=requirements.length-unresolved.length;
 return <><Header title="UK Reality Check"/><main>
  <section className="setup-hero"><Settings2/><div><h2>EXP-001 launch checklist</h2><p>Verify reality from your phone. No document, password or bank credential is stored here.</p></div></section>
  <section className="card readiness-card"><div className="readiness-top"><div><small>VERIFIED REALITY</small><h2>{verified}/{requirements.length}</h2></div><Pill tone={overall==='ELIGIBLE'?'green':overall==='BLOCKED'?'blocked':'yellow'}>{overall}</Pill></div><div className="progress"><i style={{width:`${Math.round((verified/requirements.length)*100)}%`}}/></div></section>
  {next&&overall!=='BLOCKED'&&<section className="next-proof"><small>NEXT PROOF</small><h3>{eligibilityLabels[next]}</h3><p>Check this directly in the relevant TikTok/account screen, then record only the status and a safe reference.</p><button className="primary" onClick={()=>update(next)}><ShieldCheck/> Record verification state</button></section>}
  {requirements.map((key,index)=>{const state=eligibility[key];return <button className={'check-row '+(key===next?'current':'')} key={key} onClick={()=>update(key)}><span className={'step-no '+(state==='VERIFIED'?'done':state==='BLOCKED'?'blocked':'')}>{state==='VERIFIED'?<Check/>:index+1}</span><div className="grow"><b>{eligibilityLabels[key]}</b><small>{state==='UNKNOWN'?'Evidence required':state==='VERIFIED'?'Evidence recorded':'Resolve blocker before launch'}</small></div><Pill tone={state==='VERIFIED'?'green':state==='BLOCKED'?'blocked':'yellow'}>{state}</Pill></button>})}
  <section className={'eligibility '+tone}><ShieldCheck/><div><small>LAUNCH GATE</small><h2>{overall==='ELIGIBLE'?'READY FOR POLICY CHECK':overall}</h2></div></section>
  <p className="muted">{overall==='ELIGIBLE'?'Reality prerequisites are verified. Policy, human approval and the execution kill switch still control publication.':'EXP-001 remains fail-closed. Resolve the highlighted evidence path before external execution.'}</p>
  <p className="muted">Tap states only after checking reality. V0 stores status/reference only; identity documents, payout credentials and secrets remain outside the agent.</p>
 </main></>
}
export default function App(){const [page,setPage]=useState<Page>('home');let body=page==='home'?<HomePage go={setPage}/>:page==='radar'?<RadarPage go={setPage}/>:page==='opportunity'?<OpportunityPage go={setPage}/>:page==='tests'?<TestsPage/>:page==='money'?<MoneyPage/>:<SetupPage/>;return <div className="app">{body}{page!=='setup'&&page!=='opportunity'&&<Nav page={page} setPage={setPage}/>}<button className="bot" aria-label="Agent assistant"><Bot/></button></div>}
