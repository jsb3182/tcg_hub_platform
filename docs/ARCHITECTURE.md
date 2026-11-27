# 통합 TCG 플랫폼 설계

## 배치 구조

```text
모바일 PWA / PC 웹 ── HTTPS ── Cloudflare TLS · DDoS · WAF
                                      │ 관리자 화면과 API에 Access 정책
                               Cloudflare Tunnel
                                      │
                     Galaxy A90 ┌── cloudflared
                                │        ↓ HTTP / loopback
                                │   Spring Boot 3.5 · Java 17
                                │     ├─ Vue 앱과 공개 WebP 응답
                                │     ├─ Spring Security / JWT / Access 서명 검증
                                │     └─ JPA·JDBC ─── PostgreSQL + PostGIS
                                │                          ↑     ↑
운영자 CLI ── 입력 검증·정규화 ──┤   비공개 작업 폴더 ── Python 워커  │
                                │                     └─ 파일 시트 ┘
                                └── Termux:Boot와 runit 서비스 감독

6종 카드 제공자 ──── 도감 수집 작업 ───┐
발행처·X·TCG 갤러리 ─ 공지 수집 작업 ───┴── Python 워커 ── PostgreSQL
A90 내부 /admin ── 인증 앱(TOTP) + 관리자 JWT ─┐
공개 도메인 /admin ── Access + 관리자 JWT ─────┴─ 운영 API ── 수집 요청 · 검수 · 감사 기록
```

| 디렉터리 | 책임 |
|---|---|
| `frontend/` | Vue Composition API, Router와 Pinia, 공개 도감·새 소식·로그인·모바일 관리자 화면, 설치형 PWA |
| `backend/` | 조회 API, 인증·인가, 원본 미디어 제공, 계정 생성 CLI, Flyway |
| `crawler-middleware/` | 게임별 카드 어댑터, 발행처·X·갤러리 수집, 로컬 정적 사이트 이관, 이미지 검증과 WebP 패킹 |
| `android/` | 공개 플랫폼 WebView, A90 서비스 관리, 원격 상태 조회와 로컬 네트워크 Wake-on-LAN |
| `deploy/` | PC 릴리스 빌드, Ubuntu 구성, Termux 서비스와 운영 명령 |

운영 서버 한 대에서 PostgreSQL이 조회 데이터와 작업 큐를 함께 보관한다. 브라우저는 같은 출처에서 API와 미디어를 사용한다. 이미지 처리에는 외부 요청을 받는 HTTP 포트가 필요하지 않다.

## 팩 수록 카드와 로컬 캐시

사용자는 발매 일정 또는 팩 검색에서 상품을 선택한다. `GET /api/v1/catalog-packs`는 종목·상품명·코드로 팩을 찾고 `GET /api/v1/packs/{id}`는 해당 팩에 연결된 공개 인쇄본을 페이지별로 반환한다. 동일 카드 번호의 여러 인쇄본은 각각의 ID로 구분한다. 레어도별 건수는 수록 목록에 근거한다. 수록 데이터가 도착하기 전에도 발표된 상품과 지역별 발매일을 볼 수 있다.

배포 시 `MEDIA_ROOT/cards`에는 내용 해시로 식별하는 WebP, `MEDIA_ROOT/sheets`에는 4×3 시트를 저장한다. DB는 원본 출처, 검증한 인쇄본과 파일의 관계, 이미지 좌표, 캡처 매칭용 64비트 해시를 보관한다. 덱 캡처 화면은 인증된 `POST /api/decks/import-capture`에 잘라낸 PNG 또는 JPEG와 종목·격자를 보낸다. 응답에는 칸별 상위 세 후보와 검수 여부가 담긴다. 업로드한 이미지는 매칭 후 메모리에서 해제한다.

보조 공급자 배치는 페이지 단위로 커서를 저장한다. 팩과 번호·이름이 일치하는 인쇄본에 공급자 관측값을 연결하며 후보가 여러 개면 연결을 보류한다. 상세 페이지 시세에는 판본이 확인된 거래소 관측의 금액·통화·시각이 표시된다. 운영자는 `/api/v1/admin/providers`에서 키 등록 여부와 WebP 디스크 사용량을 확인할 수 있다.

## 데이터 모델

전체 DDL은 [Flyway 마이그레이션](../backend/src/main/resources/db/migration/)에 있다. 카드 번호가 없는 자료나 같은 팩 코드를 쓰는 분류는 별도 내부 ID로 식별한다. 수록 항목은 게임·팩·언어명·번호·레어도·발매일을 가지며 게임 전용 속성은 JSONB에 보관한다. `card_variant`는 수록 항목별 일러스트·레어도·표시 순서를, `image_sheet`는 WebP 파일 키와 셀 크기를 가진다. 카드 조회는 팩별 수록 항목 단위다.

