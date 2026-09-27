"""AI추천 후보 수집 Tool — 웹 페이지·무신사 스냅·Are.na에서 사진 후보를 받아 번호 딱지 붙은 판독 이미지를 만든다.

Claude가 판독 이미지를 직접 보고 고른 뒤 tools/ai_picks.py --add 로 AI추천 탭에 넣는다 (매뉴얼: workflows/ig_api_reference.md).

출처 종류 (jobs.json의 "kind"):
- "page"    기사·룩북 페이지에서 사진 주소를 뽑음. "match"(정규식)로 원하는 사진만, "skip"으로 제외.
            Hypebeast는 image-cdn.hypb.st 주소가 기사 사진 (…-tw.jpg는 대표 이미지라 skip).
- "musinsa" 무신사 스냅(일반인 착장). "url"에 스냅 목록 주소(예: https://www.musinsa.com/snap/main/recommend?sort=NEWEST).
            robots.txt가 'Claude-User'(사용자가 요청해 Claude가 가져오는 것)를 허용 → 그 이름으로 접속. 사장님 요청 때만 실행.
- "arena"   Are.na 공개 채널(핀터레스트 비슷한 무드보드). 공식 API(api.are.na/v2), 키 필요 없음. "channel"에 채널 slug.
- "kream"   KREAM 스타일(착용 후기) 태그 페이지. "url"에 https://kream.co.kr/social/tags/태그 (한 태그당 최신 20개).
            manifest에 작성자(user)와 태그된 상품(products)도 저장 → 설명 쓸 때 참고.
공통: "id"(파일 앞글자), "label"(출처 이름 — AI추천 카드에 보임), "max"(최대 장수).

사용법 (Pillow 필요 → uv run -q --with pillow python ...):
  python tools/web_cands.py --jobs .tmp/jobs.json      후보 받기 → .tmp/cands/{id}_{nn}.jpg + .tmp/cands/manifest.json
  python tools/web_cands.py --sheet id1 id2 ...        판독 이미지 → .tmp/cands/sheets/{id}_N.jpg (32장씩)
  python tools/web_cands.py --arena-search menswear    Are.na 채널 찾기 (slug·사진 수·제목)
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import TMP_DIR, load_json, save_json  # noqa: E402

OUT = TMP_DIR / "cands"
MANIFEST = OUT / "manifest.json"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
CLAUDE_UA = "Claude-User"   # 무신사 robots.txt가 허용한 이름


def get(url: str, ua: str = BROWSER_UA, referer: str | None = None) -> bytes:
    h = {"User-Agent": ua, "Accept-Language": "ko,en"}
    if referer:
        h["Referer"] = referer
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=40) as r:
        return r.read()


def sized(url: str) -> str:
    """큰 원본 대신 720px 안팎으로 받는 주소 (사이트별)."""
    key = url.split("?")[0]
    if "hypb.st" in key:
        return key + "?w=720&cbr=1&q=90&fit=max"
    if "cdn.sanity.io" in key:
        return key + "?w=720&auto=format"
    if "cdn.shopify.com" in key or "/cdn/shop/" in key:
        return key + "?width=720"
    return url


# ---------- 출처별 후보 목록: [(사진 주소, 원래 페이지 주소)] ----------

def from_page(j: dict) -> list[tuple[str, str]]:
    t = html.unescape(get(j["url"]).decode("utf-8", "ignore")).replace(r"\/", "/").replace(r"/", "/")
    urls = re.findall(r'(?:https?:)?//[^\s"\'<>()\\,]+?\.(?:jpe?g|png|webp)(?:\?[^\s"\'<>()\\,]*)?', t, re.I)
    out, seen = [], set()
    for u in urls:
        u = "https:" + u if u.startswith("//") else u
        if not re.search(j.get("match", "."), u) or (j.get("skip") and re.search(j["skip"], u)):
            continue
        key = u.split("?")[0]
        if key not in seen:
            seen.add(key)
            out.append((u, j["url"]))
    return out


def from_musinsa(j: dict) -> list[tuple[str, str]]:
    t = get(j["url"], CLAUDE_UA).decode("utf-8", "ignore")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
    if not m:
        raise RuntimeError("스냅 목록 데이터를 못 찾음 (사이트 구조가 바뀌었을 수 있음)")
    out, seen = [], set()
    for s in re.finditer(r'\{"type":"SNAP","id":"\d+".*?"thumbnailUrl":"([^"]+)".*?"linkUrl":"([^"]+)"', m.group(1)):
        img, link = s.group(1), s.group(2)
        if link not in seen:
            seen.add(link)
            out.append((img, link))
    return out


def from_arena(j: dict) -> list[tuple[str, str]]:
    out, page = [], 1
    while len(out) < j.get("max", 30):
        d = json.loads(get(f"https://api.are.na/v2/channels/{j['channel']}/contents?per=50&page={page}&direction=desc"))
        blocks = d.get("contents", [])
        if not blocks:
            break
        for b in blocks:
            u = (b.get("image") or {}).get("display", {}).get("url")
            if u:
                out.append((u, f"https://www.are.na/block/{b['id']}"))
        page += 1
    return out


def _nuxt(html_text: str):
    """Nuxt 페이지의 __NUXT_DATA__(번호로 서로 가리키는 목록)를 보통 JSON으로 풀기."""
    data = json.loads(re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html_text, re.S).group(1))
    wrap = {"ShallowReactive", "Reactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef"}

    def r(i, depth=0):
        if depth > 40:
            return None
        v = data[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in wrap:
                return r(v[1], depth + 1)
            return [r(x, depth + 1) if isinstance(x, int) else x for x in v]
        if isinstance(v, dict):
            return {k: r(x, depth + 1) if isinstance(x, int) else x for k, x in v.items()}
        return v
    return r(0)


def from_kream(j: dict) -> list[tuple[str, str]]:
    """KREAM 스타일 태그 페이지(예: https://kream.co.kr/social/tags/어텀룩)의 첫 게시물 20개.
    robots.txt는 모든 수집기 허용(/my·/history·/bridge 제외)이지만 서버가 브라우저가 아닌 이름엔 오류(500)를 줘서 브라우저 이름으로 접속.
    사람이 찍힌 게시물(is_human_detected)만, 게시물의 첫 사진만."""
    url = j["url"]
    if "/social/tags/" in url:
        head, tag = url.split("/social/tags/", 1)
        url = f"{head}/social/tags/{urllib.parse.quote(urllib.parse.unquote(tag))}"
    root = _nuxt(get(url).decode("utf-8", "ignore"))
    items = (((root.get("pinia") or {}).get("social") or {}).get("tagFeeds") or {}).get("items") or []
    out = []
    for it in items:
        p = it.get("social_post") or {}
        imgs = p.get("images") or []
        if not imgs or p.get("is_human_detected") is False:
            continue
        img = imgs[0].get("secure_url") or imgs[0].get("url")
        tags = [((t.get("product") or {}).get("release") or {}).get("name") for t in imgs[0].get("product_tags") or []]
        user = (p.get("social_user") or {}).get("nickname") or (p.get("social_user") or {}).get("user_name") or ""
        KREAM_NOTE[f"https://kream.co.kr/social/posts/{p['id']}"] = {"user": user, "products": [t for t in tags if t]}
        out.append((img, f"https://kream.co.kr/social/posts/{p['id']}"))
    return out


KREAM_NOTE: dict[str, dict] = {}   # 게시물 주소 → 작성자·태그된 상품 (manifest에 같이 저장 → 설명 쓸 때 참고)
KINDS = {"page": from_page, "musinsa": from_musinsa, "arena": from_arena, "kream": from_kream}


def run(jobs_path: Path) -> None:
    from PIL import Image
    man = load_json(MANIFEST, {})
    OUT.mkdir(parents=True, exist_ok=True)
    for j in load_json(jobs_path, []):
        # 다른 job에서 이미 받은 사진은 건너뜀 (무신사는 주소가 달라도 같은 목록이 오는 경우가 있음)
        have = {(m["link"], m["img"].split("?")[0]) for m in man.values()}
        try:
            found = [f for f in KINDS[j.get("kind", "page")](j) if (f[1], f[0].split("?")[0]) not in have][: j.get("max", 30)]
        except Exception as e:
            print(f"{j['id']}: 실패 {e}")
            continue
        ua = CLAUDE_UA if j.get("kind") == "musinsa" else BROWSER_UA

        def dl(args):
            n, (img, link) = args
            name = f"{j['id']}_{n:02d}.jpg"
            path = OUT / name
            if not path.exists():
                try:
                    im = Image.open(io.BytesIO(get(sized(img), ua, link))).convert("RGB")
                except Exception as e:
                    print(f"  사진 받기 실패 {name}: {e}")
                    return None
                if min(im.size) < 250:
                    return None
                im.thumbnail((720, 720))
                im.save(path, quality=85)
            return name, img, link

        with ThreadPoolExecutor(8) as ex:
            got = [r for r in ex.map(dl, enumerate(found, 1)) if r]
        for name, img, link in got:
            man[name] = {"label": j["label"], "link": link, "img": img, "kind": j.get("kind", "page"), **KREAM_NOTE.get(link, {})}
        print(f"{j['id']}: 후보 {len(found)}개 중 {len(got)}장 받음 ({j['label']})")
    save_json(MANIFEST, man)


def sheet(prefixes: list[str]) -> None:
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    W, H, cols, per = 220, 300, 8, 32
    for p in prefixes:
        files = sorted(OUT.glob(f"{p}_*.jpg"))
        for s in range(0, len(files), per):
            chunk = files[s:s + per]
            rows = (len(chunk) + cols - 1) // cols
            canvas = Image.new("RGB", (cols * W, rows * H), "white")
            d = ImageDraw.Draw(canvas)
            for i, f in enumerate(chunk):
                im = Image.open(f)
                im.thumbnail((W - 6, H - 6))
                x, y = (i % cols) * W + 3, (i // cols) * H + 3
                canvas.paste(im, (x, y))
                d.rectangle([x, y, x + 12 * len(f.stem) + 6, y + 26], fill="yellow")
                d.text((x + 3, y + 1), f.stem, fill="black", font=font)
            out = OUT / "sheets" / f"{p}_{s // per + 1}.jpg"
            canvas.save(out, quality=80)
            print(out, len(chunk))


def arena_search(q: str) -> None:
    d = json.loads(get(f"https://api.are.na/v2/search/channels?q={urllib.parse.quote(q)}&per=20"))
    for c in d.get("channels", []):
        print(f"{c.get('slug')}\t{c.get('length')}개\t{c.get('title')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--jobs", type=Path)
    g.add_argument("--sheet", nargs="+")
    g.add_argument("--arena-search")
    a = ap.parse_args()
    if a.jobs:
        run(a.jobs)
    elif a.sheet:
        sheet(a.sheet)
    else:
        arena_search(a.arena_search)


if __name__ == "__main__":
    main()
