/* 플레이리스트 스튜디오 대시보드
   - 프레임워크 없음. 인터넷 연결 없이도 동작한다.
   - 이 화면의 모든 동작은 CLI 를 부를 뿐이라 크레딧이 소모되지 않는다.
     유료 생성은 "Claude에 붙여넣기" 로 넘긴다. */

'use strict';

// ---------------------------------------------------------------- 기본 도구
const $ = (id) => document.getElementById(id);

function el(tag, props, ...kids) {
  const n = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : String(v));
  }
  for (const kid of kids.flat(4)) {
    if (kid === null || kid === undefined || kid === false) continue;
    n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return n;
}

const TOKEN_KEY = 'pls.token';
function token() {
  const q = new URLSearchParams(location.search).get('t');
  if (q) { try { localStorage.setItem(TOKEN_KEY, q); } catch (e) {} return q; }
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', 'X-Token': token(), ...(opts.headers || {}) },
  });
  const data = await r.json().catch(() => ({ error: '응답을 읽을 수 없습니다.' }));
  if (!r.ok) throw new Error(data.error || `오류 ${r.status}`);
  return data;
}
const post = (p, body) => api(p, { method: 'POST', body: JSON.stringify(body) });

function toast(msg, bad = false) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show' + (bad ? ' bad' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.className = 'toast'; }, bad ? 5200 : 2600);
}

async function copy(text, what = '복사했습니다') {
  try {
    await navigator.clipboard.writeText(text);
    toast(what);
  } catch (e) {
    const ta = el('textarea', { style: 'position:fixed;left:-9999px' });
    ta.value = text;
    document.body.append(ta); ta.select();
    try { document.execCommand('copy'); toast(what); }
    catch (_) { toast('복사에 실패했습니다. 길게 눌러 직접 복사하세요.', true); }
    ta.remove();
  }
}

