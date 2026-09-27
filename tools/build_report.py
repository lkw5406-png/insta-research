"""리포트 생성 Tool — 'LKW 리서치 보드'. 판정표(data/photo_labels.json)의 패션 사진을 목록별 사진 갤러리로 만든다.

- 목록: [전체 | 인스타그램 | 핀터레스트 | 런웨이 | AI추천 | 휴지통] (common.BOARDS + '전체'(기본) + AI추천 + 휴지통,
  주소 #all / #instagram / #pinterest / #runway / #ai / #trash).
  (2026-09-27 사장님 요청으로 '전체' 추가. 전체 목록의 사진 카드에는 어느 목록 사진인지 표시)
- AI추천(2026-09-27): data/ai_picks.json — Claude가 보드와 무드가 비슷한 사진을 찾아 고른 것(tools/ai_picks.py).
  사장님이 모은 사진이 아니라 [전체]에는 안 섞음. 카드에 원래 페이지 링크 + '보드에서 닮은 사진' 번호(누르면 그 사진 검색).
- 휴지통(2026-09-27): 사진마다 [휴지통] 버튼 → 휴지통 탭, 거기서 [복구]. 사이트는 보기 전용이라 누른 것은 그 기기(브라우저)에만
  저장됨 → 위쪽 [변경 목록 복사] 글을 사장님이 Claude에게 주면 tools/ai_picks.py --apply로 판정표에 반영("trashed": 날짜).
  반영된 휴지통 사진은 모든 기기의 휴지통 탭에 보이고, 파일은 지우지 않음(복구 가능).
- 사진마다 출처(인스타·핀터레스트 @아이디는 프로필 링크, 런웨이는 브랜드·시즌), 저장 날짜, 한 줄 설명, 키워드.
- 걸러 보기: [전체|여성|남성] · 아이템·스타일·컬러·소재 · 출처 계정 · 기간(전체/이번 주/이번 달).
  출처 버튼은 사진 4장 이상인 출처만 보임(MIN_SOURCE, 2026-09-27 사장님 요청). 적은 출처도 검색칸으로는 찾을 수 있음.
- 기본(로컬): report/index.html 이 ../photos/ 원본 사진을 읽음 → 이 PC에서만 열림.
- --publish: 깃허브 공개 링크용 docs/index.html + docs/img/(목록용 긴 변 480px) + docs/img/big/(눌렀을 때 확대용 1000px).
  (2026-09-27 사장님 요청: 눌렀을 때 더 크게 → 확대용 추가. 원본 캡처 전체는 여전히 비공개)
  사장님 결정(2026-09-26)으로 공개하되 저작권 위험을 줄임: 검색 차단(noindex + robots.txt), 작은 사진만, 사진마다 출처 계정.
  원본·전체 캡처(inbox/, photos/)는 절대 저장소에 올리지 않음(.gitignore).

사용법 (--publish 에는 Pillow 필요 → uv run --with pillow python ...):
  python tools/build_report.py [--publish]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARDS, DATA_DIR, LABELS_PATH, REPORT_DIR, ROOT, load_json, today_kst

DOCS_DIR = ROOT / "docs"

SWATCH = {"블랙": "#111111", "화이트": "#f7f7f5", "아이보리/크림": "#efe6d2", "그레이/차콜": "#6e6e6e", "네이비": "#1f2a4a",
          "블루/인디고": "#3b5ea8", "브라운/카멜": "#8a5a36", "베이지/샌드": "#d6c3a0", "카키/올리브": "#6b6b3a",
          "그린/민트": "#3f8f5f", "레드/버건디": "#8e1f2c", "핑크": "#e79ab5", "퍼플/라벤더": "#8a6bb8",
          "옐로우/머스타드": "#d8a824", "오렌지": "#e0702a",
          "메탈릭(실버·골드)": "linear-gradient(135deg,#c9c9c9,#f1e3a8 50%,#b9b9b9)",
          "멀티컬러/비비드": "conic-gradient(#e0402a,#e0c02a,#3fb04f,#2a78d6,#9a4ad6,#e0402a)"}
ALL = {"all": {"name": "전체", "folder": "", "source_label": "출처"}}  # 3개 목록을 합친 보기 (AI추천 제외)
EXTRA = {"ai": {"name": "AI추천", "folder": "", "source_label": "출처"},      # Claude가 찾은 비슷한 무드 사진
         "trash": {"name": "휴지통", "folder": "", "source_label": "출처"}}   # 휴지통에 넣은 사진 (모든 목록)
AI_PATH = DATA_DIR / "ai_picks.json"
FIELDS = ["items", "styles", "colors", "materials", "details"]
PUBLISH_MAX = 480  # --publish 때 목록에 쓰는 사진 긴 변(px)
ZOOM_MAX = 1000    # 사진을 눌렀을 때 크게 보는 사진 긴 변(px)
MIN_SOURCE = 4     # 출처 필터 버튼은 사진이 이 장수 이상인 출처만 (2026-09-27 사장님 요청: 3장 이하 숨김)


def rows(publish: bool) -> list[dict]:
    out, keep = [], set()
    for fid, l in load_json(LABELS_PATH, {}).items():
        if not l.get("fashion"):
            continue
        for k, p in enumerate(l.get("photos", [])):
            src = small_copy(ROOT / p, keep) if publish else "../" + p
            big = small_copy(ROOT / p, keep, "big", ZOOM_MAX) if publish else "../" + p
            code = l.get("code", "") + ("" if k == 0 else f"_{k + 1}")
            out.append({"id": f"{fid}_{k}", "code": code, "tc": l.get("code", ""), "t": l.get("trashed", ""),
                        "b": l.get("board", "instagram"), "src": src, "big": big,
                        "source": l.get("source", ""), "origin": l.get("origin", ""), "note": l.get("source_note", ""),
                        "g": l["gender"], "sum": l.get("summary", ""), "added": l["added"],
                        **{f: l.get(f, []) for f in FIELDS}})
    for code, a in load_json(AI_PATH, {}).items():
        src = small_copy(ROOT / a["photo"], keep) if publish else "../" + a["photo"]
        big = small_copy(ROOT / a["photo"], keep, "big", ZOOM_MAX) if publish else "../" + a["photo"]
        out.append({"id": code, "code": code, "tc": code, "t": a.get("trashed", ""), "b": "ai", "src": src, "big": big,
                    "source": a["source"], "link": a["link"], "via": a["via"], "ref": a.get("ref", ""), "origin": "", "note": "",
                    "g": a["gender"], "sum": a["summary"], "added": a["added"], **{f: a.get(f, []) for f in FIELDS}})
    if publish:  # 판정표에서 빠진 사진의 공개본은 지움
        for old in (DOCS_DIR / "img").rglob("*.jpg"):
            if old.relative_to(DOCS_DIR / "img").as_posix() not in keep:
                old.unlink()
    return sorted(out, key=lambda r: (r["added"], r["code"] or r["id"]), reverse=True)


def small_copy(path: Path, keep: set, sub: str = "", size: int = PUBLISH_MAX) -> str:
    """공개용 축소본 docs/img/[sub/]<이름>.jpg (이미 있으면 그대로)."""
    from PIL import Image
    rel = f"{sub}/{path.name}" if sub else path.name
    out = DOCS_DIR / "img" / rel
    keep.add(rel)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(path).convert("RGB")
        im.thumbnail((size, size), Image.LANCZOS)
        im.save(out, "JPEG", quality=80)
    return "img/" + rel


CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781; --grid:#e1e0d9;
  --border:rgba(11,11,11,.10); --accent:#2a78d6; --chip:rgba(42,120,214,.12); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781; --grid:#2c2c2a;
  --border:rgba(255,255,255,.10); --accent:#3987e5; --chip:rgba(57,135,229,.25); } }
:root[data-theme="dark"] { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7; --muted:#898781; --grid:#2c2c2a;
  --border:rgba(255,255,255,.10); --accent:#3987e5; --chip:rgba(57,135,229,.25); }
* { box-sizing:border-box; } [hidden] { display:none !important; }
body { margin:0; background:var(--page); color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif; }
a { color:inherit; }
.wrap { max-width:1200px; margin:0 auto; padding:28px 16px 64px; }
header h1 { font-size:26px; margin:0 0 4px; letter-spacing:-.01em; }
header p { margin:0; color:var(--ink-2); }
.topbar { position:sticky; top:0; z-index:5; background:var(--page); margin:18px 0 14px; padding:10px 0;
  display:flex; flex-wrap:wrap; gap:10px 12px; align-items:center; border-bottom:1px solid var(--grid); }
.pill { display:inline-flex; padding:3px; border:1px solid var(--border); border-radius:999px; background:var(--surface); }
.pill button { font:inherit; font-weight:700; padding:6px 14px; border:0; border-radius:999px; cursor:pointer;
  background:transparent; color:var(--ink-2); }
.pill button[aria-pressed="true"] { background:var(--ink); color:var(--page); }
.search { flex:1 1 220px; max-width:320px; font:inherit; font-size:14px; padding:8px 14px; border-radius:999px;
  border:1px solid var(--border); background:var(--surface); color:var(--ink); }
.search:focus { outline:2px solid var(--accent); outline-offset:1px; }
button:focus-visible, a:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }
.stat { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:12px 14px; }
.stat small { color:var(--muted); font-size:12px; } .stat b { display:block; font-size:19px; margin-top:2px; }
.facets { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.facet { display:flex; gap:10px; align-items:flex-start; padding:6px 0; }
.facet > span { flex:none; width:64px; font-size:13px; font-weight:700; color:var(--ink-2); padding-top:5px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip { font:inherit; font-size:13px; padding:4px 10px; border-radius:999px; border:1px solid var(--border);
  background:transparent; color:var(--ink); cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
.chip i { font-style:normal; color:var(--muted); font-size:12px; }
.chip[aria-pressed="true"] { background:var(--accent); border-color:var(--accent); color:#fff; }
.chip[aria-pressed="true"] i { color:rgba(255,255,255,.8); }
.sw { width:12px; height:12px; border-radius:50%; border:1px solid var(--border); flex:none; }
.active { font-size:14px; color:var(--ink-2); margin:0 0 12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.active button { font:inherit; font-size:13px; border:0; background:none; color:var(--accent); cursor:pointer; text-decoration:underline; }
.grid { columns:4 250px; column-gap:14px; }
.item { break-inside:avoid; margin:0 0 14px; background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
.item img { display:block; width:100%; height:auto; background:var(--grid); cursor:zoom-in; }
.item .body { padding:10px 12px 12px; }
.src { font-weight:700; font-size:14px; text-decoration:none; }
.src:hover { text-decoration:underline; }
.unk { font-weight:700; font-size:14px; color:var(--muted); }
.meta { font-size:12px; color:var(--muted); }
.sum { margin:4px 0 8px; font-size:14px; }
.tags { display:flex; flex-wrap:wrap; gap:4px; }
.tags span { font-size:12px; padding:2px 8px; border-radius:999px; background:var(--chip); }
.empty { color:var(--muted); padding:48px 16px; text-align:center; line-height:1.8; column-span:all; }
.empty b { color:var(--ink); font-size:17px; }
.item { position:relative; }
.code { position:absolute; top:8px; left:8px; font:700 12px/1 ui-monospace,Consolas,monospace; color:#fff;
  background:rgba(0,0,0,.62); padding:5px 7px; border-radius:6px; letter-spacing:.02em; pointer-events:none; }
.bd { display:inline-block; font-size:11px; font-weight:700; padding:1px 7px; border-radius:6px; margin-right:6px; vertical-align:1px; color:#fff; }
.bd-instagram { background:#c13584; } .bd-pinterest { background:#e60023; } .bd-runway { background:#3a3a3a; } .bd-ai { background:#5b4bc4; }
.via { font-size:11px; font-weight:700; padding:1px 7px; border-radius:6px; margin-right:6px; vertical-align:1px; background:var(--chip); color:var(--ink); }
.acts { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; padding-top:8px; border-top:1px solid var(--grid); }
.acts button { font:inherit; font-size:12px; padding:4px 10px; border-radius:999px; border:1px solid var(--border); background:transparent; color:var(--ink-2); cursor:pointer; }
.acts button:hover { color:var(--ink); border-color:var(--ink-2); }
.acts .ref { color:#5b4bc4; border-color:rgba(91,75,196,.35); }
.item.gone { opacity:.55; }
.tmeta { font-size:12px; color:var(--muted); }
#pending { display:flex; flex-wrap:wrap; gap:8px 12px; align-items:center; margin:0 0 14px; padding:12px 14px; border-radius:12px;
  background:var(--chip); font-size:14px; }
#pending b { font-weight:700; } #pending span { color:var(--ink-2); }
#pending button { font:inherit; font-size:13px; font-weight:700; padding:6px 12px; border-radius:999px; border:0; cursor:pointer; background:var(--ink); color:var(--page); }
#pending button.ghost { background:transparent; color:var(--ink-2); font-weight:400; text-decoration:underline; padding:6px 4px; }
#pending textarea { flex:1 1 100%; font:13px/1.5 ui-monospace,Consolas,monospace; padding:8px; border-radius:8px; border:1px solid var(--border); background:var(--surface); color:var(--ink); }
.empty code { background:var(--chip); color:var(--ink); padding:2px 8px; border-radius:6px; }
.boards { display:flex; gap:8px; margin-top:18px; overflow-x:auto; scrollbar-width:none; }
.boards button { flex:none; font:inherit; font-size:16px; font-weight:700; padding:10px 18px; border-radius:12px; cursor:pointer;
  border:1px solid var(--border); background:var(--surface); color:var(--ink-2); display:inline-flex; gap:8px; align-items:center; }
.boards button i { font-style:normal; font-size:13px; font-weight:600; color:var(--muted); }
.boards button[aria-selected="true"] { background:var(--ink); color:var(--page); border-color:var(--ink); }
.boards button[aria-selected="true"] i { color:var(--page); opacity:.7; }
/* 사진 크게 보기: 화면 전체 덮개 (2026-09-27 PC에서 사진이 작게·흰 테두리로 보여 전체 화면 방식으로 바꿈) */
dialog#zoom { position:fixed; inset:0; width:100vw; height:100vh; max-width:none; max-height:none; margin:0; padding:0;
  border:0; background:rgba(0,0,0,.92); color:#fff; outline:none; overflow:hidden; }
dialog#zoom[open] { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; }
dialog#zoom::backdrop { background:rgba(0,0,0,.92); }
dialog#zoom img { display:block; height:86vh; width:auto; max-width:94vw; object-fit:contain; border-radius:6px; cursor:zoom-out; }
dialog#zoom p { margin:0; max-width:94vw; font-size:14px; text-align:center; color:#fff; }
dialog#zoom .x { position:absolute; top:14px; right:18px; font:inherit; font-size:30px; line-height:1; color:#fff;
  background:rgba(255,255,255,.12); border:0; border-radius:999px; width:44px; height:44px; cursor:pointer; }
@media (orientation:portrait) { dialog#zoom img { height:auto; width:94vw; max-height:80vh; } }
@media (max-width:560px) { .facet { flex-direction:column; gap:4px; } .facet > span { width:auto; padding:0; } }
"""

JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const LBL = {items:'아이템', styles:'스타일', colors:'컬러', materials:'소재', details:'디테일', source:'출처'};
const S = {b: D.boards[location.hash.slice(1)] ? location.hash.slice(1) : 'all', g:'전체', p:'all', f:null};   // f = {field, value}
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const day = s => new Date(s + 'T00:00:00+09:00');
function inPeriod(r) {
  if (S.p === 'all') return true;
  const diff = (day(D.today) - day(r.added)) / 864e5;
  return S.p === 'w' ? diff < 7 : diff < 31;
}
// 휴지통: 서버(판정표 trashed) + 이 기기에서 누른 것(P, localStorage). P = {번호: 'del' | 'res'}
const PK = 'lkw-board-pending';
let P = {}; try { P = JSON.parse(localStorage.getItem(PK) || '{}') || {}; } catch (e) { P = {}; }
const byTc = {}; D.rows.forEach(r => { if (r.tc) (byTc[r.tc] = byTc[r.tc] || []).push(r); });
Object.keys(P).forEach(c => { const r = (byTc[c] || [])[0]; if (!r || (P[c] === 'del') === !!r.t) delete P[c]; });  // 이미 반영된 것은 정리
const savePending = () => { try { localStorage.setItem(PK, JSON.stringify(P)); } catch (e) {} };
const trashed = r => r.tc && P[r.tc] ? P[r.tc] === 'del' : !!r.t;
function setTrash(c, want) { const r = (byTc[c] || [])[0]; if (!r) return; if (!!r.t === want) delete P[c]; else P[c] = want ? 'del' : 'res'; savePending(); }
const inBoard = (r, b) => b === 'trash' ? trashed(r) : !trashed(r) && (b === 'all' ? r.b !== 'ai' : r.b === b);
const pendingText = () => { const d = Object.keys(P).filter(c => P[c] === 'del'), s = Object.keys(P).filter(c => P[c] === 'res');
  return [d.length ? '삭제: ' + d.join(', ') : '', s.length ? '복구: ' + s.join(', ') : ''].filter(Boolean).join(' / '); };
