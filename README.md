# TCG 허브

유희왕, 바이스 슈발츠, 포켓몬 TCG, 원피스 카드게임, 니벨아레나, 리프트바운드의 카드와 최신 소식을 조회하는 PWA다. 한국어·영어·일본어로 전환할 수 있다. Python 워커가 출처별 일정에 따라 카드 데이터와 공지를 갱신한다. 운영자는 휴대폰의 관리자 화면에서 수집 상태를 확인하고 작업을 제어한다. 운영 대상은 Galaxy A90 5G의 Termux·Ubuntu다.

| 작업 | 시작점 |
|---|---|
| 전체 아키텍처, 데이터 흐름, API, 후속 기능 설계 | [시스템 설계](docs/ARCHITECTURE.md) |
| 테이블·외래 키·공간 인덱스와 덱 규칙 | [Flyway SQL](backend/src/main/resources/db/migration/) |
| PC 빌드, A90 설치, Cloudflare Tunnel·Access, 백업·복구 | [배포 가이드](docs/DEPLOYMENT.md) |
| Android에서 공개 사이트 열기, A90에서 서버 켜기·끄기 | [Android 앱 설치와 연결](docs/ANDROID.md) |
| 국내 매장 좌표·취급 종목·영업시간의 출처와 갱신 방법 | [매장 지도](docs/STORES.md) |
| Windows PC에서 API와 자동 수집 워커 함께 실행 | [Windows 실행 가이드](deploy/WINDOWS.md) |
| 로컬 카드 데이터 이관, 이미지 추가, 작업 재시도 | [워커 운영 가이드](crawler-middleware/README.md) |
| 자동 수집, 외부 소스 설정, 모바일 관리 | [수집과 운영](docs/COLLECTION.md) |
| 게임별 카드 언어, 판본 범위, 원본 출처와 갱신 방식 | [도감 출처](docs/CARD_SOURCES.md) |

