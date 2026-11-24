# TCG 허브

다섯 TCG의 카드를 모바일과 PC에서 검색하는 한국어 PWA다. 1단계에서는 공개 카드 도감, 계정 인증, 기존 유희왕 도감 이관, WebP 스프라이트 생성이 동작한다. 운영 대상은 Galaxy A90 5G의 Termux·Ubuntu다.

| 작업 | 시작점 |
|---|---|
| 전체 아키텍처, 데이터 흐름, API, 후속 기능 설계 | [시스템 설계](docs/ARCHITECTURE.md) |
| 테이블·외래 키·공간 인덱스와 덱 규칙 | [Flyway SQL](backend/src/main/resources/db/migration/) |
| PC 빌드, A90 설치, Cloudflare Tunnel·Access, 백업·복구 | [배포 가이드](docs/DEPLOYMENT.md) |
| 로컬 카드 데이터 이관, 이미지 추가, 작업 재시도 | [워커 운영 가이드](crawler-middleware/README.md) |

### 개발 환경

1. Java 17과 Maven, Node.js 22.12 이상, Python 3.12, PostGIS를 설치한 전용 PostgreSQL DB를 준비한다.
2. 배포 가이드에 따라 `DB_URL`(JDBC), `DB_USER`, `DB_PASSWORD`, `JWT_SECRET`(난수 32바이트 이상의 Base64), `MEDIA_ROOT`를 설정한다. Vite 개발 서버 사용 시 `PUBLIC_ORIGIN=http://localhost:5173`으로 설정한다.
3. `backend`에서 `mvn spring-boot:run`을 실행한다. Flyway가 마이그레이션을 적용하고 Spring이 루프백 8080에서 대기한다. `frontend`에서 `npm ci`, `npm run dev`를 실행하고 브라우저에서 `http://localhost:5173`을 연다.
4. 기존 정적 사이트의 `js/app.js`, `imgd/`, `pk/`를 한 폴더에 준비한다. 워커의 `check-legacy`로 건수와 시트를 확인하고 `import-legacy`를 실행한다. 원본이 없어도 다섯 게임의 빈 도감부터 시작할 수 있다.

PWA 설치와 오프라인 동작은 배포 빌드에서 확인한다. PC 운영자 화면은 Cloudflare Access로 인증한 뒤 관리자 계정으로 조회한다. 계정은 A90의 관리 명령으로 만든다.

### 검증

- 프론트엔드는 `frontend`에서 `npm run build`로 서비스 워커를 포함해 빌드한다.
- 백엔드는 전용 테스트 DB와 위 환경 변수를 설정하고 `TCG_TEST_DB=1`로 `backend`에서 `mvn test`를 실행한다. 테스트는 트랜잭션을 되돌린다.
- 이미지·이관·DB 통합 테스트는 워커 운영 가이드의 명령으로 실행한다. 통합 테스트는 전용 테스트 DB를 사용한다.

최초 이관의 기준 자료는 팩·분류 23개, 카드 항목 994개, WebP 시트 82장, 팩 배너 11장이다. 실제 카드 데이터, 미디어, 운영 키는 운영자의 로컬 저장소에서 관리한다.
