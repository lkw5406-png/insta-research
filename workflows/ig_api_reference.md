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

## A. 웹에서 찾기 (잡지·룩북·런웨이 + 무신사 스냅 + Are.na) — `tools/web_cands.py`
1. 후보 출처 정하기 → `.tmp/jobs.json` (형식은 `tools/web_cands.py` 맨 위). 종류 3가지:
   - **잡지·룩북 (`page`)**: Hypebeast 기사(최근 기사 목록 `hypebeast.com/fashion`, `/fashion/page/2`…에서 lookbook·collection·street-style 기사),
     브랜드 공식 룩북, Vogue Scandinavia 등. 잘 맞았던 곳: Graphpaper, Norse Projects, Uniqlo U, Carhartt WIP, Studio Nicholson,
     Our Legacy, Sunflower, Prada 런웨이, JiyongKim. 화려한 스트릿 브랜드 룩북(Awake NY 등)은 거의 안 맞음.
   - **무신사 스냅 (`musinsa`)**: 한국 일반인 착장. 목록 주소 `https://www.musinsa.com/snap/main/recommend?sort=NEWEST`(최신)·`?sort=POPULAR`(인기).
     robots.txt가 'Claude-User'를 허용 → 사장님이 요청할 때만. 한 번에 약 36개이고 주소 뒤 조건(gender 등)을 바꿔도 같은 목록이 옴 →
     새 스냅은 며칠 지나 다시 받을 때 생김(이미 받은 건 도구가 자동으로 건너뜀).
     ⚠️ **"AI로 생성" 표시가 있는 사진은 절대 고르지 않음**(흰 배경 + MUSINSA 글자 사진에 많음. 왼쪽 아래 작은 표시 → 애매하면 크게 확인).
   - **Are.na (`arena`)**: 핀터레스트 비슷한 무드보드, 공식 API(키 불필요). `--arena-search 검색어`로 채널 찾기.
     잘 맞은 채널: `fit-pics-n_s2rve1iky`(Fit pics, 가장 좋음), `menswear-s4sdko_jurw`, `throwing-fits`, `menswear-ihx8m3zkipe`.
     흑백 화보·옛 잡지 스캔·아트 채널(예: `menswear-xlanwsjtlrs`, `menswear-media-system`, `workwear-lookbook`, `artist-fits`)은 안 맞음.
   - **KREAM 스타일 (`kream`)**: 한국 착용 후기. 태그 페이지 `https://kream.co.kr/social/tags/태그` (한 태그당 최신 약 20개, 사람이 찍힌 게시물만).
     robots.txt는 전부 허용(/my·/history·/bridge 제외). 서버가 'Claude-User' 이름엔 오류(500)를 줘서 브라우저 이름으로 접속 → 사장님 요청 때만.
     잘 맞은 태그: `워크자켓`, `와이드데님`, `시티보이룩`, `레더자켓`. 안 맞음: `미니멀룩`(거의 전부 AI 사진), `레이어드룩`·`남자코디`(카드뉴스·광고 많음).
     ⚠️ KREAM도 **"AI로 제작한 이미지"** 표시(사진 오른쪽 아래)가 있으면 제외. 글자 얹은 카드뉴스·상품 광고도 제외.
     출처(source)는 `KREAM 스타일 #태그`, 링크는 게시물 주소.
2. `uv run -q --with pillow python tools/web_cands.py --jobs .tmp/jobs.json` → `--sheet 앞글자들` → 판독 이미지(`.tmp/cands/sheets/`)를
   **하나씩 Read로 보고** 고른다. 고른 것만 크게 모아 한 번 더 보고 설명·키워드를 쓴다. 한 쇼의 연속 사진은 하나만.
3. `.tmp/ai_add.json` 작성 (형식은 `tools/ai_picks.py` 맨 위, via: 룩북/런웨이/스트릿) →
   `uv run -q --with pillow python tools/ai_picks.py --add .tmp/ai_add.json`. 문제가 있으면 아무것도 안 합치고 목록을 보여 줌.
4. 출처 섞기: 한 브랜드·한 채널이 전체의 10%를 넘지 않게. 사장님 보드처럼 남성 중심이되 여성 착장도 조금.

## B. 인스타그램 공식 API로 찾기
### 처음 한 번 연결 (사장님 + Claude)
0. 먼저 정할 것: **프로페셔널 계정은 비공개로 둘 수 없음**(전환하면 공개 계정이 됨).
   사장님 계정을 비공개로 유지하고 싶으면 **리서치 전용 인스타 계정을 새로 만들어** 그 계정으로 1~4를 진행
   (Business Discovery는 '내 계정'이 아니라 '남의 공개 계정'을 읽는 기능이라, 어느 계정으로 연결해도 결과는 같음).
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
- 2026-09-27: KREAM 스타일 28장(AI-0150~0177, 태그 10개·후보 173장). web_cands.py에 kream 종류 추가. #미니멀룩은 AI 사진이라 제외.
- 2026-09-27: 2차 99장(AI-0051~0149): 무신사 스냅 12, Are.na 40, 잡지·런웨이 13, 1차 후보 재선별 34(화려한 무늬 바지 2장은 제외).
  후보 수집 도구 tools/web_cands.py(잡지·무신사·Are.na) 추가. 무신사 'AI로 생성' 사진 제외 규칙. 인스타 연결은 페이스북 페이지에 인스타 연결이
  Meta 보안 조치로 막혀 대기 중(오래가는 사용자 토큰은 저장됨 → 연결되면 --setup만 다시).
- 2026-09-27: 매뉴얼 생성. 웹 검색으로 AI추천 50장(AI-0001~0050). 인스타 공식 API 도구(tools/ig_api.py)·감시 계정 59곳
  (보드 출처 48 + 브랜드 11, 브랜드 아이디는 추정 → 첫 --fetch에서 확인). 휴지통 기능.
