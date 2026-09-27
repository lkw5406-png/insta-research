# AI추천 — 보드와 무드가 비슷한 사진 찾기 (웹 + 인스타그램 공식 API)

결과는 **LKW 리서치 보드의 [AI추천] 탭**(https://lkw5406-png.github.io/insta-research/#ai)에 들어간다.
(2026-09-27 사장님 요청으로 매뉴얼 생성. 첫 작업: 웹에서 530여 장 → 50장, AI-0001~0050)

## 목표
사장님이 저장한 보드(인스타그램·핀터레스트·런웨이 목록)와 **무드가 비슷한 패션 사진**을 찾아, Claude가 **한 장씩 직접 보고** 골라
출처 링크 + 보드에서 닮은 사진 번호 + 키워드를 붙여 AI추천 탭에 넣는다. 실행은 사장님이 말씀할 때
("보드랑 비슷한 사진 찾아줘", "AI추천 채워줘", "인스타에서 새로 찾아줘").

## 원칙
- **비용 0원.** 판정은 Claude가 대화 안에서 사진을 봄. 인스타 공식 API도 무료.
- **인스타·핀터레스트 화면을 긁지 않음**(robots.txt 금지, 계정 정지 위험). 인스타는 **공식 API만**, 핀터레스트는 공식 API로
  전체 검색이 안 됨(제휴사 전용) → 사장님 본인 핀터레스트 보드를 쓰게 되면 그때 연결을 제안.
- 공식 API로 못 하는 것: 저장됨 목록 읽기, 비슷한 사진 검색, 개인 계정 읽기, (앱 심사 없이는) 해시태그 검색.
  할 수 있는 것: **공개 비즈니스·크리에이터 계정의 최근 게시물**(Business Discovery). → '감시 계정 목록' 방식.
- AI추천은 사장님이 모은 사진이 아니므로 [전체] 목록에 섞지 않음. 사진 파일은 photos/ai/(비공개), 공개본은 축소본만.

## 무드 기준 잡기 (매번 먼저)
1. `data/photo_labels.json`에서 휴지통 아닌 사진의 성별·스타일·컬러·소재·아이템 개수를 세고,
   `docs/img/*.jpg`로 모아보기 이미지를 만들어 직접 본다 (촬영 톤: 배경·조명·전신/스냅 여부까지).
2. 기준을 3~4줄로 정리 (2026-09-27 기준: 남성 가을·겨울, 흰/회색 벽 전신 룩북 + 실내·거리 자연광 스냅,
   레더/필드 재킷 + 와이드 데님·슬랙스 레이어드, 저채도 톤에 레드·퍼플·머스타드 한 점. 화려한 쇼피스 제외).
3. AI추천 탭에서 사장님이 **휴지통에 넣은 사진**(`python tools/ai_picks.py --list`)은 "싫은 방향"이므로 비슷한 건 고르지 않는다.

## A. 웹에서 찾기 (룩북·런웨이·스트릿 기사)
1. WebSearch로 후보 페이지 찾기: Hypebeast(룩북·패션위크 스트릿 스냅 기사, 사진이 많고 받기 쉬움), 브랜드 공식 룩북 페이지,
   Vogue Scandinavia 등. 잘 맞았던 곳: Graphpaper, Norse Projects, Uniqlo U, Carhartt WIP, Studio Nicholson, Our Legacy, Sunflower.
2. 페이지의 사진 주소를 뽑아 받고(Hypebeast는 `image-cdn.hypb.st` 주소에 `?w=720`), 번호 딱지 붙은 모아보기로 한 장씩 본다.
   임시 파일은 `.tmp/`에. 한 페이지에 같은 컷이 여러 번(쇼 연속 사진) 나오면 하나만.
3. 고른 사진으로 `.tmp/ai_add.json` 작성 (형식은 `tools/ai_picks.py` 맨 위) → `uv run -q --with pillow python tools/ai_picks.py --add .tmp/ai_add.json`.
   문제가 있으면 아무것도 안 합치고 목록을 보여 줌 → 고쳐서 다시. 같은 사진은 두 번 안 들어감.

## B. 인스타그램 공식 API로 찾기
### 처음 한 번 연결 (사장님 + Claude)
1. 사장님: 인스타 앱 → 프로필 ☰ → 설정 → '계정 유형 및 도구' → **프로페셔널 계정으로 전환**(크리에이터 추천, 무료).
2. 사장님: 페이스북 페이지 준비(없으면 새로 만들기, 비공개로 둬도 됨) → 페이지 설정 → '연결된 계정' → 인스타그램 연결.
3. 사장님: https://developers.facebook.com → 로그인 → 내 앱 → **앱 만들기**(이름 예: LKW Research, 용도는 '기타' → 유형 '비즈니스').
   앱 대시보드 → 앱 설정 → 기본 설정에서 **앱 ID**, **앱 시크릿 코드**(보기 눌러 확인)를 복사.
4. 사장님: https://developers.facebook.com/tools/explorer (Graph API 탐색기) → 오른쪽 위 앱을 방금 만든 앱으로 →
   '권한 추가'에서 `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`, `business_management`
   → **Generate Access Token** → 로그인 창에서 그 페이지와 인스타 계정을 체크하고 승인 → 나온 토큰 복사.
5. 사장님: `C:\Users\lkw15\.secrets\insta-research.env`를 메모장으로 열어 `META_APP_ID=`, `META_APP_SECRET=`, `IG_SHORT_TOKEN=` 뒤에 붙여 넣고 저장.
   **키는 대화창에 붙여 넣지 않음**(대화 기록에 남음). 짧은 토큰은 약 1시간 뒤 만료 → 붙여 넣은 뒤 바로 Claude에게 "넣었어".
6. Claude: `uv run -q --with pillow python tools/ig_api.py --setup` → 오래가는 토큰(페이지 토큰, 만료 없음)으로 바꾸고 인스타 계정 id 저장,
   짧은 토큰 줄은 지움. 이어서 `--check`.
   (앱은 '개발 모드' 그대로 둠: 앱 관리자 본인 계정만 쓰므로 Meta 앱 심사 필요 없음)

### 매번
1. `tools/ig_api.py --fetch` → `data/ig_watchlist.json` 계정마다 최근 12개 게시물(이미 본 것은 건너뜀, `data/ig_seen.json`).
   못 가져온 계정(개인 계정·아이디 틀림)은 목록의 status에 기록됨 → 사장님께 보고, 아이디가 틀린 건 고쳐서 다시.
2. `--sheet` → `.tmp/ig_api/sheet_N.jpg`를 **하나씩 Read로 보고** 고른다 (S-번호 딱지).
3. `.tmp/ig_api/picks.json` 작성 (형식은 `tools/ig_api.py` 맨 위) → `--pick .tmp/ig_api/picks.json` → AI추천 탭에 합쳐짐(via 인스타, 게시물 링크).
- 감시 계정 추가: 보드에 새 출처 계정이 생기거나 잘 맞는 계정을 찾으면 `data/ig_watchlist.json`에 username만 추가.
  사장님 허락 없이 계정을 빼지 않음.

## 마무리 (A·B 공통)
1. `uv run -q --with pillow python tools/build_report.py --publish` (+ 옵션 없이 한 번 → PC용 report/)
2. `git status`로 photos/·inbox/·.env가 안 올라가는지 확인 → `git add data docs tools workflows` → 커밋 → `git pull -q --rebase` → 푸시.
3. 사장님께 보고: 후보 몇 장 중 몇 장 골랐는지, 출처별 개수, 보드와 가장 비슷한 출처, 못 가져온 계정, 링크(`#ai`).

## 휴지통 (모든 목록 공통)
- 사이트 사진마다 [휴지통] → [휴지통] 탭 → [복구]. 사이트는 보기 전용이라 **누른 기기에만** 저장됨.
- 사장님이 위쪽 [변경 목록 복사] 글("삭제: IG-0003, AI-0012 / 복구: …")을 주면:
  `python tools/ai_picks.py --apply "그 글"` → 마무리 1~2. 판정표에 "trashed": 날짜만 적고 파일은 안 지움(언제든 복구).
- 완전 삭제는 사장님이 명시적으로 요청할 때만, 대상 번호를 확인받고.

## 문제가 생겼을 때
- `--setup` "토큰 바꾸기 실패": 짧은 토큰 만료(1시간) → 탐색기에서 새로 받아 다시. 앱 ID·시크릿이 같은 앱 것인지 확인.
- "연결된 페이스북 페이지를 못 찾음": 인스타가 프로페셔널 계정인지, 페이지와 연결됐는지, 토큰 받을 때 페이지를 체크했는지.
- 호출 한도(시간당 약 200회): 도구가 멈추고 몇 곳까지 했는지 알려 줌 → 1시간 뒤 `--accounts 아이디,아이디`로 나머지만.
- 토큰이 무효가 됨(비밀번호 변경·앱 권한 해제 등): 처음 한 번 연결 4~6만 다시.
- Graph API 버전(v25.0)이 종료되면 `tools/ig_api.py`의 `GRAPH` 주소 버전을 올림.

## 변경 기록
- 2026-09-27: 매뉴얼 생성. 웹 검색으로 AI추천 50장(AI-0001~0050). 인스타 공식 API 도구(tools/ig_api.py)·감시 계정 59곳
  (보드 출처 48 + 브랜드 11, 브랜드 아이디는 추정 → 첫 --fetch에서 확인). 휴지통 기능.
