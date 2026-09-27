"""AI추천 · 휴지통 Tool — 'AI추천' 탭 사진(data/ai_picks.json)을 넣고, 모든 목록의 사진을 휴지통에 넣고 빼기.

AI추천 (2026-09-27 사장님 요청: 보드와 무드가 비슷한 사진을 리서치 보드의 별도 탭에):
- Claude가 웹(룩북·런웨이·스트릿 기사)이나 인스타 공식 API(tools/ig_api.py)에서 찾아 직접 보고 고른 사진.
- 번호 AI-0001…. 사진 파일은 photos/ai/ (저장소에 안 올라감), 공개본은 build_report.py --publish가 docs/img/에 만듦.
- 사장님이 모은 사진이 아니므로 [전체] 목록에는 안 섞임.

--add 파일 형식(.tmp/ai_add.json): 사진 한 장씩 목록
  [{"image": "사진 파일 경로", "via": "룩북|런웨이|스트릿|인스타",
    "source": "Graphpaper FW26 또는 @아이디", "link": "원래 페이지·게시물 주소",
    "gender": "여성|남성|공용", "summary": "한 줄 설명", "ref": "IG-0027 (보드에서 닮은 사진, 선택)",
    "items": [], "styles": [], "colors": [], "materials": [], "details": []}]
  이름은 tools/trend_keywords.json 이름표만. 같은 link+image는 한 번만.

휴지통 (2026-09-27 사장님 요청: 삭제 + 복구 가능한 휴지통):
- 지우지 않고 판정표에 "trashed": 날짜만 적음 → 사이트 [휴지통] 탭으로 감. 복구하면 날짜를 지움. 사진 파일은 그대로.
- 사이트에서 누른 휴지통·복구는 그 기기에만 적용됨 → 사장님이 [변경 목록 복사]로 붙여 준 글을 그대로 --apply에 넣음.

사용법 (--add 에 Pillow 필요 → uv run -q --with pillow python ...):
  python tools/ai_picks.py --add .tmp/ai_add.json
  python tools/ai_picks.py --trash IG-0003,AI-0012        휴지통으로
  python tools/ai_picks.py --restore IG-0003              복구
  python tools/ai_picks.py --apply "삭제: IG-0003, AI-0012 / 복구: IG-0010"   사이트에서 복사한 글 그대로
  python tools/ai_picks.py --list                         휴지통 목록
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_DIR, LABELS_PATH, PHOTOS_DIR, ROOT, VOCAB_PATH, load_json, save_json, today_kst  # noqa: E402

AI_PATH = DATA_DIR / "ai_picks.json"
AI_PHOTOS = PHOTOS_DIR / "ai"
VIA = ["룩북", "런웨이", "스트릿", "인스타"]
FIELDS = ["items", "styles", "colors", "materials", "details"]
CODE_RE = re.compile(r"\b(?:IG|PT|RW|AI)-\d{4}\b")


def vocab() -> dict[str, set]:
    v = load_json(VOCAB_PATH, {})
    items = v.get("items", {})
    return {"items": {x for group in items.values() for x in group} if isinstance(items, dict) else set(items),
            **{f: set(v.get(f, [])) for f in ("styles", "colors", "materials", "details")},
            "gender": set(v.get("gender", []))}


def next_code(picks: dict) -> str:
    n = max([int(c[3:]) for c in picks] or [0]) + 1
    return f"AI-{n:04d}"


def add(path: Path) -> None:
    from PIL import Image
    entries = load_json(path, [])
    V = vocab()
    board_codes = {l.get("code") for l in load_json(LABELS_PATH, {}).values()}
    bad = []
    for i, e in enumerate(entries):
        tag = f"{i + 1}번째({Path(e.get('image', '?')).name})"
        if not Path(e.get("image", "")).exists():
            bad.append(f"{tag}: 사진 파일 없음")
        if e.get("via") not in VIA:
            bad.append(f"{tag}: via는 {'/'.join(VIA)} 중 하나")
        for k in ("source", "link", "summary"):
            if not e.get(k):
                bad.append(f"{tag}: {k} 없음")
        if e.get("gender") not in V["gender"]:
            bad.append(f"{tag}: gender는 {'/'.join(sorted(V['gender']))}")
        if e.get("ref") and e["ref"] not in board_codes:
            bad.append(f"{tag}: 보드에 {e['ref']} 번호가 없음")
        for f in FIELDS:
            wrong = [x for x in e.get(f, []) if x not in V[f]]
            if wrong:
                bad.append(f"{tag}: {f}에 이름표 밖 단어 {wrong}")
    if bad:
        sys.exit("문제가 있어 아무것도 안 합침:\n  " + "\n  ".join(bad))

    picks = load_json(AI_PATH, {})
    have = {(p["link"], p.get("image_key")) for p in picks.values()}
    AI_PHOTOS.mkdir(parents=True, exist_ok=True)
    added = 0
    for e in entries:
        key = Path(e["image"]).name
        if (e["link"], key) in have:
            continue
        code = next_code(picks)
        dest = AI_PHOTOS / f"{code}.jpg"
        im = Image.open(e["image"]).convert("RGB")
        im.thumbnail((1000, 1000))
        im.save(dest, quality=88)
        picks[code] = {"code": code, "via": e["via"], "source": e["source"], "link": e["link"],
                       "photo": dest.relative_to(ROOT).as_posix(), "image_key": key,
                       "gender": e["gender"], "summary": e["summary"], "ref": e.get("ref", ""),
                       **{f: e.get(f, []) for f in FIELDS}, "added": today_kst()}
        added += 1
    save_json(AI_PATH, picks)
    print(f"AI추천 {added}장 추가 (전체 {len(picks)}장, 겹쳐서 건너뜀 {len(entries) - added}장)")


# ---------- 휴지통 ----------

def _stores():
    """(파일 경로, 데이터, 번호 → 항목) — 판정표와 AI추천 둘 다."""
    labels = load_json(LABELS_PATH, {})
    picks = load_json(AI_PATH, {})
    index = {l["code"]: l for l in labels.values() if l.get("code")}
    index.update(picks)
    return labels, picks, index


def set_trash(codes: list[str], trash: bool) -> None:
    labels, picks, index = _stores()
    missing = [c for c in codes if c not in index]
    if missing:
        sys.exit(f"없는 번호라 아무것도 안 바꿈: {', '.join(missing)}")
    changed = []
    for c in codes:
        item = index[c]
        if trash and not item.get("trashed"):
            item["trashed"] = today_kst()
            changed.append(c)
        elif not trash and item.get("trashed"):
            item.pop("trashed")
            changed.append(c)
    save_json(LABELS_PATH, labels)
    save_json(AI_PATH, picks)
    word = "휴지통으로" if trash else "복구"
    print(f"{word}: {', '.join(changed) or '바뀐 것 없음(이미 그 상태)'}")


def apply(text: str) -> None:
    """사이트 [변경 목록 복사] 글: '삭제: IG-0003, AI-0012 / 복구: IG-0010'."""
    dele = res = []
    m = re.search(r"삭제\s*:([^/]*)", text)
    if m:
        dele = CODE_RE.findall(m.group(1))
    m = re.search(r"복구\s*:([^/]*)", text)
    if m:
        res = CODE_RE.findall(m.group(1))
    if not dele and not res:
        sys.exit("번호를 못 찾음. 예: \"삭제: IG-0003, AI-0012 / 복구: IG-0010\"")
    if dele:
        set_trash(dele, True)
    if res:
        set_trash(res, False)


def show() -> None:
    _, _, index = _stores()
    t = sorted((v["trashed"], c) for c, v in index.items() if v.get("trashed"))
    print(f"휴지통 {len(t)}장" + "".join(f"\n  {c} ({d})" for d, c in t))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--add", type=Path)
    g.add_argument("--trash")
    g.add_argument("--restore")
    g.add_argument("--apply")
    g.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.add:
        add(a.add)
    elif a.trash:
        set_trash(CODE_RE.findall(a.trash), True)
    elif a.restore:
        set_trash(CODE_RE.findall(a.restore), False)
    elif a.apply:
        apply(a.apply)
    else:
        show()


if __name__ == "__main__":
    main()
