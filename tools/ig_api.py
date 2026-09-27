"""인스타그램 공식 API Tool — 감시 계정(data/ig_watchlist.json)의 최근 게시물을 가져와 Claude가 무드를 판정하게 돕는다.

공식 Instagram Graph API(페이스북 로그인 방식)의 Business Discovery만 씀:
- 공개 비즈니스·크리에이터 계정의 최근 게시물·사진 주소를 읽음. 개인 계정·저장됨 목록·비슷한 사진 검색은 API에 없음.
- 사장님 인스타 계정이 프로페셔널 계정 + 페이스북 페이지와 연결돼 있어야 함. 비용 0원. 호출 한도는 시간당 약 200회.
- 해시태그 검색은 Meta 앱 심사가 필요해서 쓰지 않음.

비밀 파일(~/.secrets/insta-research.env)에 쓰는 이름:
  META_APP_ID, META_APP_SECRET   Meta 개발자 앱 → 앱 설정 → 기본 설정
  IG_SHORT_TOKEN                 Graph API 탐색기에서 받은 짧은 토큰(사장님이 붙여 넣음). --setup이 쓰고 지움
  IG_USER_ID, IG_USERNAME        --setup이 찾아서 저장
  IG_ACCESS_TOKEN                --setup이 저장하는 페이지 토큰(만료 없음)
  IG_USER_TOKEN, IG_USER_TOKEN_EXPIRES   예비용 장기 사용자 토큰(약 60일)

사용법 (사진 처리에 Pillow 필요 → uv run -q --with pillow python ...):
  python tools/ig_api.py --setup                 짧은 토큰 → 오래가는 토큰으로 바꾸고 인스타 계정 id 찾기
  python tools/ig_api.py --check                 연결 확인 (토큰 상태 + 계정 하나 시험 조회)
  python tools/ig_api.py --fetch [--per 12] [--accounts a,b] [--all]
                                                 감시 계정 최근 게시물 → .tmp/ig_api/ (이미 본 게시물은 건너뜀, --all이면 전부)
  python tools/ig_api.py --sheet                 방금 가져온 사진 → .tmp/ig_api/sheet_N.jpg (번호 딱지, 32장씩)
  python tools/ig_api.py --pick .tmp/ig_api/picks.json   Claude가 고른 사진 → 리서치 보드 [AI추천] 탭 (tools/ai_picks.py로 합침)

picks.json 형식 (S-번호 = 판독 이미지의 딱지, 이름은 tools/trend_keywords.json 이름표만):
  {"S-012": {"summary": "한 줄 설명", "ref": "IG-0027", "gender": "남성",
             "items": [], "styles": [], "colors": [], "materials": [], "details": []}, ...}
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_picks  # noqa: E402
from common import DATA_DIR, KST, TMP_DIR, env_path, load_env, load_json, save_env, save_json, today_kst  # noqa: E402

GRAPH = "https://graph.facebook.com/v25.0"
WATCH_PATH = DATA_DIR / "ig_watchlist.json"
SEEN_PATH = DATA_DIR / "ig_seen.json"          # 이미 가져온 게시물 id → 가져온 날짜 (같은 사진 반복 방지)
WORK = TMP_DIR / "ig_api"
IMG_DIR = WORK / "img"
POSTS_PATH = WORK / "posts.json"               # 마지막 --fetch 결과 (사진 번호 S-001… 포함)
MEDIA_FIELDS = "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,children{media_type,media_url,thumbnail_url}"
RATE_LIMIT_CODES = {4, 17, 32, 613}


class GraphError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


def graph(path: str, params: dict) -> dict:
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error", {})
        except Exception:
            err = {}
        raise GraphError(int(err.get("code", e.code)), err.get("message", str(e))) from None


def need(*keys: str) -> dict[str, str]:
    load_env()
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"비밀 파일({env_path()})에 값이 없음: {', '.join(missing)}\n"
                 f"→ workflows/ig_api_reference.md '처음 한 번 연결' 순서대로 채운 뒤 다시 실행")
    return {k: os.environ[k] for k in keys}


# ---------- 연결 ----------

def setup() -> None:
    env = need("META_APP_ID", "META_APP_SECRET", "IG_SHORT_TOKEN")
    try:
        long = graph("oauth/access_token", {
            "grant_type": "fb_exchange_token", "client_id": env["META_APP_ID"],
            "client_secret": env["META_APP_SECRET"], "fb_exchange_token": env["IG_SHORT_TOKEN"]})
    except GraphError as e:
        sys.exit(f"토큰 바꾸기 실패 {e}\n→ 짧은 토큰은 약 1시간이면 만료됨. 탐색기에서 새로 받아 IG_SHORT_TOKEN에 다시 넣기. "
                 f"앱 ID·시크릿이 같은 앱 것인지도 확인")
    user_token = long["access_token"]
    expires = long.get("expires_in")
    expires_on = datetime.fromtimestamp(time.time() + expires, KST).strftime("%Y-%m-%d") if expires else ""

    pages = graph("me/accounts", {"fields": "name,access_token,instagram_business_account{id,username}",
                                  "access_token": user_token}).get("data", [])
    linked = [p for p in pages if p.get("instagram_business_account")]
    if not linked:
        names = ", ".join(p.get("name", "?") for p in pages) or "없음"
        sys.exit(f"인스타 프로페셔널 계정이 연결된 페이스북 페이지를 못 찾음 (보이는 페이지: {names})\n"
                 f"→ 인스타를 프로페셔널 계정으로 바꾸고 페이스북 페이지와 연결했는지, 토큰 받을 때 그 페이지를 체크했는지 확인")
    page = linked[0]
    ig = page["instagram_business_account"]
    save_env({"IG_USER_ID": ig["id"], "IG_USERNAME": ig.get("username", ""),
              "IG_ACCESS_TOKEN": page["access_token"], "IG_USER_TOKEN": user_token,
              "IG_USER_TOKEN_EXPIRES": expires_on, "IG_SHORT_TOKEN": None})
    print(f"연결 완료: 인스타 @{ig.get('username', '?')} (페이지: {page.get('name', '?')})")
    print(f"페이지 토큰 저장(만료 없음). 예비 사용자 토큰 만료일: {expires_on or '없음'}")
    if len(linked) > 1:
        print(f"참고: 연결된 페이지가 {len(linked)}개 — 첫 번째를 씀")


def discover(username: str, per: int, token_keys=("IG_ACCESS_TOKEN", "IG_USER_TOKEN")) -> dict:
    """username의 프로필 + 최근 per개 게시물. 페이지 토큰이 안 되면 예비 사용자 토큰으로 한 번 더."""
    load_env()
    fields = f"business_discovery.username({username}){{username,name,followers_count,media_count,media.limit({per}){{{MEDIA_FIELDS}}}}}"
    last = None
    for key in token_keys:
        token = os.environ.get(key)
        if not token:
            continue
        try:
            return graph(os.environ["IG_USER_ID"], {"fields": fields, "access_token": token})["business_discovery"]
        except GraphError as e:
            last = e
            if e.code in RATE_LIMIT_CODES or e.code != 190:   # 190 = 토큰 문제 → 다음 토큰으로
                raise
    raise last or GraphError(0, "쓸 수 있는 토큰이 없음")


def check() -> None:
    env = need("IG_USER_ID", "IG_ACCESS_TOKEN")
    me = graph(env["IG_USER_ID"], {"fields": "username,account_type", "access_token": env["IG_ACCESS_TOKEN"]})
    print(f"토큰 정상: @{me.get('username')} ({me.get('account_type', '?')})")
    exp = os.environ.get("IG_USER_TOKEN_EXPIRES")
    if exp:
        print(f"예비 사용자 토큰 만료일: {exp}")
    watch = load_json(WATCH_PATH, {"accounts": []})["accounts"]
    test = watch[0]["username"] if watch else "carharttwip"
    try:
        bd = discover(test, 1)
        print(f"시험 조회 성공: @{bd['username']} 게시물 {bd.get('media_count', '?')}개")
    except GraphError as e:
        print(f"시험 조회 실패(@{test}): {e}")


# ---------- 가져오기 ----------

def _images(post: dict) -> list[str]:
    """게시물의 사진 주소들. 여러 장이면 장마다, 영상이면 표지 사진."""
    items = post.get("children", {}).get("data") or [post]
    out = []
    for it in items:
        url = it.get("thumbnail_url") if it.get("media_type") == "VIDEO" else it.get("media_url")
        if url:
            out.append(url)
    return out


def _download(args) -> str | None:
    from PIL import Image
    url, path = args
    if path.exists():
        return path.name
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGB")
        im.thumbnail((720, 720))
        im.save(path, quality=85)
        return path.name
    except Exception as e:
        print(f"  사진 받기 실패 {path.name}: {e}")
        return None


def fetch(per: int, only: list[str] | None, include_seen: bool) -> None:
    need("IG_USER_ID", "IG_ACCESS_TOKEN")
    watch = load_json(WATCH_PATH, {"accounts": []})
    accounts = [a for a in watch["accounts"] if not only or a["username"] in only]
    seen = load_json(SEEN_PATH, {})
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    posts, jobs, fails = [], [], []
    for n, acc in enumerate(accounts, 1):
        user = acc["username"]
        try:
            bd = discover(user, per)
        except GraphError as e:
            if e.code in RATE_LIMIT_CODES:
                print(f"호출 한도에 걸림 — 여기서 멈춤 ({n - 1}/{len(accounts)}곳 완료). 1시간 뒤 --accounts로 나머지만 다시")
                break
            acc["status"] = f"실패 {today_kst()}: {e}"
            fails.append(user)
            continue
        acc["status"] = f"정상 {today_kst()}"
        acc["followers"] = bd.get("followers_count")
        for p in bd.get("media", {}).get("data", []):
            if p["id"] in seen and not include_seen:
                continue
            files = []
            for k, url in enumerate(_images(p), 1):
                path = IMG_DIR / f"{user}_{p['id']}_{k}.jpg"
                jobs.append((url, path))
                files.append(path.name)
            posts.append({"username": user, "id": p["id"], "permalink": p.get("permalink"),
                          "timestamp": p.get("timestamp"), "caption": (p.get("caption") or "")[:300], "files": files})
        print(f"[{n}/{len(accounts)}] @{user} 새 게시물 {sum(1 for x in posts if x['username'] == user)}개")
    with ThreadPoolExecutor(8) as ex:
        ok = set(filter(None, ex.map(_download, jobs)))
    # 사진 번호 S-001… (판독 이미지 딱지와 같음)
    shots, i = [], 0
    for p in posts:
        for f in p["files"]:
            if f in ok:
                i += 1
                shots.append({"code": f"S-{i:03d}", "file": f, **{k: p[k] for k in ("username", "id", "permalink", "timestamp", "caption")}})
        seen[p["id"]] = today_kst()
    save_json(POSTS_PATH, {"fetched": today_kst(), "shots": shots})
    save_json(SEEN_PATH, seen)
    save_json(WATCH_PATH, watch)
    print(f"완료: 게시물 {len(posts)}개, 사진 {len(shots)}장 → {IMG_DIR}")
    if fails:
        print(f"못 가져온 계정 {len(fails)}곳 (개인 계정이거나 아이디가 틀림): {', '.join('@' + f for f in fails)}")


# ---------- 판독 이미지 ----------

def sheet() -> None:
    from PIL import Image, ImageDraw, ImageFont
    shots = load_json(POSTS_PATH, {"shots": []})["shots"]
    if not shots:
        sys.exit("가져온 사진이 없음 → 먼저 --fetch")
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    W, H, cols, per_sheet = 220, 300, 8, 32
    for old in WORK.glob("sheet_*.jpg"):
        old.unlink()
    for s in range(0, len(shots), per_sheet):
        chunk = shots[s:s + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        canvas = Image.new("RGB", (cols * W, rows * H), "white")
        d = ImageDraw.Draw(canvas)
        for i, sh in enumerate(chunk):
            im = Image.open(IMG_DIR / sh["file"])
            im.thumbnail((W - 6, H - 30))
            x, y = (i % cols) * W + 3, (i // cols) * H + 27
            canvas.paste(im, (x, y))
            label = f"{sh['code']} @{sh['username']}"[:22]
            d.rectangle([x, y - 25, x + W - 6, y - 1], fill="yellow")
            d.text((x + 3, y - 24), label, fill="black", font=font)
        out = WORK / f"sheet_{s // per_sheet + 1}.jpg"
        canvas.save(out, quality=82)
        print(out)


# ---------- 고른 사진 ----------

def pick(path: Path) -> None:
    """고른 S-번호를 ai_picks 형식으로 바꿔 AI추천 탭에 합침 (검사는 ai_picks.add가 함)."""
    picks = load_json(path, {})
    shots = {sh["code"]: sh for sh in load_json(POSTS_PATH, {"shots": []})["shots"]}
    missing = [c for c in picks if c not in shots]
    if missing:
        sys.exit(f"이번 --fetch에 없는 번호라 아무것도 안 합침: {', '.join(missing)}")
    entries = [{"image": str(IMG_DIR / shots[c]["file"]), "via": "인스타", "source": "@" + shots[c]["username"],
                "link": shots[c]["permalink"] or f"https://www.instagram.com/{shots[c]['username']}/", **v}
               for c, v in picks.items()]
    tmp = WORK / "ai_add.json"
    save_json(tmp, entries)
    ai_picks.add(tmp)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--setup", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--fetch", action="store_true")
    g.add_argument("--sheet", action="store_true")
    g.add_argument("--pick", type=Path)
    ap.add_argument("--per", type=int, default=12, help="계정당 최근 게시물 수 (기본 12)")
    ap.add_argument("--accounts", help="쉼표로 구분한 아이디만 (@ 없이)")
    ap.add_argument("--all", action="store_true", help="이미 본 게시물도 다시 가져오기")
    a = ap.parse_args()
    if a.setup:
        setup()
    elif a.check:
        check()
    elif a.fetch:
        fetch(a.per, [x.strip().lstrip("@") for x in a.accounts.split(",")] if a.accounts else None, a.all)
    elif a.sheet:
        sheet()
    elif a.pick:
        pick(a.pick)


if __name__ == "__main__":
    main()
