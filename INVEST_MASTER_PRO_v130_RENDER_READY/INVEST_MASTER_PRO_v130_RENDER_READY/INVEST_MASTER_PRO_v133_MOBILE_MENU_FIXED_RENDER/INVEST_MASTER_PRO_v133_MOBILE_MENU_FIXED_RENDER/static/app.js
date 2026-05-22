
let candidates=[],holdings=[],watchlist=[],market={},selectedCode='3350',currentPage='dashboard';
const EMOJIS=[['🔥','高優先度','今もっとも見るべき銘柄'],['🏆','勝ちパターン一致','自分の得意形に近い'],['⚠️','リスク注意','買う前に危険確認'],['🚫','触るな','条件不足・感情買い禁止'],['🚀','急騰候補','出来高/材料で動きやすい'],['💰','資金流入','テーマや需給が強い'],['🧠','AI高評価','AI総合点が高い'],['👀','監視推奨','今すぐ買わず監視'],['📈','上昇','SBI式でプラスは赤表示'],['📉','下落警戒','SBI式でマイナスは緑表示'],['⚡','IR材料強','増配/上方修正/自社株買い'],['🧊','出来高不足','動きが弱い・様子見']];
const fmtYen=v=>v==null||isNaN(v)?'—':Math.round(v).toLocaleString()+'円';
const fmtPct=v=>v==null||isNaN(v)?'—':(v>=0?'+':'')+Number(v).toFixed(2)+'%';
const upDown=v=>v==null?'neutral':v>=0?'up':'down';
async function api(url,opt){let r=await fetch(url,opt);if(!r.ok)throw new Error(url+' '+r.status);return await r.json()}
function showPage(name,btn){document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));document.getElementById(name+'Page').classList.add('active');document.querySelectorAll('.nav button,.mobileNav button').forEach(b=>b.classList.remove('active'));if(btn)btn.classList.add('active');currentPage=name;if(name==='chart')setTimeout(()=>loadChart(selectedCode),80);if(name==='market')loadMarket();if(name==='screener'&&!document.getElementById('screenTable').innerHTML)runScreener();if(name==='report'&&!document.getElementById('irBox').innerHTML)loadIR('3350');if(name==='trades')loadTrades();if(name==='alerts')loadAlerts()}
function showPageByName(n){const label=n==='dashboard'?'ホーム':n==='ai'?'AI候補':n==='market'?'市場':n==='screener'?'スクリーナー':n==='chart'?'チャート':n==='report'?'IR':n==='holdings'?'保有':n==='watch'?'監視':n==='trades'?'取引':'アラート';showPage(n,[...document.querySelectorAll('.nav button')].find(b=>b.textContent.includes(label)));}
function iconsFor(x){let icons=[];let score=x.ai_score||0,mat=x.catalyst_score||0,st=x.strategy||{};if(score>=90||mat>=42)icons.push('🔥');if(patternMatch(x)>=70)icons.push('🏆');if(mat>=35)icons.push('⚡');if((st.volume_ratio||0)>=2)icons.push('🚀');if(score>=80)icons.push('🧠');if(isRisk(x))icons.push('⚠️');if((st.volume_ratio||0)<1.05)icons.push('🧊');if(!icons.length)icons.push('👀');return icons.join('')}
function patternMatch(x){let p=0;if((x.ai_score||0)>=70)p+=20;if((x.catalyst_score||0)>=20)p+=20;if(((x.strategy||{}).volume_ratio||0)>=1.5)p+=15;if(['上抜け監視','反発狙い'].includes((x.strategy||{}).status))p+=20;if((x.roe||0)>=20)p+=10;if((x.per||99)<=15)p+=10;if((x.pbr||99)<=1.5)p+=5;return Math.min(100,p)}
function isRisk(x){let st=x.strategy||{};return (x.change_pct||0)<-2 || (x.ai_score||0)<55 || st.status==='過熱注意' || (x.catalyst_score||0)<8}
function nameCell(x){return `<b>${iconsFor(x)} ${x.code}</b><br>${x.name}<br><span class="smallTxt">${x.theme||''}</span>`}
function scoreBlock(x){let bd=x.score_breakdown||{};return `<div class="scoreRows"><div class="scoreRow"><span>AI総合</span><span class="sep"></span><b class="mainScore">${x.ai_score??'—'}</b></div><div class="scoreRow"><span>材料</span><span class="sep"></span><b>${x.catalyst_score??0}</b></div><div class="scoreRow"><span>テク</span><span class="sep"></span><b>${bd.technical_score??'—'}</b></div><div class="scoreRow"><span>決算</span><span class="sep"></span><b>${x.earnings_score??0}</b></div><div class="scoreRow"><span>世界情勢</span><span class="sep"></span><b>${x.macro_score??0}</b></div><div class="scoreRow"><span>需給</span><span class="sep"></span><b>${Math.round(((x.strategy||{}).volume_ratio||1)*10)}</b></div></div>`}
function table(arr,type='ai',limit=null){let a=limit?arr.slice(0,limit):arr;return `<table><thead><tr><th>銘柄</th><th>現在値</th><th>前日比</th><th>スコア</th><th>一致率</th><th>判定</th><th>材料理由</th><th></th></tr></thead><tbody>`+a.map(x=>`<tr class="clickable" onclick="openDetail('${x.code}')"><td>${nameCell(x)}</td><td>${fmtYen(x.price)}</td><td class="${upDown(x.change_pct)}">${fmtPct(x.change_pct)}</td><td>${scoreBlock(x)}</td><td><b class="${patternMatch(x)>=70?'up':'neutral'}">${patternMatch(x)}%</b></td><td><span class="badge ${isRisk(x)?'warn':'ok'}">${(x.strategy||{}).status||'—'}</span></td><td>${x.catalyst_reason||x.ai_reason||'—'}</td><td><button class="btn blue" onclick="event.stopPropagation();selectedCode='${x.code}';showPageByName('chart')">チャート</button></td></tr>`).join('')+'</tbody></table>'}
async function checkLogin(){try{let me=await api('/api/me');if(me.logged_in){authScreen.style.display='none';userPill.textContent=me.user.username;await init(true)}else authScreen.style.display='grid'}catch(e){authScreen.style.display='grid'}}
async function submitLogin(){authMsg.textContent='';try{let r=await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:authUser.value,password:authPass.value})});if(!r.ok){authMsg.textContent=r.error||'ログイン失敗';return}authScreen.style.display='none';userPill.textContent=r.user.username;await init(true)}catch(e){authMsg.textContent='ログイン失敗: '+e.message}}
async function submitRegister(){authMsg.textContent='';try{let r=await api('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:authUser.value,password:authPass.value})});if(!r.ok){authMsg.textContent=r.error||'登録失敗';return}authScreen.style.display='none';await init(true)}catch(e){authMsg.textContent='登録失敗'}}
async function logout(){await api('/api/logout',{method:'POST'});location.reload()}
async function init(force=false){todayText.textContent=new Date().toLocaleString('ja-JP');await Promise.all([loadCandidates(force),loadHoldings(force),loadWatch(force),loadMarket(force)]);renderHome();renderLegend();sideTime.textContent=new Date().toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})}
async function refreshAll(){await api('/api/refresh',{method:'POST'});await init(true)}
async function loadCandidates(force=false){candidates=await api('/api/candidates?limit=60&mode='+(document.getElementById('aiMode')?.value||'total')+(force?'&force=1':''));aiTable.innerHTML=table(candidates)}
async function loadHoldings(force=false){holdings=await api('/api/holdings'+(force?'?force=1':''));holdTable.innerHTML=table(holdings,'hold')}
async function loadWatch(force=false){watchlist=await api('/api/watchlist'+(force?'?force=1':''));watchTable.innerHTML=table(watchlist,'watch')}
function renderHome(){let pattern=candidates.filter(x=>patternMatch(x)>=70),risk=candidates.filter(isRisk),hot=candidates.filter(x=>(x.ai_score||0)>=90||(x.catalyst_score||0)>=42);patternCount.textContent=pattern.length;riskCount.textContent=risk.length;hotCount.textContent=hot.length;homeHotTable.innerHTML=table(hot.length?hot:candidates,'ai',6);homeRisk.innerHTML=risk.slice(0,5).map(x=>`<div class="priorityRow"><span>⚠️</span><div><b>${x.code} ${x.name}</b><br><span class="smallTxt">${riskReason(x)}</span></div><button class="btn" onclick="openDetail('${x.code}')">詳細</button></div>`).join('')||'<div class="smallTxt">大きなリスク注意は少なめ。</div>';if(market.sectors){flowTheme.textContent=market.sectors[0]?.name||'—';homeSector.innerHTML=sectorHTML(market.sectors.slice(0,5))}}
function riskReason(x){let r=[];if((x.change_pct||0)<-2)r.push('下落率大');if((x.ai_score||0)<55)r.push('AI点不足');if((x.catalyst_score||0)<8)r.push('材料不足');if((x.strategy||{}).status==='過熱注意')r.push('過熱');return r.join(' / ')||'条件確認'}
function showPatternList(){let arr=candidates.filter(x=>patternMatch(x)>=70);modalTitle.textContent='🏆 勝ちパターン一致銘柄 '+arr.length+'件';modalBody.innerHTML=table(arr);listModal.classList.add('active')}
function showRiskList(){let arr=candidates.filter(isRisk);modalTitle.textContent='⚠️ リスク注意銘柄 '+arr.length+'件';modalBody.innerHTML=table(arr);listModal.classList.add('active')}
function closeModal(){listModal.classList.remove('active')}
function renderLegend(){let h=EMOJIS.map(e=>`<div class="legendItem"><b>${e[0]} ${e[1]}</b><br><span class="smallTxt">${e[2]}</span></div>`).join('');miniLegend.innerHTML=h;legendFull.innerHTML=h}function openLegend(){legendModal.classList.add('active')}function closeLegend(){legendModal.classList.remove('active')}
async function runScreener(){
  screenStatus.innerHTML='検索中...';
  let q=`/api/screener?limit=80&min_score=${encodeURIComponent(scMinScore.value||0)}&min_material=${encodeURIComponent(scMaterial.value||0)}&theme=${encodeURIComponent(scTheme.value||'')}`;
  if(scStatus.value==='breakout')q+='&breakout=1';
  if(scStatus.value==='oversold')q+='&oversold=1';
  let r=await api(q);
  let items=Array.isArray(r.items)?r.items:[];
  if(!items.length && (r.count||0)>0){let c=await api('/api/candidates?limit=80&mode=total');items=c||[];}
  screenStatus.innerHTML=`<b>${r.count??items.length}件ヒット</b> / ${r.scanned??items.length}銘柄スキャン / 更新 ${r.updated_at||'--:--'}`;
  screenTable.innerHTML=items.length?table(items):`<div class="panelBody">条件が厳しすぎます。AI点・材料点を下げるか、上抜け/反発条件を外してください。</div>`;
}
async function loadIR(code){
  let c=code||irCode.value||selectedCode||'3350';
  irCode.value=c;
  irBox.innerHTML='<div class="smallTxt">IR情報を検索中...</div>';
  let r=await api('/api/report?code='+encodeURIComponent(c));
  let rep=(r.reports||[])[0];
  if(!rep){irBox.innerHTML='<div class="panelBody">取得できませんでした。コードを確認してください。</div>';return}
  let discs=rep.disclosures||[];
  let peerRows=(rep.peers||[]).map(p=>`<tr><td>${p.name}</td><td>${p.per??'—'}</td><td>${p.pbr??'—'}</td><td>${p.roe??'—'}</td><td>${p.note||''}</td></tr>`).join('');
  irBox.innerHTML=`<div class="grid2">
    <div class="panel"><div class="panelHead"><h2>${rep.name}（${rep.code}）企業分析</h2><span class="badge ${rep.action&&rep.action.includes('注意')?'warn':'hot'}">${rep.action||'AI判定'}</span></div>
      <div class="panelBody reason">
        <h3>主な事業内容</h3><p>${rep.business||rep.summary||'—'}</p>
        <h3>競争優位</h3>${(rep.competitive_edge||[]).map(x=>'・'+x).join('<br>')||'—'}
        <h3>主要販売先</h3>${(rep.customers||[]).map(x=>'・'+x).join('<br>')||'—'}
        <h3>主要仕入れ先</h3>${(rep.suppliers||[]).map(x=>'・'+x).join('<br>')||'—'}
        <h3>大株主</h3>${(rep.shareholders||[]).map(x=>'・'+x).join('<br>')||'—'}
        <h3>弱気/危険IR</h3>${(rep.bear_points||rep.ir_risks||[]).map(x=>'・'+x).join('<br>')||'—'}
      </div>
    </div>
    <div class="panel"><div class="panelHead"><h2>IRリンク</h2><span class="smallTxt">コード検索対応</span></div>
      <div class="panelBody priorityList">
        ${discs.map(d=>`<div class="priorityRow"><span>${d.type?.includes('有価')?'📘':d.type?.includes('決算')?'📄':'⚡'}</span><div><b>${d.type}</b><br>${d.title}<br><span class="smallTxt">${d.summary||''}</span></div><button class="btn blue" onclick="window.open('${d.url}','_blank')">開く</button></div>`).join('')||'<div class="smallTxt">IRリンクが未登録です。</div>'}
        <button class="btn blue" onclick="window.open('https://www.google.com/search?q=${encodeURIComponent((rep.code||'')+' '+(rep.name||'')+' 決算短信 有価証券報告書 適時開示')}','_blank')">GoogleでIR検索</button>
      </div>
    </div>
  </div>
  <div class="panel" style="margin-top:14px"><div class="panelHead"><h2>同業比較</h2></div><div class="tableWrap"><table><thead><tr><th>銘柄</th><th>PER</th><th>PBR</th><th>ROE</th><th>メモ</th></tr></thead><tbody>${peerRows}</tbody></table></div></div>`;
}
async function loadMarket(force=false){market=await api('/api/market-terminal'+(force?'?force=1':''));topRegime.textContent=market.market_regime||'中立';let k=(market.kpis||[]).map(x=>`<div class="card"><h3>${x.label}</h3><div class="big ${x.color==='green'?'up':x.color==='red'?'down':'warn'}" style="font-size:27px">${x.value}</div><p class="smallTxt">${x.note||''}</p></div>`).join('');marketBox.innerHTML=`<div class="cards4">${k}</div><div class="grid2"><div class="panel"><div class="panelHead"><h2>セクター強弱</h2><span>${market.scanned}銘柄</span></div><div class="panelBody">${sectorHTML(market.sectors||[])}</div></div><div class="panel"><div class="panelHead"><h2>AIコメント</h2></div><div class="panelBody reason">${(market.comments||[]).map(c=>`<b>${c.title}</b><br>${c.text}`).join('<hr style="border-color:#1d324a">')}</div></div></div><div class="grid2"><div class="panel"><div class="panelHead"><h2>💰 資金流入ランキング</h2></div><div class="tableWrap">${table(market.money_flow||[],'ai',10)}</div></div><div class="panel"><div class="panelHead"><h2>🚀 出来高急増</h2></div><div class="tableWrap">${table(market.volume_spike||[],'ai',10)}</div></div></div><div class="panel" style="margin-top:14px"><div class="panelHead"><h2>マクロ監視</h2></div><div class="panelBody heat">${(market.macro||[]).map(m=>`<div><b>${m.name}</b><br><span class="${m.impact==='強気'?'up':m.impact==='弱気'?'down':'neutral'}">${m.impact}</span><br><small>${m.note}</small></div>`).join('')}</div></div>`;renderHome()}
function sectorHTML(rows){return `<div class="sectorDense">`+(rows||[]).map((s,i)=>`<div class="sectorCard"><div class="iconLine"><b style="color:var(--yellow)">${i+1}</b><b>${s.name}</b><span class="${upDown(s.change)}">${fmtPct(s.change)}</span></div><div class="scoreRows"><div class="scoreRow"><span>資金流入</span><span class="sep"></span><b class="${s.flow>=60?'metricGood':s.flow<40?'metricBad':''}">${s.flow}</b></div><div class="scoreRow"><span>順位</span><span class="sep"></span><b>${i+1}位</b></div><div class="scoreRow"><span>判定</span><span class="sep"></span><b class="${s.flow>=60?'metricGood':s.flow<40?'metricBad':'warn'}">${s.flow>=60?'強い':s.flow>=40?'普通':'弱い'}</b></div></div><div class="smallTxt">主導テーマ：${s.reason||'通常'}<br>AIコメント：${s.flow>=60?'資金流入を優先監視':s.flow<40?'今は優先度低め':'中立監視'}</div></div>`).join('')+`</div>`}
async function openDetail(code){selectedCode=code;chartCode.value=code;showPageByName('chart')}
let chartTf={range:'6mo',interval:'1d',label:'日足'};
let chartTech={vwap:true,bb:false,rsi:true,macd:false};
let chartView={start:0,end:90,cross:null};
let currentChartData=null;
function setTimeframe(btn){
  document.querySelectorAll('.tfBtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  chartTf={range:btn.dataset.range,interval:btn.dataset.interval,label:btn.textContent.trim()};
  chartView={start:0,end:90,cross:null};
  loadChart(selectedCode);
}
function toggleTech(btn){const k=btn.dataset.tech;chartTech[k]=!chartTech[k];btn.classList.toggle('active',!!chartTech[k]);if(currentChartData)drawChart(document.getElementById('chartCanvas'),currentChartData)}
function priceColorByChange(chg){return (chg||0)>=0?'up':'down'}
function chartVisibleSize(){
  if(chartTf.interval==='5m')return 70;
  if(chartTf.interval==='15m')return 80;
  if(chartTf.interval==='30m')return 90;
  if(chartTf.interval==='60m')return 100;
  if(chartTf.interval==='1wk')return 120;
  if(chartTf.interval==='1mo')return 140;
  return 90;
}
async function loadChart(code){
  selectedCode=code||selectedCode;chartCode.value=selectedCode;
  let ch=await api('/api/chart/'+selectedCode+`?range=${chartTf.range}&interval=${chartTf.interval}&force=1`);
  currentChartData=ch;
  const n=(ch.data||[]).length, visible=Math.min(chartVisibleSize(),n);
  chartView.start=Math.max(0,n-visible); chartView.end=n; chartView.cross=null;
  chartTitle.textContent=`${ch.name} ${ch.code}`;
  chartInfo.textContent=`${chartTf.label} / ${ch.source} / 時間足は上のボタンでのみ変更 / 上昇=赤・下落=緑`;
  drawChart(document.getElementById('chartCanvas'),ch);
  let s=ch.strategy||{};let last=(ch.data||[]).slice(-1)[0]||{};let prev=(ch.data||[]).slice(-2,-1)[0]||last;
  let chg=(last.close||0)-(prev.close||last.open||last.close||0);let pct=(prev.close?chg/prev.close*100:0);
  if(document.getElementById('chartTopInfo')) chartTopInfo.innerHTML=`
    <div class="infoBox"><small>現在値</small><b class="${priceColorByChange(chg)}">${fmtYen(last.close)}</b></div>
    <div class="infoBox"><small>前本比</small><b class="${priceColorByChange(chg)}">${fmtYen(chg)} / ${fmtPct(pct)}</b></div>
    <div class="infoBox"><small>高値</small><b>${fmtYen(last.high)}</b></div>
    <div class="infoBox"><small>安値</small><b>${fmtYen(last.low)}</b></div>
    <div class="infoBox"><small>出来高</small><b>${(last.volume||0).toLocaleString()}</b></div>`;
  chartLevels.innerHTML=`<div class="level"><small>現在値</small><b class="${priceColorByChange(chg)}">${fmtYen(last.close)}</b></div><div class="level"><small>買いゾーン</small><b>${s.buy_zone||'—'}</b></div><div class="level"><small>利確</small><b class="up">${s.take_profit_1||'—'} / ${s.take_profit_2||'—'}</b></div><div class="level"><small>損切</small><b class="down">${s.loss_cut||'—'}</b></div>`;
  let rsi=s.rsi14??last.rsi14, vol=s.volume_ratio;
  chartAiNote.innerHTML=`<b class="up">🔥 ${s.status||'様子見'}</b><br>・現在値 ${fmtYen(last.close)} / 出来高 ${vol||'—'}倍<br>・支持線 ${s.support||'—'} / 抵抗線 ${s.resistance||'—'}<br>・RSI ${rsi||'—'} ${rsi>70?'<span class="warn">過熱注意</span>':rsi<35?'<span class="up">反発候補</span>':'中立'}<br><hr style="border-color:#1d324a"><b>見るポイント</b><br>① 価格軸は右側<br>② 時間足は上のボタンで固定<br>③ 現在値ラインと支持/抵抗だけ見る`;
}
function drawChart(canvas,ch){
  if(!canvas||!ch?.data?.length)return;
  const wrap=canvas.parentElement;
  const W=Math.floor(wrap.clientWidth), H=Math.floor(wrap.clientHeight);
  if(W<120||H<260){setTimeout(()=>drawChart(canvas,ch),120);return;}
  const ctx=canvas.getContext('2d'), dpr=Math.max(1,window.devicePixelRatio||1);
  const needW=Math.floor(W*dpr), needH=Math.floor(H*dpr);
  if(canvas.width!==needW) canvas.width=needW;
  if(canvas.height!==needH) canvas.height=needH;
  canvas.style.width='100%'; canvas.style.height='100%';
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.imageSmoothingEnabled=true;ctx.clearRect(0,0,W,H);ctx.fillStyle='#03070d';ctx.fillRect(0,0,W,H);
  const all=(ch.data||[]).filter(x=>x.close!=null);if(all.length<2)return;
  if(chartView.end>all.length||chartView.end<=chartView.start){const v=Math.min(chartVisibleSize(),all.length);chartView.end=all.length;chartView.start=Math.max(0,all.length-v)}
  let data=all.slice(chartView.start,chartView.end); if(data.length<10)data=all.slice(-Math.min(90,all.length));
  const lowerMode=chartTech.macd?'macd':chartTech.rsi?'rsi':'volume';
  const pad={l:46,r:104,t:30,b:42}; const lowerH=lowerMode==='volume'?86:100; const gap=16;
  const plotH=H-pad.t-pad.b-lowerH-gap, plotW=W-pad.l-pad.r, lowerY=pad.t+plotH+gap;
  const vals=[]; data.forEach(x=>['high','low','sma25','sma75'].forEach(k=>{if(x[k]!=null)vals.push(+x[k])}));
  if(chartTech.vwap)data.forEach(x=>{if(x.vwap!=null)vals.push(+x.vwap)}); if(chartTech.bb)data.forEach(x=>['bb_upper','bb_lower'].forEach(k=>{if(x[k]!=null)vals.push(+x[k])}));
  let min=Math.min(...vals), max=Math.max(...vals); if(!isFinite(min)||!isFinite(max)||min===max){min=0;max=1} const span=max-min; min-=span*.08; max+=span*.08;
  const xAt=i=>pad.l+i*(plotW/Math.max(1,data.length-1)); const yAt=v=>pad.t+(max-v)/(max-min)*plotH;
  function px(v){return Math.round(v).toLocaleString()}
  ctx.strokeStyle='#15263a';ctx.lineWidth=1;ctx.fillStyle='#b9c9db';ctx.font='12px system-ui,sans-serif';ctx.textBaseline='middle';
  for(let i=0;i<7;i++){let y=pad.t+i*plotH/6;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();let val=max-(max-min)*i/6;ctx.fillStyle='#b9c9db';ctx.fillText(px(val),W-pad.r+10,y)}
  ctx.strokeStyle='#243a55';ctx.beginPath();ctx.moveTo(pad.l,pad.t);ctx.lineTo(pad.l,pad.t+plotH);ctx.lineTo(W-pad.r,pad.t+plotH);ctx.lineTo(W-pad.r,pad.t);ctx.stroke();
  function line(k,c,w=2,dash=[]){ctx.strokeStyle=c;ctx.lineWidth=w;ctx.setLineDash(dash);ctx.beginPath();let st=false;data.forEach((x,i)=>{if(x[k]==null)return;let xx=xAt(i),yy=yAt(+x[k]);if(!st){ctx.moveTo(xx,yy);st=true}else ctx.lineTo(xx,yy)});ctx.stroke();ctx.setLineDash([])}
  if(chartTech.bb){line('bb_upper','#61748d',1,[5,5]);line('bb_lower','#61748d',1,[5,5])}
  line('sma25','#ffd333',2.0); line('sma75','#8ab4ff',1.7); if(chartTech.vwap)line('vwap','#ffffff',1.2,[5,4]);
  const cw=Math.max(4,Math.min(15,plotW/data.length*.58));
  data.forEach((x,i)=>{let xx=xAt(i),o=yAt(+(x.open||x.close)),c=yAt(+x.close),h=yAt(+(x.high||x.close)),l=yAt(+(x.low||x.close));let isUp=+x.close>=+(x.open||x.close);ctx.strokeStyle=ctx.fillStyle=isUp?'#ff4d4d':'#2fd36b';ctx.lineWidth=1.35;ctx.beginPath();ctx.moveTo(xx,h);ctx.lineTo(xx,l);ctx.stroke();ctx.fillRect(Math.round(xx-cw/2)+.5,Math.min(o,c),Math.max(2,cw),Math.max(2,Math.abs(c-o)))});
  const st=ch.strategy||{}; [['支持',st.support,'#2fd36b'],['抵抗',st.resistance,'#ff4d4d']].forEach(([lab,val,col])=>{if(val==null||!isFinite(+val))return;let y=yAt(+val);if(y<pad.t||y>pad.t+plotH)return;ctx.strokeStyle=col;ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=col;ctx.font='bold 12px system-ui';ctx.textBaseline='bottom';ctx.fillText(lab+' '+px(+val),W-pad.r-88,y-4)});
  const last=data[data.length-1], prev=data.length>1?data[data.length-2]:last; const currentY=yAt(+last.close); const chg=(+last.close)-+(prev.close||last.open||last.close); const curCol=chg>=0?'#ff4d4d':'#2fd36b';
  ctx.strokeStyle=curCol;ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(pad.l,currentY);ctx.lineTo(W-pad.r,currentY);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle=curCol;ctx.fillRect(W-pad.r+5,currentY-14,88,28);ctx.fillStyle='#fff';ctx.font='bold 12px system-ui';ctx.textBaseline='middle';ctx.fillText(px(+last.close),W-pad.r+13,currentY);
  const hi=Math.max(...data.map(x=>+x.high||+x.close)), lo=Math.min(...data.map(x=>+x.low||+x.close)); const hiIdx=data.findIndex(x=>+x.high===hi), loIdx=data.findIndex(x=>+x.low===lo);
  ctx.font='bold 11px system-ui';ctx.fillStyle='#ffcf66';ctx.fillText('高値 '+px(hi),Math.min(W-pad.r-90,xAt(hiIdx)+6),Math.max(pad.t+12,yAt(hi)-10));ctx.fillStyle='#7ee787';ctx.fillText('安値 '+px(lo),Math.min(W-pad.r-90,xAt(loIdx)+6),Math.min(pad.t+plotH-4,yAt(lo)+14));
  ctx.strokeStyle='#15263a';ctx.beginPath();ctx.moveTo(pad.l,lowerY);ctx.lineTo(W-pad.r,lowerY);ctx.stroke();
  if(lowerMode==='volume'){
    const vmax=Math.max(...data.map(x=>+x.volume||0),1);ctx.fillStyle='#a9bad0';ctx.font='12px system-ui';ctx.fillText('出来高',pad.l,lowerY+10);
    data.forEach((x,i)=>{let bar=(+x.volume||0)/vmax*(lowerH-24);let up=+x.close>=+(x.open||x.close);ctx.fillStyle=up?'rgba(255,77,77,.62)':'rgba(47,211,107,.62)';ctx.fillRect(xAt(i)-cw/2,lowerY+lowerH-bar,cw,bar)});
  } else if(lowerMode==='rsi'){
    ctx.fillStyle='#a9bad0';ctx.font='12px system-ui';ctx.fillText('RSI',pad.l,lowerY+10); const rY=v=>lowerY+14+(100-v)/100*(lowerH-24);
    [30,70].forEach(v=>{ctx.strokeStyle=v===70?'#ff4d4d':'#2fd36b';ctx.setLineDash([4,5]);ctx.beginPath();ctx.moveTo(pad.l,rY(v));ctx.lineTo(W-pad.r,rY(v));ctx.stroke();ctx.setLineDash([])});
    ctx.strokeStyle='#ffd333';ctx.lineWidth=1.8;ctx.beginPath();let started=false;data.forEach((x,i)=>{if(x.rsi14==null)return;let xx=xAt(i),yy=rY(+x.rsi14);if(!started){ctx.moveTo(xx,yy);started=true}else ctx.lineTo(xx,yy)});ctx.stroke();
  } else if(lowerMode==='macd'){
    ctx.fillStyle='#a9bad0';ctx.font='12px system-ui';ctx.fillText('MACD',pad.l,lowerY+10); let ms=[];data.forEach(x=>{if(x.macd!=null)ms.push(+x.macd); if(x.macd_signal!=null)ms.push(+x.macd_signal)});let mn=Math.min(...ms),mx=Math.max(...ms); if(!isFinite(mn)||mn===mx){mn=-1;mx=1}; const mY=v=>lowerY+14+(mx-v)/(mx-mn)*(lowerH-24); function mline(k,c){ctx.strokeStyle=c;ctx.lineWidth=1.7;ctx.beginPath();let st=false;data.forEach((x,i)=>{if(x[k]==null)return;let xx=xAt(i),yy=mY(+x[k]);if(!st){ctx.moveTo(xx,yy);st=true}else ctx.lineTo(xx,yy)});ctx.stroke()} mline('macd','#ffd333');mline('macd_signal','#8ab4ff');
  }
  // カーソル情報はDOMオーバーレイで表示。mousemoveでCanvas全体を再描画しない。
  canvas._chartHover={data,pad,W,H,plotW,lowerY,lowerH};
  ctx.fillStyle='#8194ad';ctx.font='12px system-ui';ctx.textBaseline='alphabetic';[0,Math.floor(data.length/2),data.length-1].forEach(i=>ctx.fillText(String(data[i].time||'').slice(-11),xAt(i)-24,H-14));
  bindChartEvents(canvas,ch);
}
function bindChartEvents(canvas,ch){
  if(canvas.dataset.bound==='1')return;canvas.dataset.bound='1';
  const line=document.getElementById('chartCrossLine');
  const tip=document.getElementById('chartTooltip');
  let raf=0,lastEvt=null;
  function hideHover(){
    if(line)line.style.display='none';
    if(tip)tip.style.display='none';
  }
  function updateHover(e){
    const meta=canvas._chartHover; if(!meta||!meta.data||!meta.data.length)return;
    const r=canvas.getBoundingClientRect();
    const mx=e.clientX-r.left;
    const {data,pad,W,plotW}=meta;
    const x=Math.max(pad.l,Math.min(W-pad.r,mx));
    const idx=Math.max(0,Math.min(data.length-1,Math.round((x-pad.l)/(plotW/Math.max(1,data.length-1)))));
    const item=data[idx];
    const xx=pad.l+idx*(plotW/Math.max(1,data.length-1));
    if(line){
      line.style.display='block';
      line.style.transform=`translateX(${Math.round(xx)}px)`;
      line.style.left='0px';
    }
    if(tip){
      const bw=250; let left=Math.min(W-bw-12,xx+12); if(left<8)left=8;
      tip.style.display='block';
      tip.style.transform=`translate(${Math.round(left)}px,42px)`;
      tip.style.left='0px'; tip.style.top='0px';
      tip.innerHTML=`<b>${item.time||''}</b><br>始 ${Math.round(item.open||item.close).toLocaleString()}　高 ${Math.round(item.high||item.close).toLocaleString()}　安 ${Math.round(item.low||item.close).toLocaleString()}　終 ${Math.round(item.close).toLocaleString()}<br>出来高 ${(item.volume||0).toLocaleString()}<br>RSI ${item.rsi14??'—'} / MACD ${item.macd??'—'}`;
    }
  }
  canvas.addEventListener('mousemove',e=>{
    lastEvt=e;
    if(raf)return;
    raf=requestAnimationFrame(()=>{raf=0;updateHover(lastEvt);});
  });
  canvas.addEventListener('mouseleave',hideHover);
  canvas.addEventListener('wheel',e=>{e.preventDefault();return false;},{passive:false});
  ['mousedown','mouseup','dragstart','selectstart','touchstart','touchmove'].forEach(ev=>canvas.addEventListener(ev,e=>{e.preventDefault();return false;},{passive:false}));
}
async function addHolding(){let body={query:holdQuery.value,shares:holdShares.value,avg_price:holdAvg.value,manual_price:holdManual.value};let j=await api('/api/holding/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!j.ok){alert(j.error||'失敗');return}await loadHoldings(true)}
async function addWatch(){let j=await api('/api/watchlist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:watchQuery.value})});if(!j.ok){alert(j.error||'失敗');return}await loadWatch(true)}
async function loadAlerts(){let a=await api('/api/alerts');let arr=a.alerts||a||[];alertsBox.innerHTML=`<table><thead><tr><th>銘柄</th><th>条件</th><th>値</th><th>メモ</th><th>状態</th></tr></thead><tbody>`+arr.map(x=>`<tr><td>${x.code} ${x.name||''}</td><td>${x.condition_type}</td><td>${x.threshold??'—'}</td><td>${x.note||''}</td><td>${x.enabled===0?'停止':'有効'}</td></tr>`).join('')+'</tbody></table>'}
async function addAlert(){let body={query:alertCode.value,condition_type:alertType.value,threshold:alertValue.value,note:alertMemo.value};await api('/api/alerts/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});loadAlerts()}
async function loadTrades(){
  let r=await api('/api/trades');
  let s=r.summary||{};
  tradeSummaryBox.innerHTML=`<div class="tradeKpis"><div class="tradeKpi"><small>取引回数</small><b>${s.total_trades??0}</b></div><div class="tradeKpi"><small>勝率</small><b class="${(s.win_rate||0)>=55?'up':'warn'}">${s.win_rate??0}%</b></div><div class="tradeKpi"><small>PF</small><b>${s.profit_factor??0}</b></div><div class="tradeKpi"><small>平均利益</small><b class="up">${s.avg_win_pct??0}%</b></div><div class="tradeKpi"><small>平均損失</small><b class="down">${s.avg_loss_pct??0}%</b></div><div class="tradeKpi"><small>平均保有</small><b>${s.avg_holding_days??0}日</b></div></div>`;
  let ins=r.insights||{};
  tradeInsightBox.innerHTML=`<h3>勝ちやすい条件</h3>${(ins.win_patterns||[]).map(x=>'・'+x).join('<br>')||'履歴を入れると自動抽出'}<h3>負けやすい条件</h3>${(ins.loss_patterns||[]).map(x=>'・'+x).join('<br>')||'分析中'}<div class="${(ins.warning||'').includes('禁止')?'ruleStop':'ruleGo'}">${ins.warning||'感情ではなく条件一致で判断。'}</div>`;
  tradeTable.innerHTML=`<table><thead><tr><th>銘柄</th><th>買日</th><th>買値</th><th>売日</th><th>売値</th><th>損益</th><th>AI判定</th><th>操作</th></tr></thead><tbody>`+(r.trades||[]).map(t=>`<tr><td>${t.code} ${t.name}</td><td>${t.buy_date}</td><td>${fmtYen(t.buy_price)}</td><td>${t.sell_date}</td><td>${fmtYen(t.sell_price)}</td><td class="${upDown(t.profit_pct)}">${fmtPct(t.profit_pct)}<br>${fmtYen(t.profit)}</td><td>${t.ai_judgement||''}<br><span class="smallTxt">${t.auto_reason||''}</span></td><td><button class="btn delete" onclick="delTrade(${t.id})">削除</button></td></tr>`).join('')+'</tbody></table>';
}
async function delTrade(id){if(!confirm('この取引履歴を削除する？'))return;let j=await api('/api/trades/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});if(!j.ok){alert(j.error||'削除失敗');return}await loadTrades();}
async function addTrade(){let body={code:tradeCode.value,buy_date:tradeBuyDate.value,buy_price:tradeBuyPrice.value,sell_date:tradeSellDate.value,sell_price:tradeSellPrice.value,shares:tradeShares.value};let j=await api('/api/trades/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!j.ok){alert(j.error||'登録失敗');return}await loadTrades()}
let resizeTimer=null;window.addEventListener('resize',()=>{if(currentPage==='chart'&&currentChartData){clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>drawChart(document.getElementById('chartCanvas'),currentChartData),160)}});checkLogin();
