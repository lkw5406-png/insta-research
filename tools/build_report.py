"""리포트 생성 Tool — 'LKW 리서치 보드'. 판정표(data/photo_labels.json)의 패션 사진을 목록별 사진 갤러리로 만든다.

- 목록 3개: [인스타그램 | 핀터레스트 | 런웨이] (common.BOARDS, 주소 #instagram / #pinterest / #runway 로 바로 열림).
- 사진마다 출처(인스타·핀터레스트 @아이디는 프로필 링크, 런웨이는 브랜드·시즌), 저장 날짜, 한 줄 설명, 키워드.
- 걸러 보기: [전체|여성|남성] · 아이템·스타일·컬러·소재 · 출처 계정 · 기간(전체/이번 주/이번 달).
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
from common import BOARDS, LABELS_PATH, REPORT_DIR, ROOT, load_json, today_kst

DOCS_DIR = ROOT / "docs"

SWATCH = {"블랙": "#111111", "화이트": "#f7f7f5", "아이보리/크림": "#efe6d2", "그레이/차콜": "#6e6e6e", "네이비": "#1f2a4a",
          "블루/인디고": "#3b5ea8", "브라운/카멜": "#8a5a36", "베이지/샌드": "#d6c3a0", "카키/올리브": "#6b6b3a",
          "그린/민트": "#3f8f5f", "레드/버건디": "#8e1f2c", "핑크": "#e79ab5", "퍼플/라벤더": "#8a6bb8",
          "옐로우/머스타드": "#d8a824", "오렌지": "#e0702a",
          "메탈릭(실버·골드)": "linear-gradient(135deg,#c9c9c9,#f1e3a8 50%,#b9b9b9)",
          "멀티컬러/비비드": "conic-gradient(#e0402a,#e0c02a,#3fb04f,#2a78d6,#9a4ad6,#e0402a)"}
FIELDS = ["items", "styles", "colors", "materials", "details"]
PUBLISH_MAX = 480  # --publish 때 목록에 쓰는 사진 긴 변(px)
ZOOM_MAX = 1000    # 사진을 눌렀을 때 크게 보는 사진 긴 변(px)


def rows(publish: bool) -> list[dict]:
    out, keep = [], set()
    for fid, l in load_json(LABELS_PATH, {}).items():
        if not l.get("fashion"):
            continue
        for k, p in enumerate(l.get("photos", [])):
            src = small_copy(ROOT / p, keep) if publish else "../" + p
            big = small_copy(ROOT / p, keep, "big", ZOOM_MAX) if publish else "../" + p
            out.append({"id": f"{fid}_{k}", "b": l.get("board", "instagram"), "src": src, "big": big,
                        "source": l.get("source", ""), "origin": l.get("origin", ""), "note": l.get("source_note", ""),
                        "g": l["gender"], "sum": l.get("summary", ""), "added": l["added"],
                        **{f: l.get(f, []) for f in FIELDS}})
    if publish:  # 판정표에서 빠진 사진의 공개본은 지움
        for old in (DOCS_DIR / "img").rglob("*.jpg"):
            if old.relative_to(DOCS_DIR / "img").as_posix() not in keep:
                old.unlink()
    return sorted(out, key=lambda r: (r["added"], r["id"]), reverse=True)


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
const S = {b: D.boards[location.hash.slice(1)] ? location.hash.slice(1) : 'instagram', g:'전체', p:'all', f:null};   // f = {field, value}
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const day = s => new Date(s + 'T00:00:00+09:00');
function inPeriod(r) {
  if (S.p === 'all') return true;
  const diff = (day(D.today) - day(r.added)) / 864e5;
  return S.p === 'w' ? diff < 7 : diff < 31;
}
const base = () => D.rows.filter(r => r.b === S.b && (S.g === '전체' || r.g === S.g || r.g === '공용') && inPeriod(r));
const LINK = {instagram: 'https://www.instagram.com/', pinterest: 'https://www.pinterest.com/'};
function tabs() {
  document.querySelectorAll('[data-b]').forEach(x => {
    x.setAttribute('aria-selected', x.dataset.b === S.b);
    x.querySelector('i').textContent = D.rows.filter(r => r.b === x.dataset.b).length;
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
  const B = D.boards[S.b];
  LBL.source = B.source_label;
  const rows = base();
  const shown = S.f ? rows.filter(r => has(r, S.f)) : rows;
  const none = !D.rows.some(r => r.b === S.b);
  $('#grid').classList.toggle('grid', !none);
  ['#stats', '#facets', '#active'].forEach(k => $(k).hidden = none);
  if (none) {
    $('#grid').innerHTML = `<div class="empty"><b>${B.name} 목록이 아직 비어 있어요.</b><br>
      캡처를 <code>바탕화면/인스타 리서치/inbox/${B.folder}</code> 폴더에 넣고 "리서치 보드 정리해줘"라고 말씀해 주세요.</div>`;
    return;
  }
  const top = f => (count(rows, f)[0] || ['-', 0]);
  $('#stats').innerHTML = [['패션 사진', rows.length + '장'], [B.source_label, count(rows, 'source').length + (S.b === 'runway' ? '개' : '곳')],
    ['많이 나온 아이템', top('items')[0]], ['스타일', top('styles')[0]], ['컬러', top('colors')[0]]]
    .map(([k, v]) => `<div class="stat"><small>${k}</small><b>${esc(v)}</b></div>`).join('');
  $('#facets').innerHTML = ['items', 'styles', 'colors', 'materials', 'details', 'source'].map(f => {
    const list = count(rows, f).slice(0, f === 'source' ? 30 : 18);
    if (!list.length) return '';
    return `<div class="facet"><span>${LBL[f]}</span><div class="chips">${list.map(([v, n]) => {
      const on = S.f && S.f.field === f && S.f.value === v;
      const sw = f === 'colors' && D.swatch[v] ? `<b class="sw" style="background:${D.swatch[v]}"></b>` : '';
      return `<button class="chip" aria-pressed="${on}" data-f="${f}" data-v="${esc(v)}">${sw}${esc(v)} <i>${n}</i></button>`;
    }).join('')}</div></div>`;
  }).join('');
  $('#active').innerHTML = S.f ? `<b>${LBL[S.f.field]}: ${esc(S.f.value)}</b> · ${shown.length}장 <button id="clear">전체 보기</button>` : `${shown.length}장, 최근 저장 순`;
  $('#grid').innerHTML = shown.length ? shown.map(r => {
    const src = r.source === '확인 불가' || !r.source
      ? `<span class="unk" title="${esc(r.note)}">출처 확인 불가</span>`
      : r.source.startsWith('@') && LINK[r.b]
        ? `<a class="src" href="${LINK[r.b]}${encodeURIComponent(r.source.slice(1))}/" target="_blank" rel="noopener">${esc(r.source)}</a>`
        : `<span class="src">${esc(r.source)}</span>`;
    const origin = r.origin ? ` <span class="meta">· 원출처 ${esc(r.origin)}</span>` : '';
    const tags = [...r.items, ...r.styles, ...r.colors, ...r.materials, ...r.details].map(t => `<span>${esc(t)}</span>`).join('');
    return `<figure class="item"><img loading="lazy" src="${r.src}" alt="${esc(r.sum)}" data-big="${r.big}" data-cap="${esc((r.source || '') + ' · ' + r.sum)}">
      <div class="body">${src}${origin} <span class="meta">· ${r.g} · ${r.added}</span><p class="sum">${esc(r.sum)}</p><div class="tags">${tags}</div></div></figure>`;
  }).join('') : '<p class="empty">조건에 맞는 사진이 없어요.</p>';
}
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
  <p>인스타그램·핀터레스트·런웨이에서 모은 패션 사진 · 전체 {len(data['rows'])}장 · {data['today']} 갱신</p>
  <nav class="boards" role="tablist" aria-label="목록">{''.join(f'<button role="tab" data-b="{k}" aria-selected="false">{b["name"]} <i>0</i></button>' for k, b in BOARDS.items())}</nav>
</header>
<div class="topbar">
  <div class="pill" role="group" aria-label="성별">{''.join(f'<button data-g="{g}" aria-pressed="{str(g == "전체").lower()}">{g}</button>' for g in ("전체", "여성", "남성"))}</div>
  <div class="pill" role="group" aria-label="기간">{''.join(f'<button data-p="{k}" aria-pressed="{str(k == "all").lower()}">{v}</button>' for k, v in (("all", "전체 기간"), ("w", "최근 7일"), ("m", "최근 30일")))}</div>
</div>
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
    data = {"today": today_kst(), "rows": rows(a.publish), "swatch": SWATCH, "boards": BOARDS}
    folder = DOCS_DIR if a.publish else REPORT_DIR
    folder.mkdir(exist_ok=True)
    out = folder / "index.html"
    out.write_text(page(data), encoding="utf-8")
    if a.publish:
        (DOCS_DIR / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"리포트 생성: 패션 사진 {len(data['rows'])}장 → {out.relative_to(ROOT)} ({out.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