| 영역 | 관계와 조회 방식 |
|---|---|
| 계정 | 사용자 한 명에 갱신 세션 여러 개를 연결한다. 이메일은 정규화하고 세션에는 토큰 해시·만료·폐기 시각을 저장한다. |
| 수집·시세 | 소스와 외부 게시물 ID 조합으로 공지를 중복 제거한다. 거래소 상품을 판본에 연결하고 관측 시각별 금액·통화를 기록한다. `next_fetch_at`으로 소스·상품별 재조회 시점을 관리한다. |
| 매장·일정 | 취급 게임과 즐겨찾기는 매장별 다대다 관계다. 매장 일정에는 매장과 선택적 출처를, 개인 일정에는 소유자를 연결한다. 알림 발송 시각은 `timestamptz`로 기록하고 한국 운영 화면은 `Asia/Seoul`로 표시한다. |
| 덱 | 덱에 게임·포맷·규칙 버전을 연결한다. 구역과 수량을 저장하고 공유용 UUID로 읽기 링크를 구성한다. 포맷별 제한은 검증된 게임 규칙이 확보되면 등록한다. |
| 커뮤니티 | 자유·건의·거래 글, 카드 태그, 같은 글에 속한 댓글·대댓글, 글 또는 댓글 대상 신고를 저장한다. 거래 방식과 모집·예약·완료 상태를 구분한다. |

GIS의 저장 좌표는 WGS84 경도·위도 순서의 `geography(Point,4326)`이다. 반경 인수는 미터다. 지도의 화면 좌표 변환은 클라이언트가 맡는다.

```sql
-- 바인드 변수는 경도, 위도, 반경(m) 순서다.
SELECT id, name
FROM store
WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3);
```

## 1단계 API와 운영 흐름

| 메서드와 경로 | 입출력 |
|---|---|
| `GET /api/v1/games` | 게임 코드와 한국어 이름 배열 |
| `GET /api/v1/packs?game=YUGIOH` | 게임별 팩 배열. 배너 URL과 정밀도가 보존된 발매 표기를 포함한다. |
| `GET /api/v1/cards` | `game`, `packId`, `q`, `rarity`, 0부터 시작하는 `page`, `size`(기본 24, 최대 100). `items, page, size, total`을 반환한다. |
| `GET /api/v1/cards/{id}` | 공개 수록 항목, `specs`, 일러스트별 `variants`. 그림이 있으면 `image` 안에 `sheetId,col,row,url,cellWidth,cellHeight`가 있다. 누락 상태는 `null`이다. |
| `POST /api/v1/auth/register` | 같은 출처의 방문자가 이메일과 비밀번호로 일반 회원(`ROLE_USER`)을 만든다. 성공하면 HTTP 201과 로그인 세션을 반환한다. 이미 사용 중인 이메일은 409로 응답한다. |
| `POST /api/v1/auth/login` | JSON `email,password`를 받는다. `accessToken,role,email`과 갱신 쿠키를 발급한다. |
| `POST /api/v1/auth/refresh` · `logout` | 같은 출처와 `X-TCG-Request: 1` 헤더를 확인한다. 갱신은 기존 쿠키를 한 번만 사용할 수 있고 로그아웃은 해당 갱신 세션을 폐기한다. |
| `GET /api/v1/auth/admin-mode` | 현재 접속 경로에서 사용할 관리자 인증 방식을 반환한다. |
| `POST /api/v1/auth/local-admin` | A90 내부에서 관리자 액세스 토큰과 인증 앱의 6자리 코드로 단기 관리자 쿠키를 발급한다. |
| `GET /api/v1/admin/status` | Spring의 `ROLE_ADMIN`과 추가 인증을 확인한다. 로컬 전용 설치에서는 같은 계정의 TOTP 세션을, 공개 배포에서는 서명·발급처·대상이 유효한 Cloudflare Access 토큰을 요구한다. |
| `GET /api/v1/news` | 게임별 공개 뉴스·원문 링크를 페이지로 반환한다. `lang=ko`가 기본이며 `en`, `ja`를 지원한다. 제목·요약의 표시 언어와 번역 준비 상태가 포함된다. |
| `/api/v1/admin/operations`, `sources`, `worker`, `review` | 서버 상태, 수집 일시정지·재개·예약, 워커 재시작과 뉴스 검수를 제공한다. [요청 규격](COLLECTION.md) |
| `/api/v1/admin/catalog/packs` · `cards` | 검색·상세·신규 등록 및 버전을 확인한 수동 편집. 수집 카드의 검수·공개는 `PUT /api/v1/admin/catalog/cards/{id}/status`에서도 처리한다. |
| `POST /api/v1/admin/variants/{id}/image` · `GET /api/v1/admin/media-jobs/{id}` | 공개 카드의 크롭 완료 PNG를 비공개 작업 폴더에 저장하고 시트 반영 결과를 확인한다. |

