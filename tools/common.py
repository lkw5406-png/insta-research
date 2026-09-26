"""공통 설정 — 경로, 한국 시간, JSON 읽기·쓰기."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
DATA_DIR = ROOT / "data"
TMP_DIR = ROOT / ".tmp"
INBOX_DIR = ROOT / "inbox"          # 사장님이 캡처를 넣는 곳 (저장소에 안 올라감). 목록별 하위 폴더 3개
# 리서치 보드 목록 (2026-09-27 사장님: 사이트를 'LKW 리서치 보드'로, 인스타그램·핀터레스트·런웨이 3목록)
# 키 = 판정표·사이트에 쓰는 id, folder = inbox/ 아래 폴더 이름(사장님이 보는 이름)
BOARDS = {
    "instagram": {"name": "인스타그램", "folder": "인스타그램", "source_label": "출처 계정"},
    "pinterest": {"name": "핀터레스트", "folder": "핀터레스트", "source_label": "핀 올린 계정"},
    "runway": {"name": "런웨이", "folder": "런웨이", "source_label": "브랜드·시즌"},
}
PHOTOS_DIR = ROOT / "photos"        # 패션 사진만 잘라 낸 결과 (저장소에 안 올라감)
REPORT_DIR = ROOT / "report"        # 비공개 리포트 (저장소에 안 올라감)
LABELS_PATH = DATA_DIR / "photo_labels.json"  # Claude가 사진을 보고 쓴 판정표 (패션 여부·출처 계정·자르기 범위·키워드)
VOCAB_PATH = TOOLS_DIR / "trend_keywords.json"  # 매거진 트렌드 리서치와 같은 이름표

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
KST = timezone(timedelta(hours=9))


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    """중간에 끊겨도 파일이 깨지지 않게 임시 파일에 쓴 뒤 바꿔치기."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