const fmtDur = (s) => {
  if (!s && s !== 0) return '—';
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`
           : `${m}:${String(x).padStart(2, '0')}`;
};
const ago = (iso) => {
  if (!iso) return '';
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 90) return '방금';
  if (d < 3600) return `${Math.round(d / 60)}분 전`;
  if (d < 86400) return `${Math.round(d / 3600)}시간 전`;
  return `${Math.round(d / 86400)}일 전`;
};

// ---------------------------------------------------------------- 전역 상태
const S = { boot: null, project: null, tab: '단계', busy: null, loading: false };

// ---------------------------------------------------------------- 작업 실행
function showRun(text) {
  $('runtxt').textContent = text;
  $('runbar').classList.add('show');
}
function hideRun() { $('runbar').classList.remove('show'); }

function openSheet(title, body) {
  $('sheettitle').textContent = title;
  $('sheetbody').textContent = body || '';
  $('sheet').classList.add('open');
  $('sheetbody').scrollTop = $('sheetbody').scrollHeight;
}
$('sheetclose').onclick = () => $('sheet').classList.remove('open');
$('sheetcopy').onclick = () => copy($('sheetbody').textContent, '로그를 복사했습니다');
$('runlog').onclick = () => { if (S.busy) openSheet(S.busy.label, S.busy.log || ''); };

/** 백그라운드 작업 실행 + 완료까지 폴링. 완료되면 화면을 새로 그린다. */
async function run(command, args, label, { silent = false } = {}) {
  if (S.busy) { toast('이미 실행 중인 작업이 있습니다.', true); return null; }
  let job;
  try {
    ({ job } = await post('/api/run', { command, args }));
  } catch (e) { toast(e.message, true); return null; }

  S.busy = { label, log: '' };
  showRun(label + (job.slow ? ' — 몇 분 걸릴 수 있습니다' : '…'));

  const started = Date.now();
  while (true) {
    await new Promise((r) => setTimeout(r, 900));
    let st;
    try { st = await api('/api/job/' + job.id); }
    catch (e) { S.busy = null; hideRun(); toast(e.message, true); return null; }
    S.busy.log = st.log;
    if ($('sheet').classList.contains('open')) {
      $('sheetbody').textContent = st.log;
      $('sheetbody').scrollTop = $('sheetbody').scrollHeight;
    }
    if (job.slow) {
      showRun(`${label} — ${Math.round((Date.now() - started) / 1000)}초 경과`);
    }
    if (!st.running) {
      S.busy = null; hideRun();
      const ok = st.returncode === 0;
      if (!silent) {
        if (ok) toast(label + ' 완료');
        else { toast(label + ' 실패 — 로그를 확인하세요', true); openSheet(label + ' (실패)', st.log); }
      }
      await refresh();
      return st;
    }
  }
}

/** 조회성 명령 — 즉시 JSON 을 받는다. */
async function query(command, args) {
  try { return await post('/api/query', { command, args }); }
  catch (e) { toast(e.message, true); return null; }
}

// ---------------------------------------------------------------- 라우팅
function go(hash) { location.hash = hash; }
window.addEventListener('hashchange', navigate);

/** 화면 이동. 필요한 데이터를 먼저 불러온 뒤 그린다.
    (예전에는 곧바로 render 를 불러서 프로젝트 화면이 잠깐 비어 보였다) */
async function navigate() {
  const r = route();
  if (r.name === 'home' || r.name === 'new') { S.project = null; render(); return; }
  if (!r.key) { render(); return; }
  if (!S.project || S.project.key !== r.key) {
    S.project = null;
    S.tab = '단계';
    S.loading = true;
    render();
    try { S.project = await api('/api/project/' + encodeURIComponent(r.key)); }
    catch (e) { toast(e.message, true); }
    S.loading = false;
  }
  render();
}

function route() {
  const h = location.hash.replace(/^#\/?/, '');
  if (!h) return { name: 'home' };
  const parts = h.split('/');
  if (parts[0] === 'new') return { name: 'new' };
  if (parts[0] === 'p') {
    return { name: parts[2] || 'project', key: decodeURIComponent(parts[1] || '') };
  }
  return { name: 'home' };
}

async function refresh() {
  const r = route();
  if (r.name !== 'home' && r.key) {
    try { S.project = await api('/api/project/' + encodeURIComponent(r.key)); }
    catch (e) { S.project = null; }
  }
  try { S.boot = await api('/api/bootstrap'); } catch (e) {}
  render();
}

// ---------------------------------------------------------------- 화면
let RENDER_SEQ = 0;

function render() {
  const r = route();
  const seq = ++RENDER_SEQ;          // 늦게 끝난 비동기 화면이 덮어쓰지 못하게
  const view = $('view');
  view.innerHTML = '';
  $('topbar').classList.toggle('has-back', r.name !== 'home');
  $('back').onclick = () => (r.name === 'project' || r.name === 'new' ? go('/') : history.back());

  if (!S.boot) { view.append(el('div', { class: 'empty' }, '불러오는 중…')); return; }

  const d = S.boot.doctor || {};
  const dot = $('envdot');
  dot.className = 'env-dot ' + (!d.ready ? 'fail' : (d.warnings || []).length ? 'warn' : 'ok');
  dot.title = !d.ready ? '환경 문제 있음' : (d.warnings || []).length ? '경고 있음' : '정상';

  if (r.name === 'home') { $('title').textContent = '플레이리스트 스튜디오'; return viewHome(view); }
  if (r.name === 'new') { $('title').textContent = '새 플레이리스트'; return viewNew(view); }
  if (!S.project) {
    $('title').textContent = '프로젝트';
    view.append(el('div', { class: 'empty' },
      S.loading ? '불러오는 중…' : '프로젝트를 찾을 수 없습니다.'));
    return;
  }
  $('title').textContent = S.project.title;
  if (r.name === 'wizard') return viewWizard(view, seq);
  return viewProject(view);
}

// ---------------------------------------------------------------- 홈
function viewHome(view) {
  const d = S.boot.doctor || {};

  if (!d.ready) {
    view.append(el('div', { class: 'card', style: 'border-color:var(--fail)' },
      el('div', { class: 'eyebrow', style: 'color:var(--fail)' }, '진행 불가'),
      el('h2', null, '먼저 설치해야 할 것이 있습니다'),
      ...(d.blockers || []).map((b) => el('p', null, '• ' + b)),
      el('div', { class: 'hint' }, '설치 후 이 화면을 새로고침하세요.')
    ));
  } else if ((d.warnings || []).length) {
    view.append(el('div', { class: 'card tight' },
      el('div', { class: 'warnbox' },
        el('strong', null, '알아둘 점'),
        ...(d.warnings || []).map((w) => el('div', { style: 'margin-top:5px' }, '• ' + w)))
    ));
  }

  view.append(el('button', { class: 'btn primary block', onclick: () => go('/new') },
    '＋  새 플레이리스트 만들기'));

  const ps = S.boot.projects || [];
  if (!ps.length) {
    view.append(el('div', { class: 'empty' },
      el('div', { class: 'big' }, '🎧'),
      el('div', null, '아직 만든 플레이리스트가 없습니다.'),
      el('div', { class: 'hint', style: 'margin-top:8px' },
        '위 버튼으로 시작하세요. 채널 → 설정 → 가사 → 음악 순으로 안내합니다.')));
  } else {
    view.append(el('h3', { style: 'margin:22px 0 10px;font-size:13px;color:var(--fg-dim)' },
      `내 플레이리스트 ${ps.length}개`));
    for (const p of ps) view.append(projectCard(p));
  }

  view.append(el('div', { class: 'card tight', style: 'margin-top:22px' },
    el('div', { class: 'meta' },
      el('span', null, d.ffmpeg ? '✅ FFmpeg' : '❌ FFmpeg'),
      el('span', null, d.whisper ? '✅ 가사 싱크' : '⚠️ 가사 싱크 추정'),
      el('span', null, (d.platform || {}).system || ''),
    ),
    el('div', { class: 'hint', style: 'margin-top:8px' }, '저장 위치: ' + S.boot.studio_root),
    el('div', { class: 'btn-row', style: 'margin-top:10px' },
      el('button', { class: 'btn sm ghost', onclick: () => run('selftest', ['--tracks', '3', '--seconds', '25'], '전체 점검 (무료)') },
        '전체 점검 실행'),
      el('button', { class: 'btn sm ghost', onclick: refresh }, '새로고침'))
  ));
}

function projectCard(p) {
  const pct = Math.round((p.done_steps / p.total_steps) * 100);
  const verdict = p.qa && p.qa.verdict;
  return el('div', { class: 'card proj', onclick: () => go('/p/' + encodeURIComponent(p.key)) },
    el('div', { class: 'row' },
      el('h2', null, p.title),
      verdict === 'PASS' ? el('span', { class: 'badge ok' }, '완료')
        : verdict === 'WARN' ? el('span', { class: 'badge warn' }, '완료 (확인 1건)')
        : verdict === 'FAIL' ? el('span', { class: 'badge fail' }, 'QA 실패')
        : p.failed_steps.length ? el('span', { class: 'badge fail' }, '중단됨')
        : el('span', { class: 'badge' }, `${p.done_steps}/${p.total_steps}단계`)),
    el('div', { class: 'bar' }, el('i', { style: `width:${pct}%` })),
    el('div', { class: 'meta' },
      el('span', null, p.next_step ? `다음: ${p.next_step.n}. ${p.next_step.title}` : '모든 단계 완료'),
      p.tracks.length ? el('span', null, `${p.tracks.length}곡`) : null,
      el('span', null, ago(p.updated_at))));
}

// ---------------------------------------------------------------- 새 플레이리스트
function viewNew(view) {
  const chans = [...new Set((S.boot.projects || []).map((p) => p.channel))];
  const chanIn = el('input', { type: 'text', placeholder: '예: 로파이 밤 채널', id: 'f_chan' });
  const titleIn = el('input', { type: 'text', placeholder: '예: 비 오는 날 창가에서', id: 'f_title' });
  const existing = el('select', { id: 'f_exist' },
    el('option', { value: '' }, '＋ 새 채널 만들기'),
    ...chans.map((c) => el('option', { value: c }, c)));

  view.append(el('div', { class: 'card' },
    el('h2', null, '플레이리스트 하나를 새로 시작합니다'),
    el('p', null, '채널은 유튜브 채널 하나에 해당합니다. 같은 채널 아래에 플레이리스트를 여러 개 둘 수 있습니다.'),
    el('label', null, '채널'), existing,
    el('div', { id: 'newchanbox' },
      el('label', null, '새 채널 이름'), chanIn,
      el('div', { class: 'hint' }, '한글로 적어도 됩니다. 폴더 이름은 자동으로 안전하게 바꿉니다.')),
    el('label', null, '플레이리스트 제목'), titleIn,
    el('div', { class: 'hint' }, '나중에 유튜브 제목의 바탕이 됩니다. 지금 대충 적고 나중에 바꿔도 됩니다.'),
    el('div', { class: 'btn-row', style: 'margin-top:18px' },
      el('button', { class: 'btn primary block', id: 'f_go' }, '만들기'))));

  const sync = () => { $('newchanbox').style.display = existing.value ? 'none' : ''; };
  existing.onchange = sync; sync();

  $('f_go').onclick = async () => {
    const title = titleIn.value.trim();
    if (!title) { toast('플레이리스트 제목을 적어주세요.', true); return; }
    let chanDir = existing.value;
    if (!chanDir) {
      const name = chanIn.value.trim();
      if (!name) { toast('채널 이름을 적어주세요.', true); return; }
      const r = await query('channel-new', ['--name', name]);
      if (!r || !r.ok) { toast('채널 생성 실패', true); return; }
      chanDir = r.data.dirname;
    }
    const r2 = await query('playlist-new', ['--channel', chanDir, '--title', title]);
    if (!r2 || !r2.ok) { toast('플레이리스트 생성 실패', true); return; }
    toast('만들었습니다');
    await refresh();
    go('/p/' + encodeURIComponent(r2.data.project) + '/wizard');
  };
}

// ---------------------------------------------------------------- 설정 마법사
async function viewWizard(view, seq) {
  const p = S.project;
  $('title').textContent = '설정 — ' + p.title;
  view.append(el('div', { class: 'empty' }, '질문을 불러오는 중…'));

  const r = await api('/api/questions?project=' + encodeURIComponent(p.key)).catch(() => null);
  if (seq !== undefined && seq !== RENDER_SEQ) return;   // 그 사이 화면이 바뀌었다
  view.innerHTML = '';
  if (!r || !r.data) { view.append(el('div', { class: 'empty' }, '질문을 불러오지 못했습니다.')); return; }
  const d = r.data;

  const pct = Math.round((d.answered / d.total) * 100);
  view.append(el('div', { class: 'card tight' },
    el('div', { class: 'meta' }, el('span', null, `${d.answered} / ${d.total} 항목 답변함`)),
    el('div', { class: 'bar' }, el('i', { style: `width:${pct}%` }))));

  const pending = (d.next || []).filter((q) => q.key !== 'thumbnail_concept');
  if (!pending.length) {
    view.append(el('div', { class: 'card next' },
      el('div', { class: 'eyebrow' }, '설정 완료'),
      el('h2', null, '모두 답하셨습니다'),
      el('p', null, '이제 계획을 만들면 곡별 BPM·감정·인트로 악기가 자동으로 배분됩니다.'),
      el('button', {
        class: 'btn primary block',
        onclick: async () => {
          await run('plan', ['--project', p.key], '계획 만들기');
          go('/p/' + encodeURIComponent(p.key));
          await navigate();
        },
      }, '계획 만들기')));
  } else {
    // 한 번에 하나씩만 묻는다.
    const q = pending[0];
    const card = el('div', { class: 'card next' },
      el('div', { class: 'eyebrow' }, `질문 ${d.answered + 1}`),
      el('h2', null, q.label),
      q.hint ? el('p', null, q.hint) : null);

    let picked = q.default != null ? String(q.default) : '';
    if (q.choices && q.choices.length) {
      const box = el('div', { class: 'choices' });
      for (const c of q.choices) {
        const b = el('button', { 'aria-pressed': String(c) === picked }, c);
        b.onclick = () => {
          picked = String(c);
          [...box.children].forEach((x) => x.setAttribute('aria-pressed', x === b));
        };
        box.append(b);
      }
      card.append(box);
    } else {
      const inp = el('input', {
        type: q.kind === 'int' ? 'number' : 'text',
        value: picked, placeholder: q.hint || '',
      });
      inp.oninput = () => { picked = inp.value; };
      card.append(inp);
    }

    card.append(el('div', { class: 'btn-row', style: 'margin-top:18px' },
      el('button', {
        class: 'btn primary block',
        onclick: async () => {
          if (!String(picked).trim()) { toast('값을 골라주세요.', true); return; }
          const res = await query('config-set', ['--project', p.key, `${q.key}=${picked}`]);
          if (!res || !res.ok) { toast('저장 실패', true); return; }
          if ((res.data.warnings || []).length) toast(res.data.warnings[0], true);
          viewRefreshWizard();
        },
      }, '다음')));
    view.append(card);

    if (pending.length > 1) {
      view.append(el('div', { class: 'card tight' },
        el('div', { class: 'hint' }, '남은 질문: ' +
          pending.slice(1, 6).map((x) => x.label).join(' · ') +
          (pending.length > 6 ? ` 외 ${pending.length - 6}개` : ''))));
    }
  }

  if (d.warnings && d.warnings.length) {
    view.append(el('div', { class: 'card tight' },
      el('div', { class: 'warnbox' }, ...d.warnings.map((w) => el('div', null, '• ' + w)))));
  }
  view.append(el('button', {
    class: 'btn ghost block', style: 'margin-top:10px',
    onclick: () => go('/p/' + encodeURIComponent(p.key)),
  }, '나중에 하기'));
}
function viewRefreshWizard() { const v = $('view'); v.innerHTML = ''; viewWizard(v, ++RENDER_SEQ); }

// ---------------------------------------------------------------- 프로젝트
function viewProject(view) {
  const p = S.project;
  const pct = Math.round((p.done_steps / p.total_steps) * 100);

  view.append(el('div', { class: 'card tight' },
    el('div', { class: 'row', style: 'display:flex;gap:10px;align-items:center' },
      el('div', { style: 'flex:1' },
        el('div', { style: 'font-weight:650' }, p.title),
        el('div', { class: 'meta', style: 'margin-top:3px' },
          el('span', null, p.state),
          p.credits_spent ? el('span', null, `${p.credits_spent} cr 사용`) : null,
          el('span', null, ago(p.updated_at)))),
      p.qa && p.qa.verdict ? el('span', {
        class: 'badge ' + (p.qa.verdict === 'PASS' ? 'ok' : p.qa.verdict === 'WARN' ? 'warn' : 'fail'),
      }, 'QA ' + p.qa.verdict) : null),
    el('div', { class: 'bar' }, el('i', { style: `width:${pct}%` }))));

  const tabs = ['단계', '곡', '결과물', 'QA'];
  const bar = el('div', { class: 'tabs' });
  for (const t of tabs) {
    bar.append(el('button', {
      'aria-selected': S.tab === t,
      onclick: () => { S.tab = t; render(); },
    }, t));
  }
  view.append(bar);

  if (S.tab === '단계') tabSteps(view, p);
  else if (S.tab === '곡') tabTracks(view, p);
  else if (S.tab === '결과물') tabFiles(view, p);
  else tabQA(view, p);
}

// ---------------------------------------------------------------- 탭: 단계
function tabSteps(view, p) {
  const next = p.next_step;
  if (next) {
    const acts = stepActions(next.key, p);
    view.append(el('div', { class: 'card next' },
      el('div', { class: 'eyebrow' }, '다음 할 일'),
      el('h2', null, `${next.n}. ${next.title}`),
      el('p', null, STEP_HELP[next.key] || ''),
      acts.paid ? el('div', { class: 'paidbox' },
        el('strong', null, '💳 크레딧이 드는 단계입니다. '),
        '이 화면에서는 준비만 하고, 실제 생성은 Claude 에서 승인 후 진행합니다.') : null,
      el('div', { class: 'btn-row', style: 'margin-top:14px' },
        ...acts.items.map((a, i) => actionButton(a, i === 0)))));
  } else {
    view.append(el('div', { class: 'card next' },
      el('div', { class: 'eyebrow' }, '완료'),
      el('h2', null, '모든 단계를 마쳤습니다'),
      el('p', null, '결과물 탭에서 최종 영상과 유튜브 정보를 확인하세요.'),
      el('button', { class: 'btn primary block', onclick: () => { S.tab = '결과물'; render(); } },
        '결과물 보기')));
  }

  const list = el('div', { class: 'card' }, el('h2', null, '전체 단계'));
  for (const s of p.steps) {
    const isNext = next && next.key === s.key;
    const cls = 'step ' + (s.status === 'done' ? 'done' : s.status === 'failed' ? 'failed'
      : isNext ? 'current' : '');
    const acts = s.status === 'done' || isNext ? null : null;
    list.append(el('div', { class: cls },
      el('div', { class: 'num' }, s.status === 'done' ? '✓' : s.status === 'failed' ? '!' : s.n),
      el('div', { class: 'body' },
        el('div', { class: 't' }, s.title),
        s.error ? el('div', { class: 'n err' }, s.error.split('\n')[0].slice(0, 220))
          : s.note ? el('div', { class: 'n' }, s.note) : null,
        (s.status !== 'pending' || isNext) ? el('div', { class: 'acts' },
          ...stepActions(s.key, p).items.map((a) => actionButton(a, false, true))) : null)));
  }
  view.append(list);

  view.append(el('div', { class: 'card tight' },
    el('div', { class: 'btn-row' },
      el('button', { class: 'btn sm ghost', onclick: () => run('verify', ['--project', p.key], '파일 검증') }, '파일 검증'),
      el('button', { class: 'btn sm ghost', onclick: () => run('verify', ['--project', p.key, '--repair'], '손상 항목 정리') }, '손상 정리'),
      el('button', { class: 'btn sm ghost', onclick: async () => {
        const r = await query('resume', ['--project', p.key]);
        if (r) openSheet('이어서 할 일', JSON.stringify(r.data, null, 2));
      } }, '상태 자세히'))));
}

const STEP_HELP = {
  channel: '채널 폴더를 만듭니다.',
  plan: '장르·곡 수·BPM 같은 것을 정하면 곡별 설계가 자동으로 배분됩니다.',
  lyrics: '곡마다 제목과 가사가 필요합니다. Claude 에게 맡기거나 직접 붙여넣으세요.',
  pilot: '첫 곡 한 곡만 먼저 만들어 듣고, 마음에 들 때만 나머지를 만듭니다.',
  batch: '파일럿과 같은 방식으로 남은 곡을 하나씩 만듭니다.',
  visuals: '곡별 배경 이미지와 대표 썸네일을 준비합니다. 글자는 여기서 합성합니다.',
  align: '음원을 하나로 잇고 가사 자막의 타이밍을 맞춥니다. 무료입니다.',
  metadata: '유튜브 제목·설명·챕터·태그를 만듭니다. 무료입니다.',
  render: '최종 영상을 만들고 검사합니다. 몇 분 걸립니다. 무료입니다.',
};

function actionButton(a, primary = false, small = false) {
  const cls = 'btn' + (primary ? ' primary' : ' ghost') + (small ? ' sm' : '');
  return el('button', { class: cls, onclick: () => a.run() }, a.label);
}

// ---------------------------------------------------------------- 단계별 동작
function stepActions(key, p) {
  const K = p.key;
  const A = (label, fn) => ({ label, run: fn });

  if (key === 'channel') return { items: [] };

  if (key === 'plan') return {
    items: [
      A('설정 이어하기', () => go('/p/' + encodeURIComponent(K) + '/wizard')),
      A('계획 다시 만들기', () => run('plan', ['--project', K], '계획 만들기')),
    ],
  };

  if (key === 'lyrics') return {
    items: [
      A('Claude 에게 가사 맡기기', () => claudeCard('가사 작성', lyricsPrompt(p))),
      A('직접 입력', () => { S.tab = '곡'; render(); }),
      A('가사 검사', async () => {
        const r = await query('lyrics-validate', ['--project', K]);
        if (r) openSheet('가사 검사 결과', formatValidation(r.data));
      }),
      A('가사 확정', () => run('lyrics-collect', ['--project', K], '가사 확정')),
    ],
  };

  if (key === 'pilot' || key === 'batch') {
    const isPilot = key === 'pilot';
    const target = isPilot ? 1 : (p.tracks.find((t) => t.status !== 'verified') || {}).index;
    return {
      paid: true,
      items: [
        A('① 크레딧 계산', () => costDialog(p)),
        A('② 제출 인자 만들기', () => payloadDialog(p, target)),
        A('③ 결과 가져오기', () => importAudioDialog(p)),
        ...(isPilot ? [
          A('④ 들어보고 승인', () => { S.tab = '곡'; render(); }),
          A('승인하기', () => run('pilot-approve', ['--project', K], '파일럿 승인')),
          A('다시 만들기', () => rejectDialog(p)),
        ] : [
          A('진행 상황', () => run('batch-status', ['--project', K], '곡 상태 확인')),
        ]),
        A('자물쇠 풀기', () => releaseDialog(p, target)),
      ],
    };
  }

  if (key === 'visuals') return {
    paid: true,
    items: [
      A('① 이미지 프롬프트 보기', () => promptsDialog(p)),
      A('② Claude 에 붙여넣기', () => claudeCard('이미지 생성', imagePrompt(p))),
      A('③ 이미지 가져오기', () => importImageDialog(p)),
      A('④ 썸네일 만들기', () => thumbnailDialog(p)),
      A('완료 표시', () => run('visuals-done', ['--project', K], '이미지 준비 완료')),
    ],
  };

  if (key === 'align') return {
    items: [
      A('① 음원 병합', () => run('build-audio', ['--project', K, '--crossfade', '1.5'], '음원 정규화·병합')),
      A('② 가사 타이밍 맞추기', () => run('align', ['--project', K, '--method', 'auto'], '가사 정렬')),
      A('③ 자막 만들기', () => run('subtitles', ['--project', K], '자막 생성')),
    ],
  };

  if (key === 'metadata') return {
    items: [A('유튜브 정보 만들기', () => run('metadata', ['--project', K], '메타데이터 생성'))],
  };

  if (key === 'render') return {
    items: [
      A('① 영상 만들기', () => run('render', ['--project', K], '최종 영상 렌더')),
      A('② 검사하기', () => run('qa', ['--project', K], 'QA 검사')),
      A('빠른 초안', () => run('render',
        ['--project', K, '--preset', 'ultrafast', '--crf', '28', '--final-preset', 'veryfast', '--final-crf', '26'],
        '초안 렌더')),
    ],
  };

  return { items: [] };
}

function formatValidation(d) {
  const out = [];
  out.push(`검사한 곡: ${d.checked || 0}`);
  if ((d.errors || []).length) { out.push('', '❌ 반드시 고쳐야 함:'); d.errors.forEach((e) => out.push('  • ' + e)); }
  if ((d.warnings || []).length) { out.push('', '⚠️ 참고:'); d.warnings.forEach((w) => out.push('  • ' + w)); }
  if (!(d.errors || []).length && !(d.warnings || []).length) out.push('', '✅ 문제 없습니다.');
  return out.join('\n');
}

// ---------------------------------------------------------------- Claude 붙여넣기
function claudeCard(title, text) {
  openSheet('Claude 에 붙여넣기 — ' + title, text);
  copy(text, 'Claude 에 붙여넣을 내용을 복사했습니다');
}

function lyricsPrompt(p) {
  const c = p.config || {};
  return [
    '/playlist-studio',
    `프로젝트: ${p.key}`,
    '',
    `3단계 가사를 써줘. ${c.track_count || p.tracks.length}곡 전부.`,
    `- 장르 ${c.subgenre || c.genre || ''}, 상황 ${c.situation || ''}, 목적 ${c.purpose || ''}`,
    `- 가사 언어 ${c.lyrics_language || 'ko'}`,
    '- 곡마다 제목·부제·주제가 서로 달라야 하고, 첫 줄과 후렴이 겹치면 안 돼',
    '- [Verse] [Chorus] 같은 구조 태그를 넣어줘',
    '- track-set 으로 제목·부제·주제를, track-lyrics 로 가사를 저장하고',
    '  마지막에 lyrics-validate 로 검사한 뒤 lyrics-collect 까지 해줘',
  ].join('\n');
}

/** 곡 하나의 제출 인자를 실제로 만들어 Claude 에 붙여넣을 형태로 복사한다.
    이 화면에서는 크레딧이 나가지 않는다 — 인자를 만들고 원장에 자물쇠만 건다. */
async function payloadDialog(p, index) {
  if (!index) { toast('만들 곡이 없습니다.', true); return; }
  const choices = p.tracks.map((t) => ({
    value: String(t.index),
    label: `${t.index}. ${t.title || '(제목 없음)'} — ${TRACK_STATUS[t.status] || t.status}`,
  }));
  const model = p.config.music_model || '';
  modal('제출 인자 만들기', [
    { key: 'index', label: '몇 번 곡인가요?', type: 'select', options: choices, value: String(index) },
  ], async (v) => {
    render();
    const r = await query('submit-payload',
      ['--project', p.key, '--index', v.index, '--claim']);
    if (!r) return;
    if (!r.ok) {
      const d = r.data || {};
      if (d.blocked) {
        openSheet('⛔ 중복 생성 차단',
          [`${v.index}번 곡은 같은 모델·프롬프트·가사로 이미 요청한 적이 있습니다.`,
           `상태: ${(d.existing || {}).status}`,
           `job_key: ${(d.existing || {}).provider_job_id || '(제출 직후, 미기록)'}`,
           `크레딧: ${(d.existing || {}).credits}`,
           '',
           '같은 곡을 두 번 결제하지 않도록 막은 것입니다.',
           '정말 다시 만들려면 [자물쇠 풀기] 를 누르세요. 크레딧이 다시 나갑니다.',
          ].join('\n'));
      } else {
        openSheet('제출 인자 만들기 실패', (d.error || JSON.stringify(d, null, 2)));
      }
      return;
    }
    const d = r.data;
    const text = [
      '/playlist-studio',
      `프로젝트: ${p.key}`,
      '',
      `${v.index}번 곡을 만들어줘.`,
      `차감 예정: ${d.credits} cr (모델 ${d.arguments.model})`,
      '',
      '아래 인자를 하나도 바꾸지 말고 그대로 abocado_generate_audio 에 넣어줘:',
      '',
      '```json',
      JSON.stringify(d.arguments, null, 2),
      '```',
      '',
      '⚠️ 먼저 잔액을 확인하고 차감액을 보여준 뒤 내 승인을 받아. 승인 전에는 제출하지 마.',
      '다 되면 결과 URL 과 job_key 를 알려줘. 내가 대시보드에 붙여넣을게.',
    ].join('\n');
    openSheet(`${v.index}번 곡 제출 인자 — ${d.credits} cr`, text);
    copy(text, 'Claude 에 붙여넣을 내용을 복사했습니다');
  }, el('div', { class: 'paidbox' },
      model
        ? `모델: ${model} — 이 버튼은 인자만 만듭니다. 크레딧은 Claude 가 제출할 때 나갑니다.`
        : '⚠️ 모델을 아직 고르지 않았습니다. 먼저 [① 크레딧 계산] 에서 모델을 정하세요. '
          + '안 그러면 가장 비싼 기본 모델이 쓰입니다.'));
}

