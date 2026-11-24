# Galaxy A90 홈서버 배포

PC에서 Vue 정적 파일과 Java 실행 JAR를 빌드하고, A90에서는 Ubuntu 24.04 ARM64의 PostgreSQL 16·PostGIS 3, Java 17, Python 워커 한 개, Cloudflare 터널을 실행한다. 공용 HTTPS 주소는 하나다. 터널의 HTTP 원본은 `127.0.0.1:8080`이고 PostgreSQL은 `127.0.0.1:5432`에만 바인딩한다. 공유기의 포트포워딩은 사용하지 않는다.

## 1. PC에서 배포본 만들기

JDK 17의 `java`·`jar`, Maven 3.9, Node 22.12 이상, npm, GNU tar·coreutils, Bash를 준비한다. Windows에서는 이 명령을 Git Bash에서 실행한다. JDK의 `bin`과 Maven의 `bin`을 PATH에 추가한다.

```bash
bash deploy/build-release.sh
```

스크립트는 격리된 임시 디렉터리에서 Vue 생산 빌드를 JAR에 넣고 Maven의 package 단계를 수행한다. DB 통합 테스트는 별도 테스트 DB와 `TCG_TEST_DB=1`을 설정했을 때 실행된다. `backend/target/tcg-hub.jar`, `dist/tcg-hub-release.tar.gz`, `dist/tcg-hub-release.tar.gz.sha256`를 생성한다. 마지막 두 파일을 USB로 A90의 Download에 복사한다. 배포본에는 워커·설치 스크립트·이 가이드가 들어 있다. 기존 도감 데이터는 5단계에서 가져온다.

## 2. Cloudflare 계정 준비