1. 운영자가 원본 폴더를 이관한다. 기존 4×3 시트는 바이트를 그대로 보관하고 실제 셀 크기를 기록한다. 원본 섹션 ID와 항목 ID 또는 고정 순번으로 재실행 시 중복을 방지한다.
2. 새 이미지는 `enqueue VARIANT_ID FILE`로 등록한다. 워커가 한 번에 최대 12개 셀을 처리한다. 300×438 셀을 비율 유지·패딩한 뒤 1200×1314 WebP 품질 80으로 저장한다. 한 장만 들어온 마지막 묶음도 반영한다.
3. 파일을 임시 위치에서 해시 이름으로 원자적으로 옮기고, DB 트랜잭션에서 좌표와 완료 상태를 함께 갱신한다. 중단 직후 재실행하면 파일을 재사용할 수 있다. 자세한 명령과 실패 처리는 [워커 가이드](../crawler-middleware/README.md)에 있다.
4. PWA는 목록을 페이지 단위로 가져오고 펼친 카드의 상세와 시트를 읽는다. 앱 셸을 미리 캐시하며 최근 공개 조회 응답 80건, 공개 시트·배너 32개를 상한으로 둔다. 인증·관리자 응답과 탐색은 런타임 캐시 대상에서 제외한다.

## 관리자 도감 편집

### 운영 API

관리자 웹과 Android 운영 화면은 같은 인증 검사를 거친다. 서버는 요청마다 관리자 계정의 현재 권한을 확인한다.

| 경로 | 동작 |
|---|---|
| `GET /api/admin/server/status` | DB 연결, JVM 힙, 워커 하트비트, 예약 상태와 서비스 제어 가능 여부 |
| `POST /api/admin/server/sync` | 활성 출처의 수집 요청 등록. 발행처 재시도 시각을 준수한다. |
| `POST /api/admin/server/scheduler/{pause,resume}` | 자동 예약 일시정지 또는 재개 |
| `POST /api/admin/server/crawler/{start,stop}` | 워커가 새 수집 작업을 가져가는 동작 제어 |
| `POST /api/admin/server/{restart,shutdown}` | 등록한 systemd 서비스의 재시작 또는 정지 |
| `/api/v1/admin/stores` | 좌표·종목·공인 여부·공개 상태 등록 및 수정, 매장별 대회 등록 |

공개 매장 응답의 `events`는 현재 진행 중이거나 앞으로 7일 안에 시작하는 공개 대회다. 공인 여부가 확인되지 않은 매장은 `official: null`로 응답한다. 바인더는 카드와 소유자에 언어판·상태·교환 여부를 더해 수량을 기록한다. 기존 보유 기록은 판본과 상태 미지정으로 이관한다.

### 카드 편집

관리 화면에서 종목을 고른 뒤 팩을 등록하고, 카드 이름·번호·레어도·발매일과 게임별 상세 속성을 입력한다. 새 카드는 검수 대기로 저장할 수 있고, 팩은 등록 후 바로 검색할 수 있다. 다른 운영자가 먼저 수정한 카드는 최신 버전을 다시 연 뒤 저장한다. 자동 수집한 카드의 원본 필드는 출처에서 갱신하고 운영자는 게시 상태를 결정한다.

공개한 카드에서 일러스트를 골라 이미지를 자르면 브라우저가 300×438 PNG를 보낸다. 서버가 형식·크기를 확인한 뒤 Python 워커가 WebP 시트로 묶는다. 카드를 비공개로 바꾸거나 이미지를 교체하면 이전 시트 주소의 제공을 중단한다. 같은 시트를 쓰던 공개 카드의 셀만 새 파일에 복사하며, 비공개 카드를 다시 공개하면 보존한 셀에서 이미지를 복구한다. 온라인 PWA는 시트를 재확인하고 회수된 응답의 캐시를 지운다. 이미 내려받은 파일이나 오프라인 기기의 사본은 그 시점의 상태로 남을 수 있다.

## 후속 기능 구현 순서

1. **시세** — 시세 어댑터에 DB TTL·호출 한도·재시도 대기 시간을 적용하고 KREAM 등 거래소의 실제 상품 식별자를 사용한다.
2. **캘린더** — 운영 중인 OpenLayers 매장 지도에 매장 공지에서 추출한 일정과 사용자의 개인 일정을 표시하고 즐겨찾기 매장의 알림을 연결한다.
3. **게시판** — 자유·건의·거래 글, 카드 태그, 댓글·대댓글, 신고 처리를 연다.

계정별 바인더·덱·즐겨찾기 요청은 Spring Security 인증 후 `/api/v1/me/`에서 처리한다. 덱 편집 이력과 공유 토큰은 PostgreSQL에 저장한다. 공유 링크를 해제하면 비회원 조회도 종료된다. `/api/v1/play/cards`는 게임과 언어에 맞는 공개 카드명만 반환한다. 휴대폰에서 덱 연습의 셔플·손패 이동을 처리한다. 매장 검색은 `/api/v1/stores`에서 PostGIS 거리 조건을 적용한다.

A90 운영 절차와 실기기 인수 항목은 [배포 가이드](DEPLOYMENT.md)에 있다.