/** 실패했거나 잘못 만든 요청의 자물쇠를 푼다. */
function releaseDialog(p, index) {
  modal('자물쇠 풀기', [
    { key: 'index', label: '몇 번 곡인가요?', type: 'select',
      options: p.tracks.map((t) => ({ value: String(t.index),
        label: `${t.index}. ${t.title || ''}` })),
      value: String(index || 1) },
    { key: 'reason', label: '이유 (기록용)', value: '재시도' },
  ], async (v) => {
    render();
    await run('ledger-release',
      ['--project', p.key, '--index', v.index, '--reason', v.reason || '재시도'],
      `${v.index}번 곡 자물쇠 해제`);
  }, el('div', { class: 'paidbox' },
      '⚠️ 자물쇠를 풀고 다시 만들면 크레딧이 또 차감됩니다. '
      + '이미 완료된 곡은 풀리지 않습니다.'));
}

function pilotPrompt(p) {
  return [
    '/playlist-studio',
    `프로젝트: ${p.key}`,
    '',
    '4단계 파일럿 1곡을 만들어줘. 순서는 이렇게:',
    '1. abocado_music 으로 현재 모델 단가를 확인',
    '2. abocado_get_credits 로 지금 잔액을 확인',
    '3. cost 명령으로 표를 만들어 나에게 보여주고 승인을 받아',
    '4. 승인하면 submit-payload --index 1 --claim 으로 인자를 만들어',
    '   abocado_generate_audio 로 제출',
    '5. 다 되면 결과 URL 과 job_key 를 알려줘 (내가 대시보드에 붙여넣을게)',
    '',
    '⚠️ 내가 명시적으로 승인하기 전에는 제출하지 마.',
  ].join('\n');
}