1. Cloudflare DNS로 관리할 도메인을 추가하고 서비스 호스트명(예: `cards.example.com`)을 정한다. Zero Trust에서 조직의 팀 도메인과 관리자용 IdP를 확인한다.
2. **Access → Applications**에서 Self-hosted 앱 한 개를 만든다. 동일 앱의 공개 hostname/path 항목으로 `cards.example.com/admin`, `cards.example.com/admin/*`, `cards.example.com/api/v1/admin`, `cards.example.com/api/v1/admin/*`를 등록한다. 허용할 관리자 계정/그룹과 IdP를 지정하고 IdP의 다중 인증 정책을 적용한다. 이 앱의 Application Audience(AUD)와 `팀명.cloudflareaccess.com`을 복사한다. Spring도 Access 서명·발급자·대상·만료를 검증한다. [Access 경로 규칙](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/)
3. **Networking → Tunnels**에서 원격 관리형 `cloudflared` 터널을 생성한다. Published application route에서 공개 hostname을 위 주소로, 서비스 유형을 HTTP로, 주소를 `127.0.0.1:8080`으로 지정한다. DNS가 터널을 가리키고 zone의 HTTPS 인증서가 활성 상태인지 확인한다. 커넥터 토큰은 5단계에서 입력한다. 터널은 TCP 또는 UDP 7844 아웃바운드 연결을 사용한다. [터널 네트워크 구성](https://developers.cloudflare.com/tunnel/configuration/) · [토큰 파일 옵션](https://developers.cloudflare.com/tunnel/reference/run-parameters/)
4. 해당 zone의 SSL/TLS에서 HTTP→HTTPS 리디렉션과 WAF의 managed rules 배포 상태를 확인한다. 무료 플랜은 Free Managed Ruleset이 기본 적용된다. WAF custom rule로 해당 hostname의 `/internal` 및 `/internal/` 하위 경로를 차단한다. 캐시 규칙을 추가했다면 `/admin` 및 하위 경로와 `/api/` 하위 요청을 캐시 우회로 설정한다. [Cloudflare WAF 구성](https://developers.cloudflare.com/waf/get-started/)

## 3. A90에 Termux와 Ubuntu 설치

동일한 배포처의 Termux와 Termux:Boot를 설치하고 각각 한 번 연다. Android 설정에서 두 앱의 배터리 제한을 해제하고 상시 전원과 Wi-Fi를 준비한다. 기기를 재부팅하면 첫 잠금 해제가 필요할 수 있다. PRoot에는 독립적인 커널이나 systemd가 없으므로 Termux의 runit이 포그라운드 프로세스를 감독한다. [Termux 설치](https://github.com/termux/termux-app#installation) · [Termux:Boot 설정](https://github.com/termux/termux-boot#how-to-use) · [PRoot-Distro](https://github.com/termux/proot-distro) · [termux-services](https://github.com/termux/termux-services)

다음은 **Termux** 셸에서 실행한다. 저장소 권한 팝업에서 Download 읽기를 허용한다. DB, 미디어, 토큰 및 백업은 Termux 전용 저장공간에 둔다. PRoot 사용자와 파일 소유권은 에뮬레이션되며, Android의 앱 샌드박스가 다른 앱과의 실제 격리 경계다. [PRoot 제약 사항](https://github.com/termux/proot-distro#limitations)

```bash
pkg update
pkg install proot-distro termux-services util-linux curl coreutils tar
termux-setup-storage
proot-distro install ubuntu:24.04 --name ubuntu-tcg
cd "$HOME/storage/downloads"
sha256sum -c tcg-hub-release.tar.gz.sha256
mkdir -p "$HOME/tcg-release"
tar -xzf tcg-hub-release.tar.gz -C "$HOME/tcg-release"
install -m 700 "$HOME/tcg-release/deploy/tcgctl" "$PREFIX/bin/tcgctl"
```

## 4. DB·런타임 준비

아래의 세 값을 2단계에서 정한 실제 HTTPS origin, 팀 도메인, 64자리 앱 AUD로 바꾼다. `tcgctl install`은 Ubuntu 패키지와 가상환경을 설치하고 PostgreSQL을 먼저 기동한다. 비밀번호와 JWT 서명 키를 기기에서 생성해 `/etc/tcg-hub`에 저장하며 재실행할 때 기존 값을 사용한다. 기존 설정 변경은 Ubuntu 내부의 `runtime.env`에서 수행하고 서비스 재시작으로 반영한다. [Ubuntu ARM64 PostGIS 패키지](https://packages.ubuntu.com/noble/postgresql-16-postgis-3) · [cloudflared 서명 패키지](https://pkg.cloudflare.com/)

```bash
tcgctl install https://cards.example.com your-team.cloudflareaccess.com YOUR_64_HEX_APP_AUD
```

설치 전용 PostgreSQL 계정이 전용 DB `tcg_hub`와 PostGIS를 만들고 `tcg_app`에는 DB 접속과 public 스키마의 객체 생성 권한을 준다. Spring Flyway가 이 계정으로 마이그레이션을 실행한다. 새 DB에는 이미 PostGIS 객체가 있으므로 배포 프로필에서 Flyway baseline 버전을 **0**으로 설정해 V1부터 적용한다. 초기화 스크립트가 기존 업무 테이블을 발견하면 중단한다. 복구 설치는 다음 시작 명령을 실행하기 전에 7단계를 따른다.

```bash
tcgctl start-local
curl --fail http://127.0.0.1:8080/internal/ready
curl --fail http://127.0.0.1:8080/api/v1/games
tcgctl account admin@example.com ROLE_ADMIN
```

계정 명령에서 관리자의 실제 이메일과 암호를 입력한다. 비밀번호는 BCrypt 해시로 저장되고 이미 존재하는 이메일은 거부된다. 일반 계정은 같은 명령의 마지막 인수로 `ROLE_USER`를 사용한다. CLI의 표준 입력이 터미널이 아닌 경우에는 암호 한 줄을 비밀 입력으로 전달한다. HTTPS 브라우저 로그인은 5단계에서 확인한다.

## 5. 도감 마이그레이션과 공개

기존 사이트에서 `js/app.js`, `imgd/`, `pk/`를 디렉터리 구조 그대로 Termux의 `$HOME/tcg-import/`에 준비한다. 새로 업로드한 원본을 대기열에 넣을 때도 여기에 파일을 옮긴 뒤 DB의 실제 카드 variant ID를 지정한다.

```bash
tcgctl media check-legacy /mnt/tcg-source
tcgctl media import-legacy /mnt/tcg-source
# 단건 이미지 교체 예시
# tcgctl media enqueue 123 /mnt/tcg-source/card.png
tcgctl token
tcgctl start
tcgctl status
```

`tcgctl token` 프롬프트에는 커넥터 토큰 값만 붙여 넣는다. 토큰 파일은 전용 계정 소유·모드 0600이며 `cloudflared tunnel run --token-file`로 읽는다. 터널을 교체하면 `tcgctl maintenance` → `tcgctl token` → `tcgctl start` 순서로 적용한다.

모바일 회선에서 공개 PWA 설치, 카드 검색과 이미지 표시를 확인한다. 비로그인 창에서 `/admin`과 `/api/v1/admin` 하위 요청이 Access 인증을 요구하는지, 일반 계정으로 관리자 API에 접근하면 거부되는지, 허용된 관리자 계정에서만 관리 상태 조회가 성공하는지 확인한다. 공개 `/internal/ready`는 거부되고 기기 내부 readiness는 성공해야 한다.

## 6. 메모리와 서비스 상태

| 항목 | 기본값과 확인 방법 |
| --- | --- |
| Spring | `-Xms256m -Xmx1024m -XX:ActiveProcessorCount=2`, Hikari 최대 4개, Tomcat 최대 16개. RSS에는 힙 외에 스레드·클래스·네이티브 메모리가 포함된다. |
| PostgreSQL | `shared_buffers=96MB`, `work_mem=2MB`, 최대 연결 16개, 병렬 쿼리 워커 0개. DB 파일은 Ubuntu의 `/var/lib/postgresql/tcg-hub`에 저장한다. |
| Python | 프로세스 1개에서 도감 작업 1건과 소식 작업 1건을 병행한다. 이미지 처리와 워커 상태 갱신을 담당하는 루프는 유휴 시 최대 10초 간격으로 돈다. 공개 WebP는 `/var/lib/tcg-hub/media`, 비공개 이미지 대기열은 `spool`, 다시 받을 수 있는 원천 자료는 `catalog-cache`에 둔다. |
| 로그 | Termux의 `$PREFIX/var/log/tcg-{db,api,worker,tunnel}/current`. 서비스별 1 MiB 단위·이전 로그 4개 회전. |
| 제어 | `tcgctl status`, `tcgctl maintenance`(DB만 가동), `tcgctl stop`(모두 중지), `tcgctl start`(DB→API→워커·터널). 재부팅 시 마지막 활성화 상태를 복원한다. |

실기기에서는 스프라이트 한 시트를 처리하면서 Termux의 `top`과 Android 설정의 메모리·배터리 사용량을 확인한다. 화면을 끈 상태, Wi-Fi 재연결 후, 재부팅·잠금 해제 후에 외부 카드 조회와 워커 동작을 각각 확인한다. Android 12 이상은 백그라운드 프로세스 수나 CPU 사용량에 따라 Termux 프로세스를 종료할 수 있다. [Android Doze](https://developer.android.com/training/monitoring-device-state/doze-standby) · [Termux Android 12 안내](https://github.com/termux/termux-app#readme)

## 7. 백업·복구·업데이트

- **백업** — `tcgctl backup`은 터널·워커·API를 잠시 중지하고 PostgreSQL custom-format dump, 공개 미디어와 미처리 spool, SHA-256 목록을 `$HOME/tcg-backups/<백업명>/`에 만든 뒤 이전 서비스 활성 상태를 복원한다. 백업 중에는 서비스가 잠시 오프라인이다. 개인 콘텐츠와 인증 해시가 들어 있으므로 기기 밖에 보관할 복사본은 암호화한다. 터널 토큰·DB 비밀번호·JWT 키는 별도로 관리한다.
- **복구** — 새 설치의 4단계에서 `tcgctl install`까지만 실행한다. 백업 디렉터리를 Termux 전용 `$HOME/tcg-backups/`로 옮기고 `tcgctl restore 20261124T120000Z-1234`처럼 실제 백업명을 전달한다. 자신이 생성해 보관한 백업을 사용한다. 복구는 빈 미디어 디렉터리와 아직 Flyway를 실행하지 않은 전용 DB에서 동작한다. 중간에 끊기면 같은 백업명으로 재실행한다. 이어서 `tcgctl start-local`로 카드 수·이미지·계정 및 대기열을 확인하고, 새 토큰을 입력한 뒤 `tcgctl start`로 공개한다.
- **업데이트** — PC에서 새 릴리스를 생성하고 A90에서 `tcgctl backup`, `tcgctl maintenance` 순으로 실행한다. 새 빈 디렉터리(예: `$HOME/tcg-release-next`)에 검증한 배포본을 풀고 그 안의 `deploy/tcgctl`을 `$PREFIX/bin/tcgctl`에 설치한다. `TCG_RELEASE_DIR="$HOME/tcg-release-next" tcgctl install` 후 `tcgctl start`로 새 마이그레이션을 적용한다. 스키마를 변경한 버전의 롤백은 이전 릴리스와 배포 직전 백업을 새 설치에 복원한다.

## 8. 자동 수집과 모바일 운영

관리자로 로그인해 관리 화면에서 소스별 지난 성공·실패 시각, 실제로 확인한 행 수, 새로 저장한 행 수, 다음 실행 시각을 본다. 지금 실행과 재시도는 큐에 요청을 남긴다. 제공자의 호출 제한이 남아 있으면 그 이후 실행한다. 일시정지는 이미 커밋한 카드와 소식을 유지한다. 긴 도감 수집은 배치 사이에서 중단되고 다음 실행에서 기존 카드 키와 대조한다.

워커 재시작은 DB에 요청을 남기고 실행 중인 워커가 안전한 시점에 종료하면 runit이 새 프로세스를 띄운다. 대량 도감을 받는 동안에도 소식 수집과 heartbeat가 진행된다. 마지막 heartbeat가 오래된 경우 Termux에서 `tcgctl status`와 워커 로그를 확인한다. `tcgctl stop`으로 명시적으로 중단한 서비스는 `tcgctl start`로 다시 활성화한다. Windows에서 포그라운드 서비스를 실행하는 절차는 [Windows 실행 가이드](../deploy/WINDOWS.md)에 있다.

| 소식 출처 | 수집하는 내용 |
| --- | --- |
| 유희왕 | 코나미 영문판 공지 목록의 제목, 일자, 원문 링크. [Konami](https://www.yugioh-card.com/en/news/) |
| 포켓몬 | 공식 일본어 카드게임 뉴스 목록. 같은 상품의 여러 발표는 제목과 날짜로 구분한다. [포켓몬 카드](https://www.pokemon-card.com/info/) |
| 바이스 슈발츠 | 영어판 공식 공지 RSS의 최근 40개 제목과 원문 링크. [Bushiroad](https://en.ws-tcg.com/information/feed/) |
| 니벨아레나 | 한국어 공식 홈페이지의 공지 목록과 발행사가 직접 올린 일본 게임마켓 부스 공지. 한국어 홈페이지는 공개 HTTP를 사용한다. [한국 공식 공지](http://nivelarena.co.kr/bbs/board.php?bo_table=notice) · [발행사 부스](https://www.gamemarket.jp/booth/blog/5657) |
| 리프트바운드 | Riot 공식 발행 목록에 실린 게임 공지 제목과 발행시각. [Riftbound](https://playriftbound.com/en-us/news/) |

**X 공식 계정**은 X API 접근 권한이 있는 프로젝트의 app-only Bearer Token을 사용한다. A90의 Termux에서 `tcgctl x-token`을 실행해 비밀 입력으로 등록한 후 관리 화면에서 워커를 재시작하고 해당 소스를 재시도한다. 워커는 `/etc/tcg-hub/x.token`을 `X_BEARER_TOKEN`으로 읽는다. 첫 실행은 최근 타임라인 한 페이지를 가져오고 이후 `since_id`와 페이지 토큰으로 중단 지점을 이어 간다. 뉴스에는 계정명, 분류, 게시시각과 원문 링크를 저장한다. 토큰 누락, 이용권한·크레딧 부족, 호출 제한은 해당 소스 상태에 표시된다. [X 계정 타임라인 API](https://docs.x.com/x-api/users/get-posts)

**디시인사이드 TCG 갤러리**는 디시인사이드의 사전 서면 동의가 있을 때 운영한다. 동의 범위에 `tcggame` 목록의 자동 수집이 포함된 경우 Ubuntu의 `/etc/tcg-hub/feeds.env`에 `export DCINSIDE_WRITTEN_PERMISSION=tcggame`을 설정하고 파일 소유자를 `tcgapp`, 모드를 0600으로 지정한다. 워커를 재시작한 뒤 소스를 재시도한다. 수집기는 매회 robots 정책을 확인하고 공개 목록의 게시번호·제목·일시·원문 링크를 저장한다. 기본 검수 상태는 `PENDING`이다. [서비스 이용약관 제16조](https://nstatic.dcinside.com/dc/w/policy/policy_index.html) · [갤러리 robots 정책](https://gall.dcinside.com/robots.txt)

현장에서 소스 하나를 점검할 때는 `tcgctl media check-feed OFFICIAL_NEWS nivel-notice-kr`처럼 실행한다. 이 명령은 실제 한 번의 조회 결과와 첫 원문 링크를 출력한다. 정상적인 예약 수집은 DB 체크포인트·중복 제거·백오프를 적용한다. 이미지 권리가 확인된 운영자 파일은 5단계 `enqueue`로 처리하고, 외부 도감은 출처와 메타데이터를 저장한다.
