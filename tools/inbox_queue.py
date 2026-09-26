"""스크린샷 판정 도우미 Tool — inbox/의 새 스크린샷만 골라 Claude가 볼 판독용 이미지를 만들고,
Claude가 쓴 판정(패션 여부·출처 계정·자르기 범위·키워드)을 검사한 뒤 사진을 잘라 photos/에 저장한다.

- 파일 내용으로 구분(같은 파일을 두 번 넣어도 한 번만). 거의 같은 스크린샷(같은 게시물을 두 번 캡처)은 자동으로 '중복' 처리.
- 판독용 이미지: 스크린샷 3장씩 나란히 + 왼쪽 눈금(0~10 = 위에서부터 0%~100%) → 자르기 범위를 비율로 적기 쉽게.
- 출처는 게시물 맨 위 계정 이름을 그대로(@아이디). 화면에 안 보이면 "확인 불가" 라고 적고 source_note에 이유.

판정 파일 형식(.tmp/batchN.json):
  {"파일id": {"fashion": true, "source": "@아이디", "crop": [x1, y1, x2, y2],   # 0~1 비율. 사진 여러 장이면 [[...], [...]]
             "gender": "여성|남성|공용", "summary": "한 줄 설명",
             "items": [], "styles": [], "details": [], "colors": [], "materials": []},
   "파일id2": {"fashion": false}}
  이름은 tools/trend_keywords.json 이름표만.

사용법 (사진 처리에 Pillow 필요 → uv run --with pillow python ...):
  python tools/inbox_queue.py --next [--size 30]    새 스크린샷 → .tmp/queue.json + .tmp/sheet_N.jpg
  python tools/inbox_queue.py --merge .tmp/batchN.json   검사 후 합치기 + 사진 자르기
  python tools/inbox_queue.py --check [--review 12]     남은 개수 (+ 최근 자른 사진 모음 .tmp/review.jpg)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGE_EXT, INBOX_DIR, LABELS_PATH, PHOTOS_DIR, ROOT, TMP_DIR, VOCAB_PATH, load_json, save_json, today_kst

QUEUE_PATH = TMP_DIR / "queue.json"
PER_SHEET = 3          # 판독용 이미지 한 장에 스크린샷 3장 (계정 이름 글씨가 읽히는 크기)
CELL_W, CELL_H_MAX = 620, 1340
GUTTER = 34            # 왼쪽 눈금 폭
DUP_DISTANCE = 5       # 모양 지문 차이가 이 이하면 같은 게시물로 봄
PHOTO_MAX = 1080       # 잘라 낸 사진 긴 변 최대(px)
LIST_FIELDS = ["items", "styles", "details", "colors", "materials"]


def file_id(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def open_image(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def dhash(img: Image.Image) -> int:
    """모양 지문 — 상태표시줄 시간처럼 작은 차이는 무시하고 사진 내용이 같으면 비슷한 값."""
    g = img.convert("L").resize((9, 16), Image.LANCZOS)
    px = list(g.tobytes())
    bits = 0
    for r in range(16):
        for c in range(8):
            bits = (bits << 1) | (px[r * 9 + c] > px[r * 9 + c + 1])
    return bits


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
    known = {int(l["hash"], 16): i for i, l in labels.items() if l.get("hash")}
    queue, dups, seen = [], 0, set()
    for p in inbox_files():
        fid = file_id(p)
        if fid in labels or fid in seen:
            continue
        seen.add(fid)
        img = open_image(p)
        h = dhash(img)
        twin = next((i for k, i in known.items() if bin(k ^ h).count("1") <= DUP_DISTANCE), None)
        if twin:
            labels[fid] = {"dup_of": twin, "file": p.name, "added": today_kst(), "hash": f"{h:016x}"}
            dups += 1
            continue
        known[h] = fid
        if len(queue) < size:
            queue.append({"id": fid, "file": str(p.relative_to(ROOT)), "w": img.width, "h": img.height, "hash": f"{h:016x}"})
    if dups:
        save_json(LABELS_PATH, labels)
    for old in TMP_DIR.glob("sheet_*.jpg"):
        old.unlink()
    for s in range(0, len(queue), PER_SHEET):
        make_sheet(queue[s:s + PER_SHEET], s // PER_SHEET + 1, s)
    save_json(QUEUE_PATH, queue)
    pending = sum(1 for p in inbox_files() if file_id(p) not in labels) - len(queue)
    print(f"새 스크린샷 {len(queue)}장 → .tmp/queue.json, 판독용 이미지 {(len(queue) + PER_SHEET - 1) // PER_SHEET}장 (.tmp/sheet_N.jpg)"
          + (f", 중복 {dups}장 자동 처리" if dups else "") + (f", 다음 묶음에 남은 것 {pending}장" if pending > 0 else ""))
    for n, q in enumerate(queue, 1):
        print(f"  #{n} {q['id']}  {q['file']}  ({q['w']}x{q['h']})")


def make_sheet(items: list[dict], sheet_no: int, offset: int) -> None:
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
        d.text((x0 + 4, 6), f"#{offset + k + 1}  {q['id']}", fill="black", font=f_big)
        sheet.paste(c, (x0 + GUTTER, head))
        for t in range(11):  # 눈금: 0=맨 위, 10=맨 아래
            y = head + round(c.height * t / 10)
            d.line([(x0 + GUTTER - 10, y), (x0 + GUTTER + c.width, y)], fill=(255, 0, 80), width=1)
            d.text((x0 + 2, max(head, y - 9)), str(t), fill=(255, 0, 80), font=f_small)
        for t in (5,):  # 가로 가운데 표시
            x = x0 + GUTTER + round(c.width * t / 10)
            d.line([(x, head), (x, head + 12)], fill=(255, 0, 80), width=2)
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


def validate(lab: dict, v: dict) -> list[str]:
    if not isinstance(lab.get("fashion"), bool):
        return ["fashion 은 true/false"]
    if not lab["fashion"]:
        return []
    errs = []
    src = lab.get("source", "")
    if not (isinstance(src, str) and (src.startswith("@") and len(src) > 1 or src == "확인 불가")):
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
    problems = {fid: (["큐에 없는 id"] if fid not in queue else validate(lab, v)) for fid, lab in batch.items()}
    problems = {k: e for k, e in problems.items() if e}
    if problems:
        for fid, e in problems.items():
            print(f"  {fid}: {'; '.join(e)}")
        print(f"문제 {len(problems)}개 — 고친 뒤 다시 합치세요 (아무것도 합치지 않음)")
        return 1
    today, n_photo = today_kst(), 0
    for fid, lab in batch.items():
        q = queue[fid]
        rec = {**lab, "file": Path(q["file"]).name, "added": today, "hash": q["hash"]}
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
    fashion = sum(1 for l in batch.values() if l["fashion"])
    print(f"합침: {len(batch)}장 (패션 {fashion}장 → 사진 {n_photo}개 저장, 패션 아님 {len(batch) - fashion}장)")
    return 0


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
    ap.add_argument("--size", type=int, default=30)
    ap.add_argument("--review", type=int, default=0)
    a = ap.parse_args()
    TMP_DIR.mkdir(exist_ok=True)
    INBOX_DIR.mkdir(exist_ok=True)
    PHOTOS_DIR.mkdir(exist_ok=True)
    if a.next:
        cmd_next(a.size)
    elif a.merge:
        return cmd_merge(a.merge)
    else:
        cmd_check(a.review)
    return 0


if __name__ == "__main__":
    sys.exit(main())