function batchPrompt(p) {
  const left = p.tracks.filter((t) => t.status !== 'verified').map((t) => t.index);
  return [
    '/playlist-studio',
    `프로젝트: ${p.key}`,
    '',
    `5단계 남은 곡을 만들어줘. 남은 곡 번호: ${left.join(', ') || '없음'}`,
    '1. abocado_get_credits 로 잔액 확인 후 cost 표로 총액을 보여주고 승인받아',
    '2. 승인하면 곡마다 submit-payload --index N --claim → abocado_generate_audio',
    '3. 각 곡의 결과 URL 과 job_key 를 번호와 함께 정리해서 알려줘',
    '',
    '⚠️ 이미 만든 곡은 다시 만들지 마. 원장이 막아줄 거야.',
  ].join('\n');
}

function imagePrompt(p) {
  return [
    '/playlist-studio',
    `프로젝트: ${p.key}`,
    '',
    '6단계 이미지를 만들어줘.',
    '1. visual-prompts 로 프롬프트를 뽑아',
    '2. abocado_check_cost 로 견적을 내고 잔액과 함께 보여주고 승인받아',
    '3. 승인하면 abocado_generate_image 로:',
    '   - 썸네일 후보 4장 (콘셉트 A/B/C/D)',
    `   - 곡별 배경 ${p.tracks.length}장`,
    '   - 인트로 1장',
    '4. 각 이미지의 URL 을 역할(썸네일 후보 N / 배경 N / 인트로)과 함께 알려줘',
    '',
    '⚠️ 이미지에 글자를 그리게 하지 마. 제목은 내가 대시보드에서 합성할게.',
  ].join('\n');
}