**바인더**에서 언어판·카드 상태·교환 가능 여부별 보유 수량을 기록하고 9포켓 또는 목록으로 본다. **내 덱**에서 덱을 만들거나 수정한다. 저장한 덱은 공유 링크·덱 코드·PNG로 내보낼 수 있다. 덱 코드를 가져오면 편집 가능한 새 덱이 열린다. **플레이**에서 유희왕·포켓몬·원피스의 인쇄 카드명을 세 언어로 검색해 손패를 연습하거나 저장한 메인 덱을 불러온다. 시작 손패의 기본값은 유희왕 5장, 포켓몬 실물 덱 7장이며 연습 전에 바꿀 수 있다. 실제 온라인 대전은 화면에서 연결한 공식 앱을 이용한다. Pokémon TCG Pocket에는 모바일 전용 카드와 규칙이 있다. [Master Duel](https://www.konami.com/yugioh/masterduel/asia/ko/) · [포켓몬 카드 게임 Pocket](https://www.pokemonkorea.co.kr/pokemon_tcg_pocket/)

처음 방문하면 **바인더**나 **내 덱**에서 **회원가입**을 누른다. 이메일과 비밀번호를 등록하면 로그인되어 열려던 화면으로 돌아간다. 공개 도감과 매장 지도는 가입 전에도 볼 수 있다.

**매장 지도**에서 국내 매장의 주소와 종목별 출처를 확인하고, 가까운 매장을 검색해 즐겨찾기에 저장할 수 있다.

관리자는 PC나 휴대폰의 `/admin`에서 팩·카드를 등록하고 게시 상태와 일러스트를 편집한다. 이미지는 저장 영역을 미리 확인한 뒤 4×3 WebP 시트에 반영한다. [도감 편집과 이미지 처리](docs/ARCHITECTURE.md#관리자-도감-편집)

### A90 실기기 측정 기록

2026년 11월 26일 22시 41분(KST) A90에서 조회한 도감에는 6종 92,851개 수록 항목이 있었다. 최초 이관한 유희왕 994개가 포함된 수치다. 국내 매장 34곳 중 6곳은 원피스 발행사 자료로 공인 여부를 확인했다.

| 유희왕 | 포켓몬 TCG | 원피스 | 바이스 슈발츠 | 니벨아레나 | 리프트바운드 |
|---:|---:|---:|---:|---:|---:|
| 46,343 | 20,323 | 3,607 | 19,321 | 1,525 | 1,732 |

- **자동 수집과 언어** — 도감은 기본 24시간, 활성 발행처 공지는 1시간마다 조회한다. 새 소식은 한국어로 열리며 영어와 일본어를 선택할 수 있다. X 계정 연동에는 읽기 권한이 있는 API 토큰이, 디시인사이드 TCG 갤러리 연동에는 사전 서면 동의가 필요하다. [수집 출처와 설정](docs/COLLECTION.md)
- **휴대폰 운영** — Android 앱의 **A90 서버 관리**에서 서버를 켜거나 끈다. 같은 폰의 브라우저에서는 `http://127.0.0.1:8080/`으로 접속한다. 외부 방문자에게 링크를 공유하려면 별도로 도메인과 Cloudflare Tunnel을 연결하고 관리자 경로에 Access를 설정한다. [APK와 서버 릴리스](https://github.com/jsb3182/tcg_hub_platform/releases) · [공개 배포 절차](docs/DEPLOYMENT.md)
- **일정과 후속 기능** — 지도에서 매장별 향후 7일의 공개 대회를 볼 수 있다. 개인 캘린더와 알림, 거래소 시세, 커뮤니티·거래 게시판은 후속 구현 대상이다. [후속 기능 구현 순서](docs/ARCHITECTURE.md#후속-기능-구현-순서)

### 개발 환경

1. Java 17과 Maven, Node.js 22.12 이상, Python 3.12, PostGIS를 설치한 전용 PostgreSQL DB를 준비한다.
2. 배포 가이드에 따라 `DB_URL`(JDBC), `DB_USER`, `DB_PASSWORD`, `JWT_SECRET`(난수 32바이트 이상의 Base64), `MEDIA_ROOT`를 설정한다. Vite 개발 서버 사용 시 `PUBLIC_ORIGIN=http://localhost:5173`으로 설정한다.
3. `backend`에서 `mvn spring-boot:run`을 실행한다. Flyway가 마이그레이션을 적용하고 Spring이 루프백 8080에서 대기한다. `frontend`에서 `npm ci`, `npm run dev`를 실행하고 브라우저에서 `http://localhost:5173`을 연다.
4. [워커 운영 가이드](crawler-middleware/README.md)에 따라 Python 환경을 설치한 뒤 `python -m tcg_worker run`을 실행한다. 여섯 게임 도감과 발행처 공지의 초기 수집이 시작된다. 기존 정적 사이트의 `js/app.js`, `imgd/`, `pk/`도 사용할 경우 `check-legacy`로 건수와 시트를 확인하고 `import-legacy`로 이관한다.

PWA 설치와 오프라인 동작은 배포 빌드에서 확인한다. A90 내부에서는 Termux에서 관리자 계정과 인증 앱을 등록한 뒤 휴대폰 브라우저의 `http://127.0.0.1:8080/admin`에서 비밀번호와 인증 코드를 입력한다. 공개 도메인에서는 Cloudflare Access와 관리자 계정으로 접속한다. [계정 등록과 접속 절차](docs/DEPLOYMENT.md)

### 검증

- 프론트엔드는 `frontend`에서 `npm run build`로 서비스 워커를 포함해 빌드한다.
- 백엔드는 전용 테스트 DB와 위 환경 변수를 설정하고 `TCG_TEST_DB=1`로 `backend`에서 `mvn test`를 실행한다. 테스트는 트랜잭션을 되돌린다.
- 이미지·이관·DB 통합 테스트는 워커 운영 가이드의 명령으로 실행한다. 통합 테스트는 전용 테스트 DB를 사용한다.

최초 이관의 기준 자료는 팩·분류 23개, 카드 항목 994개, WebP 시트 82장, 팩 배너 11장이다. 실제 카드 데이터, 미디어, 운영 키는 운영자의 로컬 저장소에서 관리한다.
