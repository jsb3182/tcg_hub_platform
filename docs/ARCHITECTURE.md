# 통합 TCG 플랫폼 설계

## 배치 구조

```text
모바일 PWA / PC 웹 ── HTTPS ── Cloudflare TLS · DDoS · WAF
                                      │ 관리자 화면과 API에 Access 정책
                               이미 연결된 Tunnel
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

후속 외부 소스 ── 제한된 스케줄러 ── 소스별 어댑터 ── 수집·검수 / 시세 테이블
```

| 디렉터리 | 책임 |
|---|---|
| `frontend/` | Vue Composition API, Router와 Pinia, 공개 도감·로그인·PC 관리자 상태 조회, 설치형 PWA |
| `backend/` | 조회 API, 인증·인가, 원본 미디어 제공, 계정 생성 CLI, Flyway |
| `crawler-middleware/` | 로컬 정적 사이트 이관, 이미지 유효성 확인, DB 작업 큐와 WebP 패킹 |
| `deploy/` | PC 릴리스 빌드, Ubuntu 구성, Termux 서비스와 운영 명령 |

운영 서버 한 대에서 PostgreSQL이 조회 데이터와 작업 큐를 함께 보관한다. 브라우저는 같은 출처에서 API와 미디어를 사용한다. 이미지 처리에는 외부 요청을 받는 HTTP 포트가 필요하지 않다.

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
| `POST /api/v1/auth/login` | JSON `email,password`를 받는다. `accessToken,role,email`과 갱신 쿠키를 발급한다. |
| `POST /api/v1/auth/refresh` · `logout` | 같은 출처와 `X-TCG-Request: 1` 헤더를 확인한다. 갱신은 기존 쿠키를 한 번만 사용할 수 있고 로그아웃은 해당 갱신 세션을 폐기한다. |
| `GET /api/v1/admin/status` | 유효한 Cloudflare Access 서명·발급처·대상과 Spring의 `ROLE_ADMIN`을 모두 확인한 후 상태를 반환한다. 운영자 화면은 `/admin`이다. |

1. 운영자가 원본 폴더를 이관한다. 기존 4×3 시트는 바이트를 그대로 보관하고 실제 셀 크기를 기록한다. 원본 섹션 ID와 항목 ID 또는 고정 순번으로 재실행 시 중복을 방지한다.
2. 새 이미지는 `enqueue VARIANT_ID FILE`로 등록한다. 워커가 한 번에 최대 12개 셀을 처리한다. 300×438 셀을 비율 유지·패딩한 뒤 1200×1314 WebP 품질 80으로 저장한다. 한 장만 들어온 마지막 묶음도 반영한다.
3. 파일을 임시 위치에서 해시 이름으로 원자적으로 옮기고, DB 트랜잭션에서 좌표와 완료 상태를 함께 갱신한다. 중단 직후 재실행하면 파일을 재사용할 수 있다. 자세한 명령과 실패 처리는 [워커 가이드](../crawler-middleware/README.md)에 있다.
4. PWA는 목록을 페이지 단위로 가져오고 펼친 카드의 상세와 시트를 읽는다. 앱 셸을 미리 캐시하며 최근 공개 조회 응답 80건, 공개 시트·배너 32개를 상한으로 둔다. 인증·관리자 응답과 탐색은 런타임 캐시 대상에서 제외한다.

## 후속 기능 구현 순서

1. **PC 등록·검수** — 팩·카드 편집, 크롭, 비공개 검수용 미리보기, 승인·반려를 연결한다. 공개 시트에는 승인된 그림만 넣는다. 이미 공개한 이미지를 철회할 때는 같은 시트의 보존 대상 이미지를 재패킹하고 기존 URL과 캐시를 갱신한다.
2. **소스 수집·시세** — X 계정·디시인사이드 갤러리별로 커서와 처리한 원문 ID를 저장한다. 연결 가능한 소스의 정식 인터페이스·접근 권한을 확인해 어댑터를 등록한다. 검수 기본값은 `PENDING`, 승인 또는 소스별 자동 게시 시 `PUBLISHED`로 전환한다. 시세 어댑터는 DB TTL·호출 한도·재시도 대기 시간을 적용하고 KREAM 등 거래소의 실제 상품 식별자를 사용한다.
3. **GIS·캘린더** — OpenLayers 지도에 반경·취급 게임 조건과 매장 길찾기를 연결한다. 매장 공지에서 추출한 일정과 사용자의 개인 일정을 표시하고 즐겨찾기 매장의 알림을 제공한다.
4. **덱·게시판** — 게임별 규칙 검증, 덱 공유·`html-to-image` 저장, 자유·건의·거래 글, 카드 태그, 댓글·대댓글, 신고 처리를 연다.

A90 운영 절차와 실기기 인수 항목은 [배포 가이드](DEPLOYMENT.md)에 있다.