// ---------------------------------------------------------------- 입력 모달
function modal(title, fields, onSubmit, extra) {
  const view = $('view');
  const inputs = {};
  const card = el('div', { class: 'card next' },
    el('div', { class: 'eyebrow' }, '입력'),
    el('h2', null, title));
  if (extra) card.append(extra);
  for (const f of fields) {
    card.append(el('label', null, f.label));
    let inp;
    if (f.type === 'select') {
      inp = el('select', null, ...f.options.map((o) =>
        el('option', { value: o.value, selected: o.value === f.value }, o.label)));
    } else if (f.type === 'textarea') {
      inp = el('textarea', { placeholder: f.placeholder || '' });
      inp.value = f.value || '';
    } else {
      inp = el('input', { type: f.type || 'text', placeholder: f.placeholder || '', value: f.value || '' });
    }
    inputs[f.key] = inp;
    card.append(inp);
    if (f.hint) card.append(el('div', { class: 'hint' }, f.hint));
  }
  card.append(el('div', { class: 'btn-row', style: 'margin-top:18px' },
    el('button', { class: 'btn ghost', onclick: () => render() }, '취소'),
    el('button', {
      class: 'btn primary', onclick: () => {
        const vals = {};
        for (const [k, i] of Object.entries(inputs)) vals[k] = i.value.trim();
        onSubmit(vals);
      },
    }, '확인')));
  view.innerHTML = '';
  view.append(el('button', { class: 'btn ghost block', style: 'margin-bottom:12px', onclick: () => render() }, '← 돌아가기'), card);
}

