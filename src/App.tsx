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
 return <><Header title="UK Setup"/><main><section className="setup-hero"><Settings2/><div><h2>Money-path eligibility</h2><p>Nothing executes externally until the real UK route is verified.</p></div></section>
 {requirements.map(key=>{const state=eligibility[key];return <button className="check-row" key={key} onClick={()=>update(key)}><span className={'check '+(state==='VERIFIED'?'yes':state==='BLOCKED'?'blocked':'')}>{state==='VERIFIED'?<Check/>:<X/>}</span><div><b>{eligibilityLabels[key]}</b><small>{state} · tap to change</small></div></button>})}
 <section className={'eligibility '+tone}><ShieldCheck/><div><small>OVERALL STATUS</small><h2>{overall}</h2></div></section>
 <p className="muted">{overall==='ELIGIBLE'?'Eligibility gate permits external execution; policy and human approval still apply.':'External execution is fail-closed. Research, simulation and creative preparation remain available.'}</p>
 <p className="muted">V0 stores status only. Identity documents and bank credentials stay with TikTok/payment providers.</p></main></>}
export default function App(){const [page,setPage]=useState<Page>('home');let body=page==='home'?<HomePage go={setPage}/>:page==='radar'?<RadarPage go={setPage}/>:page==='opportunity'?<OpportunityPage go={setPage}/>:page==='tests'?<TestsPage/>:page==='money'?<MoneyPage/>:<SetupPage/>;return <div className="app">{body}{page!=='setup'&&page!=='opportunity'&&<Nav page={page} setPage={setPage}/>}<button className="bot" aria-label="Agent assistant"><Bot/></button></div>}
