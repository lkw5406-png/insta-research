"""스크린샷 판정 도우미 Tool — inbox/의 새 스크린샷만 골라 Claude가 볼 판독용 이미지를 만들고,
Claude가 쓴 판정(패션 여부·출처 계정·자르기 범위·키워드)을 검사한 뒤 사진을 잘라 photos/에 저장한다.

- 파일 내용으로 구분(같은 파일을 두 번 넣어도 한 번만). 거의 같은 스크린샷(같은 게시물을 두 번 캡처)은 자동으로 '중복' 처리.
- 판독용 이미지: 세로(폰) 캡처는 3장씩 나란히 + 왼쪽 눈금, 가로(PC) 캡처는 1장씩 크게 + 위·왼쪽 눈금
  (0~10 = 0%~100%) → 자르기 범위를 비율로 적기 쉽게.
- 목록(board)은 넣은 폴더로 정해짐: inbox/인스타그램, inbox/핀터레스트, inbox/런웨이 (inbox 바로 아래 파일은 인스타그램으로 봄).
- 출처(source) 규칙 — 화면에 안 보이면 "확인 불가" + source_note에 이유. 추측으로 채우지 않음.
  인스타그램: 게시물 맨 위 계정 "@아이디" / 핀터레스트: 핀을 올린 계정 "@아이디" (+ 원래 사이트가 보이면 origin에 "musinsa.com" 등)
    PC 핀 상세 화면은 아이디 대신 표시 이름만 보임 → 보이는 이름 그대로 "Yulia Korma" (@ 없이 = 프로필 링크 없이 이름만 표시).
    PC 핀 상세 화면 캡처는 왼쪽 큰 사진만 사장님 핀. 오른쪽·아래 작은 사진은 핀터레스트 추천이라 자르지 않음.
  런웨이: "브랜드 시즌" (예: "Prada 2027SS", "Lemaire 2026FW") + 캡처한 사이트가 보이면 origin (예: "vogue.com")

판정 파일 형식(.tmp/batchN.json):
  {"파일id": {"fashion": true, "source": "@아이디", "origin": "(선택)", "crop": [x1, y1, x2, y2],   # 0~1 비율. 여러 장이면 [[...], [...]]
             "gender": "여성|남성|공용", "summary": "한 줄 설명",
             "items": [], "styles": [], "details": [], "colors": [], "materials": []},
   "파일id2": {"fashion": false}}
  이름은 tools/trend_keywords.json 이름표만.

사용법 (사진 처리에 Pillow 필요 → uv run --with pillow python ...):
  python tools/inbox_queue.py --next [--size 30]    새 스크린샷 → .tmp/queue.json + .tmp/sheet_N.jpg
  python tools/inbox_queue.py --merge .tmp/batchN.json   검사 후 합치기 + 사진 자르기
  python tools/inbox_queue.py --check [--review 12]     남은 개수 (+ 최근 자른 사진 모음 .tmp/review.jpg)
  python tools/inbox_queue.py --codes                    번호 없는 판정에 번호 붙이기 (--merge 때 자동. 손으로 고친 뒤 다시 맞출 때)

사진 번호 (2026-09-27 사장님 요청: 사이트 사진과 inbox 파일을 찾기 쉽게 같은 이름으로):
  목록별 번호 IG-0001 / PT-0001 / RW-0001. 합칠 때 자동으로
  inbox 파일 → "IG-0001_출처.png", 잘라 낸 사진 → photos/…/IG-0001.jpg (한 캡처에 여러 장이면 IG-0001_2.jpg),
  사이트 공개본 → docs/img/IG-0001.jpg. 사이트 카드·크게 보기에 번호가 보임. 같은 사진 중복 캡처는 "IG-0001_중복_xxxx.png".
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARDS, IMAGE_EXT, INBOX_DIR, LABELS_PATH, PHOTOS_DIR, ROOT, TMP_DIR, VOCAB_PATH, load_json, save_json, today_kst

QUEUE_PATH = TMP_DIR / "queue.json"
PER_SHEET = 3          # 세로(폰) 캡처는 판독용 이미지 한 장에 3장, 가로(PC) 캡처는 1장씩 크게
CELL_W, CELL_H_MAX = 620, 1340
WIDE_W = 1600          # 가로 캡처 판독용 폭 (계정 이름 글씨가 읽히는 크기)
GUTTER = 34            # 눈금 폭
DUP_DIFF = 1.0         # 축소 흑백 사진의 평균 밝기 차이가 이 미만이면 같은 사진을 다시 캡처한 것으로 봄.
                       # (2026-09-27: 4.0이었는데 같은 게시물의 다른 컷(흰 배경 룩북)이 2~3으로 나와 중복 처리됨 → 1.0)
PHOTO_MAX = 1080       # 잘라 낸 사진 긴 변 최대(px)
LIST_FIELDS = ["items", "styles", "details", "colors", "materials"]


def file_id(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def open_image(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def fingerprint(img: Image.Image) -> str:
    """축소 흑백 지문(48x27, 세로면 27x48). 처음엔 9x16 모양 지문을 썼는데, PC 캡처는 어두운 배경·메뉴가 같아서
    다른 게시물도 같다고 판정함(2026-09-27) → 픽셀 밝기를 직접 비교하는 방식으로 바꿈."""
    size = (48, 27) if img.width >= img.height else (27, 48)
    return img.convert("L").resize(size, Image.BILINEAR).tobytes().hex()


def same_post(a: str, b: str) -> bool:
    if len(a) != len(b) or len(a) < 100:  # 크기가 다르거나 옛 형식 지문이면 비교 안 함
        return False
    x, y = bytes.fromhex(a), bytes.fromhex(b)
    return sum(abs(i - j) for i, j in zip(x, y)) / len(x) < DUP_DIFF


def board_of(path: Path) -> str:
    """inbox/<폴더>/... 의 첫 폴더 이름으로 목록을 정함. 모르는 폴더·inbox 바로 아래는 인스타그램."""
    parts = path.relative_to(INBOX_DIR).parts
    name = parts[0] if len(parts) > 1 else ""
    return next((k for k, b in BOARDS.items() if name in (b["folder"], k)), "instagram")


def inbox_files() -> list[Path]:
    return sorted((p for p in INBOX_DIR.rglob("*") if p.suffix.lower() in IMAGE_EXT and p.is_file()),
                  key=lambda p: p.stat().st_mtime)


def font(size: int):
    for name in ("malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def vocab() -> dict:
    v = load_json(VOCAB_PATH, {})
    flat = lambda x: {i for g in x.values() for i in g} if isinstance(x, dict) else set(x)
    return {"gender": set(v["gender"]), **{f: flat(v[f]) for f in LIST_FIELDS}}


# ---------- --next ----------
def cmd_next(size: int) -> None:
    labels = load_json(LABELS_PATH, {})
    known = [(l["hash"], i) for i, l in labels.items() if l.get("hash") and "dup_of" not in l]
    queue, dups, seen = [], 0, set()
    for p in inbox_files():
        fid = file_id(p)
        if fid in labels or fid in seen:
            continue
        seen.add(fid)
        img = open_image(p)
        h = fingerprint(img)
        twin = next((i for k, i in known if same_post(k, h)), None)
        if twin:
            labels[fid] = {"dup_of": twin, "file": p.name, "added": today_kst(), "hash": h}
            dups += 1
            continue
        known.append((h, fid))
        if len(queue) < size:
            queue.append({"id": fid, "file": str(p.relative_to(ROOT)), "board": board_of(p), "w": img.width, "h": img.height, "hash": h})
    if dups:
        save_json(LABELS_PATH, labels)
    for old in TMP_DIR.glob("sheet_*.jpg"):
        old.unlink()
    n_sheet, tall = 0, []
    for k, q in enumerate(queue):
        q["n"] = k + 1
        if q["w"] > q["h"]:
            n_sheet += 1
            q["sheet"] = n_sheet
            make_wide_sheet(q, n_sheet)
        else:
            tall.append(q)
    for s in range(0, len(tall), PER_SHEET):
        n_sheet += 1
        for q in tall[s:s + PER_SHEET]:
            q["sheet"] = n_sheet
        make_sheet(tall[s:s + PER_SHEET], n_sheet)
    save_json(QUEUE_PATH, queue)
    pending = sum(1 for p in inbox_files() if file_id(p) not in labels) - len(queue)
    print(f"새 스크린샷 {len(queue)}장 → .tmp/queue.json, 판독용 이미지 {n_sheet}장 (.tmp/sheet_N.jpg)"
          + (f", 중복 {dups}장 자동 처리" if dups else "") + (f", 다음 묶음에 남은 것 {pending}장" if pending > 0 else ""))
    for q in queue:
        print(f"  #{q['n']} sheet_{q['sheet']}  {q['id']}  {q['file']}  ({q['w']}x{q['h']})")


RED = (255, 0, 80)


def make_wide_sheet(q: dict, sheet_no: int) -> None:
    """가로(PC) 캡처 1장: 위쪽 눈금(가로 0~10)과 왼쪽 눈금(세로 0~10), 10% 격자."""
    img = open_image(ROOT / q["file"])
    scale = WIDE_W / img.width
    c = img.resize((WIDE_W, round(img.height * scale)), Image.LANCZOS)
    head = 40 + 22
    sheet = Image.new("RGB", (GUTTER + c.width + 8, head + c.height + 8), "white")
    sheet.paste(c, (GUTTER, head))
    d = ImageDraw.Draw(sheet, "RGBA")
    f_big, f_small = font(24), font(15)
    d.text((6, 6), f"#{q['n']}  {q['id']}  [{BOARDS[q['board']]['name']}]  ({Path(q['file']).name})", fill="black", font=f_big)
    for t in range(11):
        x = GUTTER + round(c.width * t / 10)
        y = head + round(c.height * t / 10)
        d.line([(x, head - 8), (x, head + c.height)], fill=(255, 0, 80, 150), width=1)
        d.line([(GUTTER - 8, y), (GUTTER + c.width, y)], fill=(255, 0, 80, 150), width=1)
        d.text((min(x - 4, GUTTER + c.width - 20), head - 24), str(t), fill=RED, font=f_small)
        d.text((4, max(head, y - 9)), str(t), fill=RED, font=f_small)
    sheet.save(TMP_DIR / f"sheet_{sheet_no}.jpg", quality=88)


def make_sheet(items: list[dict], sheet_no: int) -> None:
    """세로(폰) 캡처 3장 나란히, 왼쪽 눈금(0=맨 위, 10=맨 아래)."""
    cells = []
    for q in items:
        img = open_image(ROOT / q["file"])
        scale = min(CELL_W / img.width, CELL_H_MAX / img.height)
        cells.append(img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS))
    head = 40
    H = max(c.height for c in cells) + head
    sheet = Image.new("RGB", ((GUTTER + CELL_W + 16) * len(cells), H), "white")
    d = ImageDraw.Draw(sheet)
    f_big, f_small = font(24), font(15)
    for k, (q, c) in enumerate(zip(items, cells)):
        x0 = k * (GUTTER + CELL_W + 16)
        d.text((x0 + 4, 6), f"#{q['n']}  {q['id']}  [{BOARDS[q['board']]['name']}]", fill="black", font=f_big)
        sheet.paste(c, (x0 + GUTTER, head))
        for t in range(11):
            y = head + round(c.height * t / 10)
            d.line([(x0 + GUTTER - 10, y), (x0 + GUTTER + c.width, y)], fill=RED, width=1)
            d.text((x0 + 2, max(head, y - 9)), str(t), fill=RED, font=f_small)
        x = x0 + GUTTER + round(c.width / 2)  # 가로 가운데 표시
        d.line([(x, head), (x, head + 12)], fill=RED, width=2)
    sheet.save(TMP_DIR / f"sheet_{sheet_no}.jpg", quality=88)


# ---------- --merge ----------
def boxes(crop) -> list[list[float]]:
    if not isinstance(crop, list) or not crop:
        raise ValueError("crop 없음")
    bs = crop if isinstance(crop[0], list) else [crop]
    for b in bs:
        if len(b) != 4 or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in b) or b[2] <= b[0] or b[3] <= b[1]:
            raise ValueError(f"crop 형식 오류 {b} (0~1 비율 [왼쪽, 위, 오른쪽, 아래])")
    return bs


def validate(lab: dict, v: dict, board: str = "instagram") -> list[str]:
    if not isinstance(lab.get("fashion"), bool):
        return ["fashion 은 true/false"]
    if not lab["fashion"]:
        return []
    errs = []
    src = lab.get("source", "")
    if board == "runway":
        if not (isinstance(src, str) and len(src.strip()) >= 3):
            errs.append('런웨이 source 는 "브랜드 시즌"(예: "Prada 2027SS") 또는 "확인 불가"')
    elif board == "pinterest":
        # 핀 상세 화면(PC)에는 아이디 대신 표시 이름만 보임 → 보이는 이름 그대로 (2026-09-27)
        if not (isinstance(src, str) and src.strip() and src != "@"):
            errs.append('핀터레스트 source 는 "@아이디", 보이는 표시 이름(예: "Yulia Korma") 또는 "확인 불가"')
    elif not (isinstance(src, str) and (src.startswith("@") and len(src) > 1 or src == "확인 불가")):
        errs.append('source 는 "@아이디" 또는 "확인 불가"')
    if src == "확인 불가" and not lab.get("source_note"):
        errs.append("출처 확인 불가면 source_note에 이유")
    try:
        boxes(lab.get("crop"))
    except ValueError as e:
        errs.append(str(e))
    if lab.get("gender") not in v["gender"]:
        errs.append(f"gender '{lab.get('gender')}'")
    if len(lab.get("summary", "")) < 5:
        errs.append("summary 5자 이상")
    for f in LIST_FIELDS:
        bad = [x for x in lab.get(f, []) if x not in v[f]]
        if bad:
            errs.append(f"{f} 이름표 밖: {bad}")
    return errs


def cmd_merge(path: str) -> int:
    batch = load_json(Path(path), {})
    queue = {q["id"]: q for q in load_json(QUEUE_PATH, [])}
    labels, v = load_json(LABELS_PATH, {}), vocab()
    problems = {fid: (["큐에 없는 id"] if fid not in queue else validate(lab, v, queue[fid].get("board", "instagram")))
                for fid, lab in batch.items()}
    problems = {k: e for k, e in problems.items() if e}
    if problems:
        for fid, e in problems.items():
            print(f"  {fid}: {'; '.join(e)}")
        print(f"문제 {len(problems)}개 — 고친 뒤 다시 합치세요 (아무것도 합치지 않음)")
        return 1
    today, n_photo = today_kst(), 0
    for fid, lab in batch.items():
        q = queue[fid]
        rec = {**lab, "board": q.get("board", "instagram"), "file": Path(q["file"]).name, "added": today, "hash": q["hash"]}
        if lab["fashion"]:
            img = open_image(ROOT / q["file"])
            out = []
            for k, (x1, y1, x2, y2) in enumerate(boxes(lab["crop"])):
                piece = img.crop((round(x1 * img.width), round(y1 * img.height), round(x2 * img.width), round(y2 * img.height)))
                piece.thumbnail((PHOTO_MAX, PHOTO_MAX), Image.LANCZOS)
                rel = Path("photos") / today[:7] / f"{fid}{'' if k == 0 else f'_{k + 1}'}.jpg"
                (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
                piece.save(ROOT / rel, quality=88)
                out.append(rel.as_posix())
            rec["photos"] = out
            n_photo += len(out)
        labels[fid] = rec
    save_json(LABELS_PATH, labels)
    assign_codes()
    fashion = sum(1 for l in batch.values() if l["fashion"])
    print(f"합침: {len(batch)}장 (패션 {fashion}장 → 사진 {n_photo}개 저장, 패션 아님 {len(batch) - fashion}장)")
    return 0


# ---------- 번호 붙이기 ----------
def safe_name(text: str) -> str:
    t = re.sub(r'[\\/:*?"<>|\s]+', "_", (text or "").lstrip("@")).strip("._")
    return t[:40] or "출처확인불가"


def rename(src: Path, dst: Path) -> Path:
    if src == dst or not src.exists():
        return src
    if dst.exists():  # 이미 같은 이름이 있으면 건드리지 않음
        print(f"  이름 겹침 — 그대로 둠: {src.name} → {dst.name}")
        return src
    src.rename(dst)
    return dst


def assign_codes() -> int:
    """번호 없는 판정에 목록별 다음 번호를 붙이고, inbox 파일·잘라 낸 사진 이름을 번호로 바꿈 (여러 번 돌려도 안전)."""
    labels = load_json(LABELS_PATH, {})
    paths = {file_id(p): p for p in inbox_files()}
    order = {fid: k for k, fid in enumerate(paths)}  # 파일 넣은 순서
    used: dict[str, int] = {}
    for l in labels.values():
        m = re.fullmatch(r"([A-Z]{2})-(\d+)", l.get("code", ""))
        if m:
            used[m[1]] = max(used.get(m[1], 0), int(m[2]))
    todo = sorted((fid for fid, l in labels.items() if "code" not in l and "dup_of" not in l),
                  key=lambda f: (labels[f].get("added", ""), order.get(f, 10**9)))
    for fid in todo:
        l = labels[fid]
        pre = BOARDS[l.get("board", "instagram")]["prefix"]
        used[pre] = used.get(pre, 0) + 1
        code = l["code"] = f"{pre}-{used[pre]:04d}"
        if fid in paths:
            p = paths[fid]
            label = ("출처확인불가" if l.get("source") == "확인 불가" else l.get("source", "")) if l.get("fashion") else "패션아님"
            l["file"] = rename(p, p.with_name(f"{code}_{safe_name(label)}{p.suffix.lower()}")).name
        new_photos = []
        for k, ph in enumerate(l.get("photos", [])):
            old = ROOT / ph
            new = old.with_name(f"{code}{'' if k == 0 else f'_{k + 1}'}.jpg")
            new_photos.append(rename(old, new).relative_to(ROOT).as_posix())
        if new_photos:
            l["photos"] = new_photos
    for fid, l in labels.items():  # 중복 캡처는 원본 번호를 따라감
        twin = labels.get(l.get("dup_of", ""), {})
        if twin.get("code") and fid in paths and not paths[fid].name.startswith(twin["code"]):
            p = paths[fid]
            l["file"] = rename(p, p.with_name(f"{twin['code']}_중복_{fid[:4]}{p.suffix.lower()}")).name
    save_json(LABELS_PATH, labels)
    if todo:
        print(f"번호 붙임: {len(todo)}장 ({todo and labels[todo[0]]['code']} ~ {todo and labels[todo[-1]]['code']})")
    return len(todo)


# ---------- --check ----------
def cmd_check(review: int) -> None:
    labels = load_json(LABELS_PATH, {})
    files = inbox_files()
    pending = [p for p in files if file_id(p) not in labels]
    fashion = [l for l in labels.values() if l.get("fashion")]
    unknown = sum(1 for l in fashion if l.get("source") == "확인 불가")
    print(f"inbox 스크린샷 {len(files)}장 / 판정 {len(labels)}장 (패션 {len(fashion)}장, 중복 {sum(1 for l in labels.values() if 'dup_of' in l)}장, "
          f"출처 확인 불가 {unknown}장) / 남은 것 {len(pending)}장")
    if review and fashion:
        recent = sorted(fashion, key=lambda l: l["added"])[-review:]
        paths = [ROOT / p for l in recent for p in l.get("photos", [])][-review:]
        thumbs = []
        for p in paths:
            im = open_image(p)
            im.thumbnail((360, 480))
            thumbs.append(im)
        cols = 4
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 370, rows * 490), "white")
        for k, im in enumerate(thumbs):
            sheet.paste(im, ((k % cols) * 370 + 5, (k // cols) * 490 + 5))
        sheet.save(TMP_DIR / "review.jpg", quality=85)
        print(f"최근 자른 사진 {len(thumbs)}개 → .tmp/review.jpg (잘 잘렸는지 눈으로 확인)")


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--next", action="store_true")
    g.add_argument("--merge")
    g.add_argument("--check", action="store_true")
    g.add_argument("--codes", action="store_true")
    ap.add_argument("--size", type=int, default=30)
    ap.add_argument("--review", type=int, default=0)
    a = ap.parse_args()
    TMP_DIR.mkdir(exist_ok=True)
    INBOX_DIR.mkdir(exist_ok=True)
    for b in BOARDS.values():
        (INBOX_DIR / b["folder"]).mkdir(exist_ok=True)
    PHOTOS_DIR.mkdir(exist_ok=True)
    if a.next:
        cmd_next(a.size)
    elif a.merge:
        return cmd_merge(a.merge)
    elif a.codes:
        n = assign_codes()
        print(f"번호 없는 판정 {n}장 처리")
    else:
        cmd_check(a.review)
    return 0


if __name__ == "__main__":
    sys.exit(main())