function costDialog(p) {
  const models = S.boot.music_models || [];
  modal('크레딧 계산', [
    { key: 'model', label: '음악 모델', type: 'select', value: 'se-motion-music-t2a',
      options: models.map((m) => ({ value: m.key, label: `${m.display} — ${m.credits}cr/곡` })) },
    { key: 'balance', label: '현재 잔액 (Claude 에서 확인한 숫자)', type: 'number', placeholder: '예: 134',
      hint: 'Claude 에게 "잔액 알려줘" 라고 물어보면 abocado_get_credits 로 확인해 줍니다.' },
    { key: 'unit', label: '곡당 크레딧 (비워두면 위 모델 기본값)', type: 'number', placeholder: '선택' },
  ], async (v) => {
    const args = ['--project', p.key, '--model', v.model];
    if (v.balance) args.push('--balance', v.balance);
    if (v.unit) args.push('--unit-credits', v.unit);
    const r = await query('cost', args);
    if (!r) return;
    const d = r.data;
    const lines = [
      `모델        ${d.display}`,
      `곡당        ${d.unit_credits} cr`,
      `만들 곡     ${d.to_generate} 곡 (이미 ${d.already_done}곡 완료)`,
      `───────────────────────────`,
      `총 필요     ${d.total_credits} cr`,
      d.balance == null ? '잔액        확인 안 됨' : `현재 잔액   ${d.balance} cr`,
      d.shortfall > 0 ? `⚠️ 부족      ${d.shortfall} cr` :
        (d.balance != null ? `남는 크레딧 ${d.balance - d.total_credits} cr` : ''),
    ].filter(Boolean);
    openSheet('크레딧 계산 결과', lines.join('\n'));
  });
}

function importAudioDialog(p) {
  const pending = p.tracks.filter((t) => t.status !== 'verified');
  modal('생성된 곡 가져오기', [
    { key: 'index', label: '몇 번 곡인가요?', type: 'select',
      options: p.tracks.map((t) => ({ value: String(t.index), label: `${t.index}. ${t.title || '(제목 없음)'} — ${t.status}` })),
      value: String((pending[0] || p.tracks[0] || {}).index || 1) },
    { key: 'src', label: '결과 URL', placeholder: 'https://...',
      hint: 'Claude 가 알려준 음악 파일 주소를 붙여넣으세요.' },
    { key: 'job', label: 'job_key (선택)', placeholder: '기록용' },
    { key: 'credit', label: '차감된 크레딧 (선택)', type: 'number', placeholder: '예: 48' },
  ], async (v) => {
    if (!v.src) { toast('결과 URL 을 붙여넣으세요.', true); return; }
    const args = ['--project', p.key, '--index', v.index, '--src', v.src];
    if (v.job) args.push('--job-id', v.job);
    if (v.credit) args.push('--credit-cost', v.credit);
    render();
    await run('track-import', args, `${v.index}번 곡 가져오기`);
  });
}

function importImageDialog(p) {
  const roleOpts = [
    { value: 'thumb-candidate:1', label: '썸네일 후보 1 (A)' },
    { value: 'thumb-candidate:2', label: '썸네일 후보 2 (B)' },
    { value: 'thumb-candidate:3', label: '썸네일 후보 3 (C)' },
    { value: 'thumb-candidate:4', label: '썸네일 후보 4 (D)' },
    { value: 'intro:0', label: '인트로 이미지' },
    ...p.tracks.map((t) => ({ value: 'bg:' + t.index, label: `배경 ${t.index}번 — ${t.title || ''}` })),
  ];
  modal('이미지 가져오기', [
    { key: 'role', label: '어떤 이미지인가요?', type: 'select', options: roleOpts },
    { key: 'src', label: '이미지 URL', placeholder: 'https://...' },
    { key: 'job', label: 'job_key (선택)', placeholder: '기록용' },
    { key: 'credit', label: '차감된 크레딧 (선택)', type: 'number' },
  ], async (v) => {
    if (!v.src) { toast('이미지 URL 을 붙여넣으세요.', true); return; }
    const [role, n] = v.role.split(':');
    const args = ['--project', p.key, '--role', role, '--src', v.src, '--provider', 'abocado'];
    if (role === 'bg') args.push('--index', n);
    if (role === 'thumb-candidate') args.push('--slot', n);
    if (v.job) args.push('--job-id', v.job);
    if (v.credit) args.push('--credit-cost', v.credit);
    render();
    await run('image-import', args, '이미지 가져오기');
  });
}

