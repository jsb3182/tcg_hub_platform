# 카드와 새 소식 운영

**카드 도감**은 게임별 데이터에서 판본·번호·이름·레어도·수록 팩 등을 읽는다. **새 소식**은 발행처의 공지 제목·날짜·원문 링크를 보여준다. 원본 사이트가 날짜를 제공하지 않으면 수집 시각을 표시한다. 게임 선택은 도감과 새 소식 양쪽에서 사용할 수 있다.

## 자동 수집

A90의 로컬 설치에서는 `tcgctl start-local`, 공개 HTTPS 설치에서는 `tcgctl start`로 Python 워커를 실행한다. 워커는 PostgreSQL에 저장한 다음 조회 시각을 기준으로 작업을 고른다. 초기 배포 시 도감 5개와 발행처 공지 6개가 등록되며, 기본 주기는 도감 24시간·소식 1시간이다. DB에 원본 키와 체크포인트를 보관하므로 앱을 닫아도 서버에서 수집이 계속된다. 기존 한국어 유희왕 정적 도감을 가지고 있다면 [이관 도구](../crawler-middleware/README.md)로 함께 보관할 수 있다.

| 게임 | 발행처 소식 | X 계정 |
|---|---|---|
| 유희왕 | [KONAMI TCG 소식](https://www.yugioh-card.com/en/news/) | [@YuGiOh_TCG](https://x.com/YuGiOh_TCG) |
| 바이스 슈발츠 | [부시로드 공식 RSS](https://en.ws-tcg.com/information/feed/) | [@weissschwarz_en](https://x.com/weissschwarz_en) |
| 포켓몬 TCG | [포켓몬 카드 일본 공지](https://www.pokemon-card.com/info/) | [@PokemonTCG](https://x.com/PokemonTCG) |
| 니벨아레나 | [젬블로 국내 공지](http://nivelarena.co.kr/bbs/board.php?bo_table=notice) · [일본 게임마켓의 출전사 소식](https://www.gamemarket.jp/booth/blog/5657) | [@NivelArena](https://x.com/NivelArena) |
| 리프트바운드 | [Riot Games 공지](https://playriftbound.com/en-us/news/) | [@PlayRiftbound](https://x.com/PlayRiftbound) |

카드의 언어와 수록 범위는 출처별로 다르다. 수집 대상은 카드와 팩 메타데이터이며, 카드 상세의 출처 링크에서 원문을 확인할 수 있다. Riftbound를 외부에 서비스할 때 Riot의 디지털 도구 정책에 따라 서면 라이선스 또는 앱 전용 API 키를 준비한다. [게임별 도감 출처](CARD_SOURCES.md) · [Riot 개발자 정책](https://developer.riotgames.com/docs/riftbound)

## 게시물 언어

새 소식은 한국어로 열리며 영어와 일본어를 선택할 수 있다. 선택한 언어는 기기에 저장된다. 공지의 제목과 발행처가 제공한 요약을 로컬 번역 워커가 처리한다. 바이스 슈발츠 RSS에 설명이 있으면 짧은 발췌문도 표시한다. 원문을 확인할 수 있도록 출처 링크를 함께 제공한다.

번역이 준비되는 동안에는 원문 언어와 대기 상태를 표시한다. 이전에 수집한 게시물도 번역 큐에 들어가며, 제목이나 요약이 수정되면 변경된 원문을 기준으로 다시 번역한다. X는 계정과 게시물 유형, 갤러리는 수집을 허가받은 목록의 제목을 표시한다.

## X와 TCG 갤러리

- **X**는 공식 API의 사용자 타임라인을 읽는다. 운영자 계정에서 API 읽기 권한·사용량 한도를 확인하고 워커에 `X_BEARER_TOKEN`을 설정한다. 화면에는 계정, 게시물 유형과 원문 링크를 표시한다. [X 타임라인 API](https://docs.x.com/x-api/posts/timelines/introduction)
- **디시인사이드**의 대상은 `tcggame` 마이너 갤러리다. 이용약관 제16조에 따른 자동 수집 사전 서면 동의를 받은 운영자는 워커에 `DCINSIDE_WRITTEN_PERMISSION=tcggame`을 설정한다. 수집기는 사이트의 robots 정책도 확인한다. 게시물의 제목, 작성 시각, 원문 링크가 검수 대기열로 들어온다. [갤러리](https://gall.dcinside.com/mgallery/board/lists/?id=tcggame) · [디시인사이드 이용약관](https://nstatic.dcinside.com/dc/w/policy/policy_index.html)
- 처음 등록한 공식 발행처 공지는 자동 게시한다. X와 커뮤니티 글은 관리자가 승인한 뒤 공개된다. 자격 증명 누락·권한 오류·호출 한도는 해당 출처의 상태에 표시되며 다른 출처는 독립적으로 동작한다.

## 휴대폰에서 관리

1. A90 로컬 설치에서는 `tcgctl totp EMAIL`로 관리자 인증 앱을 등록한 뒤 같은 폰에서 `http://127.0.0.1:8080/login?to=admin`을 연다. 공개 배포에서는 운영 HTTPS 도메인의 `/admin`을 열고 Cloudflare Access를 통과한다. 두 모드 모두 사용 가능한 `ROLE_ADMIN` 계정이 필요하다. [관리자 등록과 로그인](DEPLOYMENT.md)
2. **서버 상태**에서 JVM 힙, 미디어 볼륨 여유 공간, 워커의 마지막 응답 시각, 게임별 공개 카드 수를 확인한다. 재시작은 DB에 요청으로 남고 워커가 안전한 시점에 종료한 뒤 프로세스 감독자가 다시 실행한다. 워커가 이미 중단됐다면 호스트 감독 상태도 확인한다.
3. **수집 출처**에서 마지막 성공 시각, 조회·추가 건수, 오류와 다음 조회 시각을 확인한다. 특정 출처를 일시정지하거나 재개할 수 있다. 즉시 수집은 대기열에 예약되며 출처가 반환한 재시도 시각을 따른다.
4. **검수 대기**에서 원문을 확인해 승인 또는 반려한다. 일반 갤러리처럼 게임을 알 수 없는 글은 승인 시 게임을 지정할 수 있다. 공개 결과는 `/news`에서 확인한다.

관리 작업에는 관리자 JWT와 같은 출처 요청 검사가 적용된다. A90 로컬 모드는 인증 앱으로 확인한 관리자 세션을, 공개 HTTPS 모드는 Cloudflare Access의 자격 증명을 검증한다. 제어 작업과 검수 결정은 관리자 ID와 시각과 함께 DB에 기록된다. 관리자 화면은 서버에 미리 정의된 작업만 요청한다.

## HTTP 인터페이스

| 요청 | 동작 |
|---|---|
| `GET /api/v1/news?game=WEISS&page=0&size=20` | 승인된 소식의 페이지와 총 건수. 게임 필터를 생략하면 전체를 반환한다. |
| `GET /api/v1/admin/operations` | 실제 서버 자원, 워커 시각, 출처별 일정·결과, 도감 건수 |
| `POST /api/v1/admin/sources/{id}/enabled` | JSON `{"enabled":false}`로 일시정지, `true`로 재개 |
| `POST /api/v1/admin/sources/{id}/run` | 활성 출처의 다음 실행을 요청 |
| `POST /api/v1/admin/worker/restart` | 워커 재시작 요청을 저장하고 HTTP 202 반환 |
| `GET /api/v1/admin/review` | 검수 대기 뉴스의 페이지 |
| `POST /api/v1/admin/review/{id}/decision` | `status`에 `PUBLISHED` 또는 `REJECTED`. 승인 시 선택적 `gameCode` 지정 |