function pendingBar() {
  const n = Object.keys(P).length, el = $('#pending');
  el.hidden = !n;
  if (!n) return;
  el.innerHTML = `<b>이 기기에서 바꾼 것 ${n}건</b><span>다른 기기에도 반영하려면 목록을 복사해 Claude에게 붙여 넣어 주세요.</span>
    <button id="copyp">변경 목록 복사</button><button class="ghost" id="undop">모두 되돌리기</button>
    <textarea id="ptext" rows="2" readonly aria-label="변경 목록">${esc(pendingText())}</textarea>`;
}
const hit = r => { const q = (S.q || '').trim().toLowerCase().replace(/^@/, ''); if (!q) return true;
  return [r.code, r.source, r.origin, r.sum].some(v => (v || '').toLowerCase().replace(/^@/, '').includes(q)); };
const base = () => D.rows.filter(r => inBoard(r, S.b) && (S.g === '전체' || r.g === S.g || r.g === '공용') && inPeriod(r) && hit(r));
const LINK = {instagram: 'https://www.instagram.com/', pinterest: 'https://www.pinterest.com/'};
function tabs() {
  document.querySelectorAll('[data-b]').forEach(x => {
    x.setAttribute('aria-selected', x.dataset.b === S.b);
    x.querySelector('i').textContent = D.rows.filter(r => inBoard(r, x.dataset.b)).length;
  });
}
const has = (r, f) => f.field === 'source' ? r.source === f.value : r[f.field].includes(f.value);
function count(rows, field) {
  const c = {};
  rows.forEach(r => (field === 'source' ? [r.source] : r[field]).forEach(v => { if (v && v !== '확인 불가') c[v] = (c[v] || 0) + 1; }));
  return Object.entries(c).sort((a, b) => b[1] - a[1]);
}
function render() {
  tabs();
  pendingBar();
  const B = D.boards[S.b];
  LBL.source = B.source_label;
  const rows = base();
  const shown = S.f ? rows.filter(r => has(r, S.f)) : rows;
  const none = !D.rows.some(r => inBoard(r, S.b));
  $('#grid').classList.toggle('grid', !none);
  ['#stats', '#facets', '#active'].forEach(k => $(k).hidden = none);
  if (none) {
    $('#grid').innerHTML = S.b === 'trash' ? `<div class="empty"><b>휴지통이 비어 있어요.</b><br>사진의 [휴지통] 버튼을 누르면 여기로 옮겨지고, 여기서 [복구]할 수 있어요.</div>`
      : S.b === 'ai' ? `<div class="empty"><b>AI추천 사진이 아직 없어요.</b><br>"보드랑 비슷한 무드 사진 찾아줘"라고 말씀해 주세요.</div>`
      : `<div class="empty"><b>${B.name} 목록이 아직 비어 있어요.</b><br>
      캡처를 <code>바탕화면/인스타 리서치/inbox/${B.folder || '인스타그램·핀터레스트·런웨이'}</code> 폴더에 넣고 "리서치 보드 정리해줘"라고 말씀해 주세요.</div>`;
    return;
  }
  const top = f => (count(rows, f)[0] || ['-', 0]);
  $('#stats').innerHTML = [['패션 사진', rows.length + '장'], [B.source_label, count(rows, 'source').length + (S.b === 'runway' ? '개' : '곳')], ...(S.b === 'all' ? [['목록', Object.keys(D.boards).filter(k => k !== 'all' && rows.some(r => r.b === k)).map(k => D.boards[k].name).join('·') || '-']] : []),
    ['많이 나온 아이템', top('items')[0]], ['스타일', top('styles')[0]], ['컬러', top('colors')[0]]]
    .map(([k, v]) => `<div class="stat"><small>${k}</small><b>${esc(v)}</b></div>`).join('');
  $('#facets').innerHTML = ['items', 'styles', 'colors', 'materials', 'details', 'source'].map(f => {
    // 출처는 4장 이상인 것만 버튼으로 (2026-09-27 사장님: 3장 이하는 표시하지 말 것). 사진은 그대로 보임
    const list = count(rows, f).filter(([, n]) => f !== 'source' || n >= D.minSource).slice(0, f === 'source' ? 30 : 18);
    if (!list.length) return '';
    return `<div class="facet"><span>${LBL[f]}</span><div class="chips">${list.map(([v, n]) => {
      const on = S.f && S.f.field === f && S.f.value === v;
      const sw = f === 'colors' && D.swatch[v] ? `<b class="sw" style="background:${D.swatch[v]}"></b>` : '';
      return `<button class="chip" aria-pressed="${on}" data-f="${f}" data-v="${esc(v)}">${sw}${esc(v)} <i>${n}</i></button>`;
    }).join('')}</div></div>`;
  }).join('');
  $('#active').innerHTML = S.f ? `<b>${LBL[S.f.field]}: ${esc(S.f.value)}</b> · ${shown.length}장 <button id="clear">전체 보기</button>` : `${shown.length}장, 최근 저장 순`;
  $('#grid').innerHTML = shown.length ? shown.map(r => {
    const src = r.link ? `<a class="src" href="${esc(r.link)}" target="_blank" rel="noopener">${esc(r.source)}</a>`
      : r.source === '확인 불가' || !r.source
      ? `<span class="unk" title="${esc(r.note)}">출처 확인 불가</span>`
      : r.source.startsWith('@') && LINK[r.b]
        ? `<a class="src" href="${LINK[r.b]}${encodeURIComponent(r.source.slice(1))}/" target="_blank" rel="noopener">${esc(r.source)}</a>`
        : `<span class="src">${esc(r.source)}</span>`;
    const origin = r.origin ? ` <span class="meta">· 원출처 ${esc(r.origin)}</span>` : '';
    const tags = [...r.items, ...r.styles, ...r.colors, ...r.materials, ...r.details].map(t => `<span>${esc(t)}</span>`).join('');
    const gone = trashed(r);
    const acts = [r.ref ? `<button class="ref" data-ref="${esc(r.ref)}">보드에서 닮은 사진 ${esc(r.ref)} →</button>` : '',
      r.tc ? (gone ? `<button data-restore="${esc(r.tc)}">복구</button>` : `<button data-trash="${esc(r.tc)}" aria-label="${esc(r.tc)} 휴지통으로">휴지통</button>`) : ''].join('');
    const tinfo = gone ? `<p class="tmeta">휴지통에 넣은 날: ${r.t && P[r.tc] !== 'del' ? r.t : '방금 (이 기기)'}</p>` : '';
    return `<figure class="item${gone ? ' gone' : ''}">${r.code ? `<span class="code">${esc(r.code)}</span>` : ''}<img loading="lazy" src="${r.src}" alt="${esc(r.sum)}" data-big="${r.big}" data-cap="${esc((r.code ? r.code + ' · ' : '') + (r.source || '') + ' · ' + r.sum)}">
      <div class="body">${S.b === 'all' || S.b === 'trash' ? `<span class="bd bd-${r.b}">${esc(D.boards[r.b].name)}</span>` : ''}${r.via ? `<span class="via">${esc(r.via)}</span>` : ''}${src}${origin} <span class="meta">· ${r.g} · ${r.added}</span><p class="sum">${esc(r.sum)}</p><div class="tags">${tags}</div>${tinfo}<div class="acts">${acts}</div></div></figure>`;
  }).join('') : '<p class="empty">조건에 맞는 사진이 없어요.</p>';
}
document.getElementById('q').addEventListener('input', e => { S.q = e.target.value; S.f = null; render(); });
document.addEventListener('click', e => {
  const b = e.target.closest('button');
  const img = e.target.closest('.item img');
  if (img) { $('#zoom img').src = img.src; const big = new Image(); big.onload = () => { $('#zoom img').src = big.src; }; big.src = img.dataset.big || img.src; $('#zoom p').textContent = img.dataset.cap; $('#zoom').showModal(); $('#zoom').focus(); return; }
  if (e.target.closest('#zoom')) { $('#zoom').close(); $('#zoom img').removeAttribute('src'); return; }
  if (!b) return;
  if (b.dataset.b) { S.b = b.dataset.b; S.f = null; history.replaceState(null, '', '#' + S.b); window.scrollTo({top: 0}); }
  else if (b.dataset.g) { S.g = b.dataset.g; S.f = null; document.querySelectorAll('[data-g]').forEach(x => x.setAttribute('aria-pressed', x === b)); }
  else if (b.dataset.p) { S.p = b.dataset.p; S.f = null; document.querySelectorAll('[data-p]').forEach(x => x.setAttribute('aria-pressed', x === b)); }
  else if (b.dataset.f) { const same = S.f && S.f.field === b.dataset.f && S.f.value === b.dataset.v; S.f = same ? null : {field: b.dataset.f, value: b.dataset.v}; }
  else if (b.id === 'clear') S.f = null;
  else if (b.dataset.trash) setTrash(b.dataset.trash, true);
  else if (b.dataset.restore) setTrash(b.dataset.restore, false);
  else if (b.dataset.ref) { S.b = 'all'; S.f = null; S.q = b.dataset.ref; $('#q').value = b.dataset.ref; history.replaceState(null, '', '#all'); window.scrollTo({top: 0}); }
  else if (b.id === 'undop') { P = {}; savePending(); }
  else if (b.id === 'copyp') { const t = pendingText(); navigator.clipboard.writeText(t).then(() => { b.textContent = '복사됨'; })
      .catch(() => { const ta = $('#ptext'); ta.focus(); ta.select(); b.textContent = '아래 글을 복사해 주세요'; }); return; }
  else return;
  render();
});
render();
"""


def page(data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>LKW 리서치 보드</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>LKW 리서치 보드</h1>
  <p>인스타그램·핀터레스트·런웨이에서 모은 패션 사진 {sum(r['b'] != 'ai' for r in data['rows'])}장 + AI추천 {sum(r['b'] == 'ai' for r in data['rows'])}장 · {data['today']} 갱신</p>
  <nav class="boards" role="tablist" aria-label="목록">{''.join(f'<button role="tab" data-b="{k}" aria-selected="false">{b["name"]} <i>0</i></button>' for k, b in data['boards'].items())}</nav>
</header>
<div class="topbar">
  <div class="pill" role="group" aria-label="성별">{''.join(f'<button data-g="{g}" aria-pressed="{str(g == "전체").lower()}">{g}</button>' for g in ("전체", "여성", "남성"))}</div>
  <div class="pill" role="group" aria-label="기간">{''.join(f'<button data-p="{k}" aria-pressed="{str(k == "all").lower()}">{v}</button>' for k, v in (("all", "전체 기간"), ("w", "최근 7일"), ("m", "최근 30일")))}</div>
  <input id="q" class="search" type="search" placeholder="번호·계정 검색 (예: IG-0023, AI-0005, fabregat)" aria-label="번호·계정 검색">
</div>
<div id="pending" role="status" hidden></div>
<div class="stats" id="stats"></div>
<div class="facets" id="facets"></div>
<p class="active" id="active"></p>
<div class="grid" id="grid"></div>
</div>
<dialog id="zoom" tabindex="-1" aria-label="사진 크게 보기"><button class="x" aria-label="닫기">×</button><img alt=""><p></p></dialog>
<script type="application/json" id="data">{blob}</script>
<script>{JS}</script>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    data = {"today": today_kst(), "rows": rows(a.publish), "swatch": SWATCH, "boards": {**ALL, **BOARDS, **EXTRA}, "minSource": MIN_SOURCE}
    folder = DOCS_DIR if a.publish else REPORT_DIR
    folder.mkdir(exist_ok=True)
    out = folder / "index.html"
    out.write_text(page(data), encoding="utf-8")
    if a.publish:
        (DOCS_DIR / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"리포트 생성: 사진 {len(data['rows'])}장(AI추천 포함) → {out.relative_to(ROOT)} ({out.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