function thumbnailDialog(p) {
  modal('대표 썸네일 만들기', [
    { key: 'concept', label: '어느 후보를 쓸까요?', type: 'select',
      options: [['A', 1], ['B', 2], ['C', 3], ['D', 4]].map(([c, n]) =>
        ({ value: c, label: `후보 ${n} (${c})` })) },
    { key: 'title', label: '썸네일 제목 (비우면 플레이리스트 제목)', placeholder: p.title },
    { key: 'subtitle', label: '부제 (비우면 자동)', placeholder: '자동' },
    { key: 'badge', label: '왼쪽 위 뱃지 (비우면 장르)', placeholder: (p.config.genre || '').toUpperCase() },
  ], async (v) => {
    const args = ['--project', p.key, '--concept', v.concept];
    if (v.title) args.push('--title', v.title);
    if (v.subtitle) args.push('--subtitle', v.subtitle);
    if (v.badge) args.push('--badge', v.badge);
    render();
    await run('thumbnail', args, '썸네일 합성');
    S.tab = '결과물'; render();
  });
}

function rejectDialog(p) {
  modal('파일럿 다시 만들기', [
    { key: 'reason', label: '어떤 점이 마음에 안 드나요?', type: 'textarea',
      placeholder: '예: 보컬이 너무 앞에 나옴 / 드럼이 셈' },
  ], async (v) => {
    render();
    await run('pilot-reject', ['--project', p.key, '--reason', v.reason || '사용자 요청'], '파일럿 거절 기록');
    claudeCard('음색 조정', [
      '/playlist-studio',
      `프로젝트: ${p.key}`,
      '',
      '파일럿이 마음에 안 들어서 거절했어. 이유는:',
      v.reason || '(적지 않음)',
      '',
      'dna-show 로 sonic_dna 를 보여주고, 어떤 항목을 바꾸면 좋을지 하나만 제안해줘.',
      '내가 고르면 dna-set 으로 바꾸고, 다시 크레딧 승인을 받은 뒤 재생성해줘.',
      '⚠️ 재생성하면 크레딧이 또 나간다는 걸 먼저 알려줘.',
    ].join('\n'));
  }, el('div', { class: 'paidbox' }, '⚠️ 다시 만들면 크레딧이 또 차감됩니다.'));
}

async function promptsDialog(p) {
  const r = await query('visual-prompts', ['--project', p.key]);
  if (!r || !r.ok) return;
  const d = r.data;
  const parts = ['[썸네일 후보]'];
  for (const [k, v] of Object.entries(d.thumbnail_prompts || {})) parts.push(`\n--- ${k} ---\n${v}`);
  parts.push('\n\n[인트로]\n' + (d.intro_prompt || ''));
  parts.push('\n\n[곡별 배경]');
  for (const [k, v] of Object.entries(d.bg_prompts || {})) parts.push(`\n--- ${k}번 곡 ---\n${v}`);
  const text = parts.join('\n');
  openSheet('이미지 프롬프트', text);
  copy(text, '프롬프트를 복사했습니다');
}

// ---------------------------------------------------------------- 탭: 곡
function tabTracks(view, p) {
  if (!p.tracks.length) {
    view.append(el('div', { class: 'empty' }, '아직 곡 계획이 없습니다. 설정을 마치고 계획을 만드세요.'));
    return;
  }
  for (const t of p.tracks) {
    const audio = (p.files.audio || {})[String(t.index).padStart(2, '0')];
    const card = el('div', { class: 'card' },
      el('div', { style: 'display:flex;gap:10px;align-items:flex-start' },
        el('div', { style: 'flex:1;min-width:0' },
          el('div', { style: 'font-weight:650' }, `${t.index}. ${t.title || '(제목 없음)'}`),
          t.subtitle ? el('div', { class: 'hint' }, t.subtitle) : null,
          el('div', { class: 'meta', style: 'margin-top:5px' },
            el('span', null, `${t.bpm} BPM`),
            el('span', null, t.mood),
            t.duration_seconds ? el('span', null, fmtDur(t.duration_seconds)) : null)),
        el('span', {
          class: 'badge ' + (t.status === 'verified' ? 'ok' : t.status === 'failed' ? 'fail' : ''),
        }, TRACK_STATUS[t.status] || t.status)));

    if (audio) {
      card.append(el('audio', {
        controls: true, preload: 'none',
        src: mediaUrl(p.key, audio),
      }));
    }
    card.append(el('div', { class: 'btn-row', style: 'margin-top:10px' },
      el('button', { class: 'btn sm ghost', onclick: () => trackEdit(p, t) }, '제목·주제 수정'),
      el('button', { class: 'btn sm ghost', onclick: () => lyricsEdit(p, t) }, '가사 입력'),
      t.lyrics_path ? el('button', {
        class: 'btn sm ghost',
        onclick: async () => {
          const r = await api(`/api/text?project=${encodeURIComponent(p.key)}&path=${encodeURIComponent(t.lyrics_path)}`)
            .catch((e) => ({ text: e.message }));
          openSheet(`${t.index}. 가사`, r.text);
        },
      }, '가사 보기') : null));
    view.append(card);
  }
}

const TRACK_STATUS = {
  planned: '계획됨', lyrics_ready: '가사 완료', submitted: '생성 요청함',
  downloaded: '받음', verified: '완료', failed: '실패', rejected: '거절',
};

function mediaUrl(key, rel) {
  return `/media?project=${encodeURIComponent(key)}&path=${encodeURIComponent(rel)}&t=${encodeURIComponent(token())}`;
}

function trackEdit(p, t) {
  modal(`${t.index}번 곡 정보`, [
    { key: 'title', label: '제목', value: t.title || '' },
    { key: 'subtitle', label: '부제', value: t.subtitle || '' },
    { key: 'theme', label: '가사 주제', value: t.lyrical_theme || '',
      hint: '곡마다 달라야 합니다.' },
  ], async (v) => {
    const args = ['--project', p.key, '--index', String(t.index)];
    if (v.title) args.push('title=' + v.title);
    if (v.subtitle) args.push('subtitle=' + v.subtitle);
    if (v.theme) args.push('lyrical_theme=' + v.theme);
    render();
    await run('track-set', args, `${t.index}번 곡 정보 저장`, { silent: true });
    S.tab = '곡'; render(); toast('저장했습니다');
  });
}

function lyricsEdit(p, t) {
  modal(`${t.index}번 곡 가사`, [
    { key: 'text', label: '가사', type: 'textarea',
      placeholder: '[Verse]\n첫 줄\n둘째 줄\n\n[Chorus]\n후렴 첫 줄',
      hint: '[Verse] [Chorus] 같은 구조 태그를 꼭 넣으세요. 다른 곡과 첫 줄·후렴이 겹치면 안 됩니다.' },
  ], async (v) => {
    if (!v.text) { toast('가사를 입력하세요.', true); return; }
    render();
    await run('track-lyrics', ['--project', p.key, '--index', String(t.index), '--text', v.text],
      `${t.index}번 곡 가사 저장`);
    S.tab = '곡'; render();
  });
}

