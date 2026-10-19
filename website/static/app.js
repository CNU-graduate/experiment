'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states = {pending:'검토 대기', reviewing:'검토 중', hold:'보류', completed:'검증 완료'};
const labels = {Yes:'비교 가능', No:'비교 불가', Unknown:'추가 검토 필요', '':'미선택'};
let state = {cases:[], live:false, csrf:'', filter:'all', query:'', year:'all', purpose:'all', page:1, current:null, dirty:false, busy:false};
let toastTimer;
const fmt = value => value ? new Date(value).toLocaleString('ko-KR', {timeZone:'Asia/Seoul', month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
function toast(message, error=false) {
  const el = $('#toast'); el.textContent = message; el.className = 'toast show' + (error ? ' error':'');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), error ? 8000:4000);
}
async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf}, body:JSON.stringify(body)} : {});
  let data;
  try { data = await response.json(); } catch { throw new Error('서버 응답을 읽을 수 없습니다. 연결 상태를 확인하세요.'); }
  if (!response.ok) throw new Error(data.error || '요청을 처리하지 못했습니다.');
  return data;
}
function statusBadge(status) { return `<span class="badge ${esc(status)}">${esc(states[status])}</span>`; }
function safeLink(url, text) {
  if (!url) return '';
  try { if (!['http:','https:'].includes(new URL(url).protocol)) return ''; } catch {return '';}
  return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)} ↗</a>`;
}
function updateCase(c) {
  const brief = {...c}; delete brief.analyses; delete brief.history;
  const i = state.cases.findIndex(x => x.id === c.id);
  if (i >= 0) state.cases[i] = brief; else state.cases.unshift(brief);
  $('#nav-count').textContent = state.cases.filter(x => x.status !== 'completed').length;
}
function navigate(hash) {
  if (state.busy) {toast('현재 작업이 끝난 후 이동해 주세요.'); return;}
  if (state.dirty) {showLeave(hash); return;}
  location.hash = hash;
}
function pageHeading(eyebrow, title, description, actions='') {
  return `<div class="page-heading"><div><h1>${title}</h1>${description?`<p>${description}</p>`:""}</div><div class="button-row">${actions}</div></div>`;
}
function actions() {return `<a class="btn" href="/api/export" download="residue-expert-reviews.csv">CSV 내보내기</a><button class="btn primary" id="new-case">사례 등록</button>`;}
function queue(completed=false) {
  const all = state.cases;
  const counts = Object.fromEntries(Object.keys(states).map(k => [k, all.filter(c => c.status === k).length]));
  const total = all.length;
  const completion = total ? Math.round(counts.completed / total * 100) : 0;
  const title = completed ? '검증 완료' : '검토 목록';
  $('#main').innerHTML = pageHeading('',title,'',actions()) +
    `    <section class="panel"><div class="panel-heading"><div><h2>${completed?'완료된 검토':'비교 사례 목록'} <span class="panel-count" id="filtered-count"></span></h2></div></div>
      <div class="toolbar"><div class="tabs" role="group" aria-label="작업 상태 필터">${completed ? '<span class="tab active">검증 완료</span>' : [['all','전체',total], ...Object.entries(states).map(([key,name]) => [key,name,counts[key]])].map(([key,name,n])=>`<button class="tab ${state.filter===key?'active':''}" data-filter="${key}">${name}<small>${n}</small></button>`).join('')}</div>
      <div class="filters"><label class="search"><span>⌕</span><input id="search" aria-label="농약명 또는 사례 ID 검색" placeholder="농약명 또는 사례 ID 검색" value="${esc(state.query)}"></label><select id="year-filter" aria-label="연도 필터"><option value="all">전체 연도</option>${[...new Set(all.map(c=>c.year))].sort().reverse().map(y=>`<option ${state.year===y?'selected':''}>${esc(y)}</option>`).join('')}</select><select id="purpose-filter" aria-label="목적 필터"><option value="all">전체 목적</option>${[...new Set(all.map(c=>c.purpose))].sort().map(p=>`<option ${state.purpose===p?'selected':''}>${esc(p)}</option>`).join('')}</select></div></div>
      <div class="table-wrap"><table><thead><tr><th>농약명 / 사례 ID</th><th>대상 연도</th><th>비교 목적</th><th>적용 품목</th><th>작업 상태</th><th>전문가 판정</th><th>검토</th></tr></thead><tbody id="case-rows"></tbody></table></div><div class="pagination" id="pagination"></div>
    </section>`;
  $('#new-case').onclick = newCase;
  $$('.tab[data-filter]').forEach(b => b.onclick = () => {state.filter=b.dataset.filter;state.page=1;$$('.tab').forEach(x=>x.classList.toggle('active',x===b));renderRows(completed);});
  $('#search').oninput = e => {state.query=e.target.value;state.page=1;renderRows(completed);};
  $('#year-filter').onchange = e => {state.year=e.target.value;state.page=1;renderRows(completed);};
  $('#purpose-filter').onchange = e => {state.purpose=e.target.value;state.page=1;renderRows(completed);};
  renderRows(completed);
}
function renderRows(completed) {
  const query = state.query.toLowerCase().trim();
  const rows = state.cases.filter(c => (!completed || c.status==='completed') && (completed || state.filter==='all' || c.status===state.filter) &&
    (state.year==='all' || c.year===state.year) && (state.purpose==='all' || c.purpose===state.purpose) && (!query || `${c.substance} ${c.id}`.toLowerCase().includes(query)));
  const size=10, pages=Math.max(1,Math.ceil(rows.length/size)); state.page=Math.min(state.page,pages);
  $('#filtered-count').textContent = `${rows.length}건`;
  $('#case-rows').innerHTML = rows.slice((state.page-1)*size,state.page*size).map(c => `<tr><td><a class="substance" href="#case/${esc(c.id)}">${esc(c.substance)}</a><span class="case-id">${esc(c.id)}</span></td><td><span class="year-chip">${esc(c.year)}</span></td><td class="purpose">${esc(c.purpose)}</td><td class="commodity">${esc(c.commodity)}</td><td>${statusBadge(c.status)}</td><td>${esc(labels[c.review.label] || '—')}</td><td><a class="row-action" href="#case/${esc(c.id)}">${c.status==='completed'?'결과 보기':'검토하기'} <span>↗</span></a></td></tr>`).join('') || '<tr><td colspan="7" class="empty"><strong>조건에 맞는 사례가 없습니다.</strong>검색어나 필터를 변경해 보세요.</td></tr>';
  const start=Math.max(1, Math.min(state.page-2, pages-4)), nums=Array.from({length:Math.min(5,pages)},(_,i)=>start+i);
  $('#pagination').innerHTML = `<span>총 ${rows.length}건 중 ${rows.length?(state.page-1)*size+1:0}–${Math.min(state.page*size,rows.length)}건 표시</span><div class="pages"><button class="page-btn" data-page="1" ${state.page===1?'disabled':''} aria-label="첫 페이지">«</button><button class="page-btn" data-page="${state.page-1}" ${state.page===1?'disabled':''} aria-label="이전 페이지">‹</button>${nums.map(n=>`<button class="page-btn ${state.page===n?'selected':''}" data-page="${n}" aria-label="${n}페이지" ${state.page===n?'aria-current="page"':''}>${n}</button>`).join('')}<button class="page-btn" data-page="${state.page+1}" ${state.page===pages?'disabled':''} aria-label="다음 페이지">›</button><button class="page-btn" data-page="${pages}" ${state.page===pages?'disabled':''} aria-label="마지막 페이지">»</button></div>`;
  $$('[data-page]').forEach(b=>b.onclick=()=>{state.page=Number(b.dataset.page);renderRows(completed);});
}
function sourceCard(c, side) {
  const eu=side==='EU';
  return `<section class="panel source-card"><div class="source-head"><h2>${eu?'EU':'JMPR'}</h2><div class="source-links">${safeLink(c.source_table_url,'비교표')}${safeLink(c.source_url,'출처')}</div></div><div class="source-text" id="source-${side}">${esc(c[side])}</div></section>`;

}
function detail(c) {
  state.current=c; state.dirty=false;
  const r=c.review;
  $('#main').innerHTML = `<a href="#queue" class="back-link">← 목록</a>`+
    pageHeading('EXPERT REVIEW',esc(c.substance),`<span class="detail-meta"><span>${esc(c.id)}</span><span>·</span><span>${esc(c.year)}년</span><span>·</span><span>${esc(c.purpose)}</span><span>·</span><span>${esc(c.commodity)}</span></span>`,statusBadge(c.status))+
    `<div class="source-grid">${sourceCard(c,'JMPR')}${sourceCard(c,'EU')}</div><div class="review-layout"><div>
      <section class="panel analysis-panel"><div class="panel-heading"><h2>비교 결과</h2><button class="btn" id="analyze" ${!state.live?'disabled title="모델 연결 후 사용할 수 있습니다."':''}>${c.analyses.some(a=>a.mode==='live')?'다시 비교':'비교 실행'}</button></div>
      <div class="analysis-body" id="analysis-body"></div></section>
      <details class="panel history-section"><summary>검토 이력 <span class="panel-count">${c.history.length}</span></summary>${c.history.map(h=>`<div class="history-entry"><strong>${esc(h.data.reviewer||'검토자 미입력')} · ${esc(states[h.action])}${h.data.label?' · '+esc(labels[h.data.label]):''}</strong><small>${fmt(h.created)}</small>${h.data.notes?`<p>${esc(h.data.notes)}</p>`:''}</div>`).join('')||'<div class="empty">저장된 이력이 없습니다.</div>'}</details>
    </div><aside class="panel review-panel"><div class="panel-heading"><h2>최종 판정</h2></div><form class="review-body" id="review-form">
      ${c.status==='completed'?`<div class="save-info">${esc(r.reviewer)} · ${fmt(c.updated)} 확정</div>`:''}
      <div class="field"><span>비교 가능성</span><div class="decision-options"><label class="decision-option"><input type="radio" name="label" value="Yes" ${r.label==='Yes'?'checked':''}>비교 가능 <small>Yes</small></label><label class="decision-option"><input type="radio" name="label" value="No" ${r.label==='No'?'checked':''}>비교 불가 <small>No</small></label></div></div>
      <div class="field"><label for="reviewer">검토자</label><input id="reviewer" name="reviewer" placeholder="이름" value="${esc(r.reviewer||localStorage.getItem('residue-reviewer')||'')}" maxlength="100" autocomplete="name"></div>
      <div class="field"><label for="notes">검토 의견</label><textarea id="notes" name="notes" placeholder="판정 근거 또는 보류 사유" maxlength="20000">${esc(r.notes||'')}</textarea></div>
      <details class="review-reference"><summary>참고한 분석 기록</summary><div class="field"><label for="review-analysis" class="sr-only">참고한 분석 기록</label><select id="review-analysis"><option value="">초안 없이 직접 검토</option>${c.analyses.map(a=>`<option value="${a.analysis_id}" ${String(r.analysis_id)===String(a.analysis_id)?'selected':''}>초안 #${a.analysis_id} · ${a.mode==='preview'?'미리보기':'AI 분석'} · ${fmt(a.created)}</option>`).join('')}</select></div></details>
      <label class="checkbox-label"><input type="checkbox" id="confirmed"><span>원문과 적용 범위를 확인했습니다.</span></label>
      <button type="submit" class="btn primary full" id="complete-review">판정 확정</button><div class="review-buttons"><button type="button" class="btn" id="save-draft">임시 저장</button><button type="button" class="btn" id="hold-review">보류</button></div>
    </form></aside></div>`;
  renderAnalysis(c.analyses[0]);
  $('#review-form').oninput = () => {state.dirty=true;};
  $('#review-form').onchange = () => {state.dirty=true;};
  $('#review-form').onsubmit = e => {e.preventDefault();saveReview('completed');};
  $('#save-draft').onclick = () => saveReview('reviewing');
  $('#hold-review').onclick = () => saveReview('hold');
  $('#analyze').onclick = analyze;
}
function predictionResult(a) {
  const predicted = a?.mode === 'live' && ['Yes', 'No'].includes(a.label) ? a.label : null;
  const unknown = a?.mode === 'live' && !predicted;
  return `<section class="prediction-result" aria-label="모델 예측"><span class="prediction-label">모델 예측</span>${predicted?`<div class="prediction-value ${predicted.toLowerCase()}"><strong>${predicted}</strong><span>${labels[predicted]}</span></div>`:`<div class="prediction-value pending"><strong>—</strong><span>${unknown?'판단 유보':'예측 결과 없음'}</span>`+`</div>`}${unknown?'<p class="prediction-note">추가 자료 확인이 필요합니다.</p>':''}</section>`;
}
function renderAnalysis(a) {
  const live = a?.mode === 'live';
  const versions = state.current.analyses.filter(x=>x.mode==='live');
  $('#analysis-body').innerHTML = `${versions.length>1?`<div class="field version-field"><label for="analysis-version">분석 기록</label><select id="analysis-version">${versions.map(x=>`<option value="${x.analysis_id}" ${x.analysis_id===a?.analysis_id?'selected':''}>${fmt(x.created)}</option>`).join('')}</select></div>`:''}
    ${predictionResult(a)}
    ${live?`<div class="analysis-summary"><h3>판정 근거</h3><p>${esc(a.summary)}</p></div>
    <div class="comparison-checks">${a.checks.map((check,i)=>`<div class="check-item"><h3>${esc(check.item)}</h3><div><p>${esc(check.finding)}</p><div class="quotes">${['jmpr','eu'].map(side=>check[side+'_verified']?`<button class="quote-btn" data-quote-index="${i}" data-quote-side="${side}">${side.toUpperCase()} 근거</button>`:check[side+'_quote']?`<span class="unverified">${side.toUpperCase()} 인용 확인 필요</span>`:'').join('')}</div></div></div>`).join('')}</div>
    ${a.uncertainties.length?`<div class="uncertainties"><strong>확인 사항</strong>${a.uncertainties.map(u=>`<div>· ${esc(u)}</div>`).join('')}</div>`:''}
    <div class="analysis-meta">${fmt(a.created)} 분석</div>`:`<p class="analysis-unavailable">${state.live?'비교 실행을 누르면 예측과 근거가 표시됩니다.':'모델 연결 전입니다. 원문을 확인해 직접 판정할 수 있습니다.'}</p>`}`;
  if($('#analysis-version')) $('#analysis-version').onchange=e=>{clearHighlights();renderAnalysis(state.current.analyses.find(x=>x.analysis_id===Number(e.target.value)));};
  $$('[data-quote-index]').forEach(b=>b.onclick=()=>{
    clearHighlights();
    const side=b.dataset.quoteSide.toUpperCase(), quote=a.checks[Number(b.dataset.quoteIndex)][b.dataset.quoteSide+'_quote'];
    const el=$('#source-'+side), text=state.current[side], index=text.indexOf(quote);
    if(index>=0){el.replaceChildren(document.createTextNode(text.slice(0,index)));const mark=document.createElement('mark');mark.textContent=quote;el.append(mark,document.createTextNode(text.slice(index+quote.length)));el.scrollIntoView({behavior:'smooth',block:'center'});}
  });
}
function clearHighlights(){for(const side of ['JMPR','EU']) $('#source-'+side).textContent=state.current[side];}
async function analyze() {
  if(state.busy||!state.live)return;
  const button=$('#analyze');
  state.busy=true;button.disabled=true;button.textContent=state.live?'분석 중… 최대 120초':'초안 준비 중…';
  const busyTimer=setTimeout(()=>{if(state.busy)toast('모델 응답을 기다리고 있습니다. 완료될 때까지 이 화면을 유지해 주세요.');},45000);
  try{
    const c=await api(`/api/cases/${state.current.id}/analyze`,{});
    // Preserve any unsaved human edits while refreshing the independent analysis area.
    state.current.analyses=c.analyses;
    renderAnalysis(c.analyses[0]);
    const select=$('#review-analysis');
    const option=document.createElement('option');option.value=c.analyses[0].analysis_id;option.textContent=`초안 #${c.analyses[0].analysis_id} · ${state.live?'AI 분석':'미리보기'} · ${fmt(c.analyses[0].created)}`;select.append(option);
    toast(state.live?'비교 결과를 저장했습니다.':'미리보기가 생성되었습니다. 실제 LLM 판정은 실행하지 않았습니다.');
  }catch(error){toast(error.message,true);}finally{clearTimeout(busyTimer);state.busy=false;button.disabled=false;button.textContent=state.current.analyses.some(a=>a.mode==='live')?'다시 비교':'비교 실행';}
}
async function saveReview(status) {
  if(state.busy)return;
  const form=$('#review-form');
  const body={status,revision:state.current.revision,label:form.elements.label.value,reviewer:$('#reviewer').value.trim(),notes:$('#notes').value.trim(),confirmed:$('#confirmed').checked,analysis_id:$('#review-analysis').value||''};
  if(status==='completed'&&(!body.label||!body.reviewer||!body.confirmed)){toast('최종 판정, 검토자 이름, 원문 검증 확인을 모두 입력하세요.',true);return;}
  if(status==='hold'&&!body.notes){toast('검토 의견에 보류 사유를 입력하세요.',true);$('#notes').focus();return;}
  state.busy=true;$$('button',form).forEach(b=>b.disabled=true);
  try{
    const c=await api(`/api/cases/${state.current.id}/review`,body);
    localStorage.setItem('residue-reviewer',body.reviewer);updateCase(c);state.dirty=false;detail(c);
    toast(status==='completed'?'판정을 확정했습니다.':status==='hold'?'보류로 저장했습니다.':'임시 저장했습니다.');
  }catch(error){toast(error.message,true);}finally{state.busy=false;$$('button',$('#review-form')).forEach(b=>b.disabled=false);}
}
function historyPage() {
  const rows=state.cases.filter(c=>c.revision>0).sort((a,b)=>b.updated.localeCompare(a.updated));
  $('#main').innerHTML=pageHeading('','판정 이력','',actions())+
    `<section class="panel"><div class="panel-heading"><h2>최근 검토 기록 <span class="panel-count">${rows.length}건</span></h2></div>${rows.map(c=>`<div class="history-page-entry"><div><a class="substance" href="#case/${esc(c.id)}">${esc(c.substance)} <span class="case-id">${esc(c.id)}</span></a><p>${esc(c.review.reviewer||'검토자 미입력')} · ${fmt(c.updated)} (한국 시간) · ${esc(labels[c.review.label]||'판정 미선택')}</p></div><div class="button-row">${statusBadge(c.status)}<a class="row-action" href="#case/${esc(c.id)}">전체 이력 ↗</a></div></div>`).join('')||'<div class="empty"><strong>아직 검토 기록이 없습니다.</strong>사례를 검토하고 저장하면 여기에 표시됩니다.</div>'}</section>`;
  $('#new-case').onclick=newCase;
}
function openModal(title, body) {
  $('#modal-content').innerHTML=`<div class="modal-head"><h2>${title}</h2><button class="close-btn" aria-label="닫기" id="modal-close">×</button></div><div class="modal-body">${body}</div>`;
  $('#modal-close').onclick=()=>$('#modal').close();
  if(!$('#modal').open)$('#modal').showModal();
}
function showLeave(hash) {
  openModal('저장하지 않은 검토가 있습니다',`<p>현재 입력한 판정과 의견을 저장하지 않고 이동할까요?</p><div class="modal-actions"><button class="btn" id="stay">계속 검토</button><button class="btn primary" id="leave">저장하지 않고 이동</button></div>`);
  $('#stay').onclick=()=>$('#modal').close();
  $('#leave').onclick=()=>{state.dirty=false;$('#modal').close();location.hash=hash;};
}
function newCase() {
  openModal('새 비교 사례 등록',`<p>잔류정의 원문과 적용 목적·품목을 입력하세요. 등록 후 전문가 검토를 시작할 수 있습니다.</p><form id="new-form"><div class="form-grid"><div class="field"><label for="new-substance">농약명</label><input id="new-substance" name="substance" required maxlength="300" placeholder="예: Flubendiamide"></div><div class="field"><label for="new-year">자료 연도</label><input id="new-year" name="year" required type="number" min="2000" max="2100" value="2025"></div><div class="field"><label for="new-purpose">비교 목적</label><select id="new-purpose" name="purpose"><option>Enforcement</option><option>Risk assessment</option></select></div><div class="field"><label for="new-commodity">적용 품목</label><input id="new-commodity" name="commodity" required maxlength="1000" placeholder="예: Plant products"></div></div><div class="field"><label for="new-jmpr">JMPR 잔류정의 원문</label><textarea id="new-jmpr" name="JMPR" required maxlength="20000" placeholder="원문을 그대로 붙여 넣으세요."></textarea></div><div class="field"><label for="new-eu">EU 잔류정의 원문</label><textarea id="new-eu" name="EU" required maxlength="20000" placeholder="Reg. / Peer review / MRL review 구분을 포함하세요."></textarea></div><div class="field"><label for="new-source">자료 출처 URL (선택)</label><input id="new-source" name="source_url" type="url" placeholder="https://…" maxlength="2000"></div><p class="form-error" id="new-error" role="alert"></p><div class="modal-actions"><button type="button" class="btn" id="new-cancel">취소</button><button class="btn primary" type="submit">등록하고 검토하기 →</button></div></form>`);
  $('#new-cancel').onclick=()=>$('#modal').close();
  $('#new-form').onsubmit=async e=>{
    e.preventDefault();const button=$('button[type=submit]',e.target);button.disabled=true;
    try{const c=await api('/api/cases',Object.fromEntries(new FormData(e.target)));updateCase(c);$('#modal').close();navigate('#case/'+c.id);toast('새 비교 사례가 등록되었습니다.');}
    catch(error){$('#new-error').textContent=error.message;}finally{button.disabled=false;}
  };
}
function guide() {
  openModal('사용 안내',`<h3>검토</h3><p>목적과 품목을 확인하고 JMPR·EU 원문을 비교합니다. 비교 실행 후 모델 예측과 근거를 확인할 수 있습니다.</p><h3>저장</h3><p>검토 중인 내용은 임시 저장합니다. 추가 자료가 필요하면 사유를 적고 보류합니다. 최종 판정은 Yes 또는 No를 선택하고 검토자와 원문 확인 여부를 입력해 확정합니다.</p><h3>기록</h3><p>이전 판정은 검토 이력에서 확인합니다. 목록의 CSV 내보내기로 현재 판정을 내려받을 수 있습니다.</p>`);
}
let routeToken=0, lastHash=location.hash||'#queue';
async function route() {
  const token=++routeToken;
  const hash=location.hash||'#queue';
  if(state.busy){history.replaceState(null,'',lastHash);toast('작업이 끝난 후 이동해 주세요.');return;}
  if(state.dirty&&hash!==lastHash){history.replaceState(null,'',lastHash);showLeave(hash);return;}
  lastHash=hash;state.current=null;state.dirty=false;
  const section=hash.startsWith('#case/')?'queue':hash.slice(1);
  $$('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===section));
  $('#breadcrumb').textContent=({'queue':'검토 목록',completed:'검증 완료',history:'판정 이력'})[section]||'검토 목록';
  if(hash.startsWith('#case/')){
    $('#main').innerHTML='<div class="loading">비교 사례를 불러오고 있습니다…</div>';
    try{const c=await api('/api/cases/'+encodeURIComponent(hash.slice(6)));if(token===routeToken)detail(c);}
    catch(error){if(token===routeToken)$('#main').innerHTML=`<div class="empty"><strong>${esc(error.message)}</strong><a class="btn" href="#queue">목록으로 돌아가기</a></div>`;}
  }else if(section==='history')historyPage();else queue(section==='completed');
  window.scrollTo(0,0);
}
document.addEventListener('click',e=>{
  const a=e.target.closest('a[href^="#"]');
  if(a&&a.getAttribute('href')!=='#main') {e.preventDefault();navigate(a.getAttribute('href'));}
});
window.addEventListener('hashchange',route);
window.addEventListener('beforeunload',e=>{if(state.dirty||state.busy){e.preventDefault();e.returnValue='';}});
$('#guide-button').onclick=guide;
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const rect=e.target.getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)e.target.close();}});
async function boot(){
  try{
    const data=await api('/api/bootstrap');Object.assign(state,data);
    $('#connection').textContent=data.live?'모델 연결됨':'모델 미연결';
    $('#nav-count').textContent=state.cases.filter(c=>c.status!=='completed').length;
    await route();
  }catch(error){$('#main').innerHTML=`<div class="empty"><strong>워크스페이스 연결에 실패했습니다.</strong>${esc(error.message)}<p>서버 실행 여부를 확인하고 페이지를 새로고침하세요.</p></div>`;}
}
boot();