// ---------------------------------------------------------------- 탭: 결과물
function tabFiles(view, p) {
  const f = p.files || {};
  const any = f.final_mp4 || f.thumbnail || Object.keys(f.meta || {}).length;
  if (!any) {
    view.append(el('div', { class: 'empty' }, '아직 만들어진 결과물이 없습니다.'));
    return;
  }

  if (f.final_mp4) {
    view.append(el('div', { class: 'card' },
      el('h2', null, '최종 영상'),
      el('video', { controls: true, playsinline: true, preload: 'metadata',
                    src: mediaUrl(p.key, f.final_mp4) }),
      el('div', { class: 'meta', style: 'margin-top:9px' },
        el('span', null, fmtDur((p.timing || {}).total_duration)),
        el('span', null, '1920×1080 · 30fps')),
      el('div', { class: 'btn-row', style: 'margin-top:10px' },
        el('a', { class: 'btn sm ghost', href: mediaUrl(p.key, f.final_mp4), download: '' }, '내려받기'))));
  }

  if (f.thumbnail) {
    view.append(el('div', { class: 'card' },
      el('h2', null, '대표 썸네일'),
      el('img', { class: 'preview', src: mediaUrl(p.key, f.thumbnail), alt: '썸네일' }),
      el('div', { class: 'btn-row', style: 'margin-top:10px' },
        el('a', { class: 'btn sm ghost', href: mediaUrl(p.key, f.thumbnail), download: '' }, '내려받기'),
        el('button', { class: 'btn sm ghost', onclick: () => thumbnailDialog(p) }, '다시 만들기'))));
  }

  if ((f.thumb_candidates || []).length) {
    view.append(el('div', { class: 'card' },
      el('h2', null, '썸네일 후보'),
      el('div', { class: 'thumbs' },
        ...f.thumb_candidates.map((c) =>
          el('img', { class: 'preview', src: mediaUrl(p.key, c.path), alt: `후보 ${c.slot}` })))));
  }

  const metaNames = {
    'youtube_title.txt': '유튜브 제목',
    'youtube_description.txt': '유튜브 설명',
    'chapters.txt': '챕터',
    'tags.txt': '태그',
    'generation_disclosure.txt': 'AI 생성 고지',
  };
  const metas = Object.entries(f.meta || {}).filter(([k]) => metaNames[k]);
  if (metas.length) {
    const card = el('div', { class: 'card' }, el('h2', null, '유튜브에 붙여넣을 것'),
      el('p', null, '업로드는 자동으로 하지 않습니다. 아래를 복사해 직접 올리세요.'));
    for (const [k, rel] of metas) {
      card.append(el('div', { class: 'btn-row', style: 'margin-top:8px' },
        el('button', {
          class: 'btn sm ghost', style: 'flex:1',
          onclick: async () => {
            const r = await api(`/api/text?project=${encodeURIComponent(p.key)}&path=${encodeURIComponent(rel)}`)
              .catch((e) => ({ text: e.message }));
            openSheet(metaNames[k], r.text);
          },
        }, metaNames[k] + ' 보기'),
        el('button', {
          class: 'btn sm primary',
          onclick: async () => {
            const r = await api(`/api/text?project=${encodeURIComponent(p.key)}&path=${encodeURIComponent(rel)}`)
              .catch(() => null);
            if (r) copy(r.text.trim(), metaNames[k] + ' 복사됨');
          },
        }, '복사')));
    }
    view.append(card);
  }

  const others = el('div', { class: 'card' }, el('h2', null, '그 밖의 파일'));
  const rows = [
    ['전체 가사', f.lyrics_all], ['자막 SRT', f.srt], ['자막 ASS', f.ass],
    ['권리 기록 rights.json', (f.meta || {})['rights.json']], ['QA 보고서', f.qa_md],
  ].filter(([, v]) => v);
  if (rows.length) {
    for (const [label, rel] of rows) {
      others.append(el('div', { class: 'btn-row', style: 'margin-top:8px' },
        el('button', {
          class: 'btn sm ghost', style: 'flex:1',
          onclick: async () => {
            const r = await api(`/api/text?project=${encodeURIComponent(p.key)}&path=${encodeURIComponent(rel)}`)
              .catch((e) => ({ text: e.message }));
            openSheet(label, r.text);
          },
        }, label),
        el('a', { class: 'btn sm ghost', href: mediaUrl(p.key, rel), download: '' }, '↓')));
    }
    view.append(others);
  }
}

// ---------------------------------------------------------------- 탭: QA
function tabQA(view, p) {
  const q = p.qa;
  if (!q) {
    view.append(el('div', { class: 'card' },
      el('h2', null, '아직 검사하지 않았습니다'),
      el('p', null, '최종 영상을 만든 뒤 검사를 실행하세요.'),
      el('button', { class: 'btn primary block', onclick: () => run('qa', ['--project', p.key], 'QA 검사') },
        '검사 실행')));
    return;
  }
  const c = q.counts || {};
  view.append(el('div', { class: 'card' },
    el('div', { style: 'display:flex;align-items:center;gap:10px' },
      el('h2', { style: 'flex:1;margin:0' }, '검사 결과'),
      el('span', { class: 'badge ' + (q.verdict === 'PASS' ? 'ok' : q.verdict === 'WARN' ? 'warn' : 'fail') },
        q.verdict)),
    el('div', { class: 'meta', style: 'margin-top:10px' },
      el('span', null, `통과 ${c.pass || 0}`),
      el('span', null, `경고 ${c.warn || 0}`),
      el('span', null, `실패 ${c.fail || 0}`)),
    el('div', { class: 'btn-row', style: 'margin-top:12px' },
      el('button', { class: 'btn ghost block', onclick: () => run('qa', ['--project', p.key], 'QA 다시 검사') },
        '다시 검사'))));

  const bad = (q.checks || []).filter((x) => x.status !== 'PASS');
  if (bad.length) {
    const card = el('div', { class: 'card' }, el('h2', null, '확인이 필요한 항목'));
    for (const x of bad) {
      card.append(el('div', { class: 'step' },
        el('div', { class: 'num', style: `background:var(--${x.status === 'FAIL' ? 'fail' : 'warn'});border-color:transparent;color:#fff` },
          x.status === 'FAIL' ? '!' : '?'),
        el('div', { class: 'body' },
          el('div', { class: 't' }, x.name),
          el('div', { class: 'n' }, x.detail || ''))));
    }
    view.append(card);
  }

  const good = (q.checks || []).filter((x) => x.status === 'PASS');
  if (good.length) {
    view.append(el('div', { class: 'card' },
      el('h2', null, `통과한 항목 ${good.length}개`),
      el('div', { class: 'hint' }, good.map((x) => x.name).join(' · '))));
  }
}

// ---------------------------------------------------------------- 시작
(async function boot() {
  if (!token()) {
    $('view').innerHTML = '';
    $('view').append(el('div', { class: 'card' },
      el('h2', null, '접속 주소를 확인해 주세요'),
      el('p', null, 'PC 터미널에 표시된 주소를 그대로 입력해야 합니다. 주소 끝의 ?t=... 부분까지 포함해야 합니다.')));
    return;
  }
  await refresh();
  await navigate();
  setInterval(() => { if (!S.busy && !$('sheet').classList.contains('open')) refresh(); }, 20000);
})();
