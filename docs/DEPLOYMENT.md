# Galaxy A90 홈서버 배포

**A90만 있다면** [휴대폰 설치 안내](ANDROID.md#pc-없이-처음-설치하거나-로컬-서버-업데이트하기)를 따른다. GitHub 릴리스에는 Vue 화면을 포함한 Java 실행 JAR와 Python 워커가 들어 있다. A90은 Ubuntu 24.04 ARM64에서 Java 17과 워커 한 개를 실행한다. Google Play판 Termux에서는 PostgreSQL과 PostGIS를 Termux에서 직접 실행한다. 외부 공개용 Cloudflare 터널은 `127.0.0.1:8080`에 연결하고, DB는 `127.0.0.1:5432`에서 접속을 받는다.

## 1. PC에서 배포본 만들기

JDK 17의 `java`·`jar`, Maven 3.9, Node 22.12 이상, npm, GNU tar·coreutils, Bash를 준비한다. Windows에서는 이 명령을 Git Bash에서 실행한다. JDK의 `bin`과 Maven의 `bin`을 PATH에 추가한다.

```bash
bash deploy/build-release.sh
```

스크립트는 격리된 임시 디렉터리에서 Vue 생산 빌드를 JAR에 넣고 Maven의 package 단계를 수행한다. DB 통합 테스트는 별도 테스트 DB와 `TCG_TEST_DB=1`을 설정했을 때 실행된다. `backend/target/tcg-hub.jar`와 `dist`의 배포 압축 파일, 체크섬, `bootstrap-termux.sh`, `setup-termux.sh`를 생성한다. USB로 처음 설치할 때는 `tcg-hub-release.tar.gz`, `tcg-hub-release.tar.gz.sha256`, `bootstrap-termux.sh` 세 파일을 A90의 `Download/tcg-hub/<압축 파일 SHA-256 앞 12자리>/`에 함께 복사한다. 기존 도감 데이터는 5단계에서 가져온다.

### Cloudflare 등록 전 A90에서 먼저 열기

3단계에서 사용하는 배포처에 맞춰 Termux를 한 번 연다. 아래 한 줄에서 `DIGEST12`를 PC에서 복사한 **이번 릴리스의 12자리 폴더명**으로 바꾼 뒤 A90의 Termux에 붙여 넣는다. Android 저장공간 권한 창이 표시되면 허용하고 Termux로 돌아와 Enter를 누른다. 설치 중에는 전원과 인터넷 연결을 유지한다.

```bash
d=/sdcard/Download/tcg-hub/DIGEST12; [ -r "$d/bootstrap-termux.sh" ] || { termux-setup-storage; read -rp 'Allow storage, then press Enter: '; }; bash "$d/bootstrap-termux.sh" --proof
```

스크립트가 앱 전용 저장소의 복사본에서 압축 파일과 내부 매니페스트를 검증하고, 옆에 있는 실행 스크립트도 패키지의 원본과 대조한다. 필요한 Termux 패키지와 Ubuntu 24.04를 준비한 뒤 `tcgctl install --local`, `tcgctl start-local`을 실행한다. 폰의 브라우저에서 `http://127.0.0.1:8080/`을 열어 카드와 뉴스를 조회한다. 관리자는 4단계에서 인증 앱을 등록한 뒤 같은 기기에서 로그인한다.

`--proof`를 주면 서버의 준비 상태와 공개 게임 목록을 조회한다. 원피스를 포함한 여섯 종목이 모두 있으면 같은 폴더에 `tcg-hub-ready.json`을 원자적으로 기록한다. 파일에는 압축 파일의 SHA-256, 상태, 게임 수와 UTC 확인 시각이 들어간다. PC에서는 이번 전송 이후의 확인 시각과 동일한 릴리스 해시를 대조한다. 기록이 필요 없으면 `--proof`를 생략한다. 같은 로컬 릴리스에서 다시 실행하면 DB와 기존 데이터를 보존한다.

## 2. 외부 공개용 Cloudflare 계정 준비

리프트바운드 도감은 기본 수집기에서 RiftHunt 판본과 Riot 공식 갤러리를 읽는다. 앱 전용 `RIOT_API_KEY`를 등록하면 보조 수집기가 Riot 콘텐츠 API에서 받은 공식 데이터를 연결한다. 키를 등록한 뒤에도 기존 판본과 그림은 남는다. 이 도감을 외부에 공개할 때는 앱에 발급된 키 또는 서면 라이선스의 범위에 맞는 자료를 제공한다. [리프트바운드 도감 출처](CARD_SOURCES.md#리프트바운드-공개-배포) · [Riot 디지털 도구 정책](https://developer.riotgames.com/docs/riftbound)

공개 주소를 받은 사람은 브라우저 또는 Android 앱에서 도감·소식·매장 지도를 바로 열 수 있다. 주소를 전달받은 다른 사람도 열 수 있다. 개인 바인더·덱은 서비스 계정 로그인 후 사용하고, 서버 켜기·끄기 권한은 A90에서 승인한 제어 폴더에만 부여한다. 아래 Access 앱의 적용 범위는 관리자 경로로 지정한다.

1. 소유하거나 관리 권한이 있는 도메인을 Cloudflare에 추가해 zone이 **Active**가 되면 그 아래에 서비스 호스트명(예: `cards.example.com`)을 정한다. 이미 운영하는 사이트의 서브도메인을 쓸 수 있다. Zero Trust에서 조직의 팀 도메인과 관리자용 IdP를 확인한다. [공개 호스트용 Access 요건](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
2. **Access → Applications**에서 Self-hosted 앱 한 개를 만든다. 동일 앱의 공개 hostname/path 항목으로 `cards.example.com/admin`, `cards.example.com/admin/*`, `cards.example.com/api/v1/admin`, `cards.example.com/api/v1/admin/*`, `cards.example.com/api/admin/server/*`를 등록한다. 허용할 관리자 계정/그룹과 IdP를 지정하고 IdP의 다중 인증 정책을 적용한다. 이 앱의 Application Audience(AUD)와 `팀명.cloudflareaccess.com`을 복사한다. Spring도 Access 서명·발급자·대상·만료를 검증한다. [Access 경로 규칙](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/)
3. **Networking → Tunnels**에서 원격 관리형 `cloudflared` 터널을 생성한다. Published application route에서 공개 hostname을 위 주소로, 서비스 유형을 HTTP로, 주소를 `127.0.0.1:8080`으로 지정한다. DNS가 터널을 가리키고 zone의 HTTPS 인증서가 활성 상태인지 확인한다. 커넥터 토큰은 5단계에서 입력한다. 터널은 TCP 또는 UDP 7844 아웃바운드 연결을 사용한다. [터널 네트워크 구성](https://developers.cloudflare.com/tunnel/configuration/) · [토큰 파일 옵션](https://developers.cloudflare.com/tunnel/reference/run-parameters/)
4. 해당 zone의 SSL/TLS에서 HTTP→HTTPS 리디렉션과 WAF의 managed rules 배포 상태를 확인한다. 무료 플랜은 Free Managed Ruleset이 기본 적용된다. WAF custom rule로 해당 hostname의 `/internal` 및 `/internal/` 하위 경로를 차단한다. 사용자 지정 캐시 규칙이 있으면 `/admin` 및 하위 경로와 `/api/`, `/media/sheets/`, `/media/cards/` 하위 요청을 캐시 우회로 설정한다. 카드 그림이나 시트의 공개를 중단하면 다음 요청이 원본 서버에 도달해 404를 받는다. [Cloudflare WAF 구성](https://developers.cloudflare.com/waf/get-started/)

개인 기기 몇 대만 연결하는 경우, 도메인 구매 없이 Cloudflare One Client(WARP)에 기기를 등록하고 사설 IP 경로와 허용 정책을 설정할 수 있다. 이 앱의 원본은 A90의 루프백 주소이므로 해당 방식에는 별도의 사설 경로와 원본 연결 설정이 필요하다. Quick Tunnel은 임시 개발용 주소를 발급한다. [사설 네트워크 연결](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/private-net/cloudflared/) · [Quick Tunnel의 용도와 제한](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## 3. A90에 Termux와 Ubuntu 설치

이 A90에 설치된 Google Play판 Termux에는 부팅 실행 기능이 내장되어 있다. Termux를 한 번 열고 Android 설정에서 이 앱의 배터리 제한을 해제한다. F-Droid판을 사용하는 기기는 Termux와 Termux:Boot를 모두 F-Droid에서 받아 각각 한 번 열고 두 앱의 배터리 제한을 해제한다. [Google Play판 부팅 기능](https://github.com/termux-play-store) · [F-Droid판 Termux:Boot 설정](https://github.com/termux/termux-boot#how-to-use)

상시 전원과 Wi-Fi를 준비한다. 기기를 재부팅하면 첫 잠금 해제가 필요할 수 있다. PRoot에는 독립적인 커널이나 systemd가 없으므로 Termux의 runit이 포그라운드 프로세스를 감독한다. [Termux 설치](https://github.com/termux/termux-app#installation) · [PRoot-Distro](https://github.com/termux/proot-distro) · [termux-services](https://github.com/termux/termux-services)

다음은 **Termux** 셸에서 실행한다. 저장소 권한 팝업에서 Download 읽기를 허용한다. DB, 미디어, 토큰 및 백업은 Termux 전용 저장공간에 둔다. PRoot 사용자와 파일 소유권은 에뮬레이션되며, Android의 앱 샌드박스가 다른 앱과의 실제 격리 경계다. [PRoot 제약 사항](https://github.com/termux/proot-distro#limitations)

```bash
pkg update
pkg install proot-distro termux-services util-linux curl coreutils tar
termux-setup-storage
proot-distro install ubuntu:24.04 --name ubuntu-tcg
cd "$HOME/storage/downloads"
cd "tcg-hub/DIGEST12"
sha256sum -c tcg-hub-release.tar.gz.sha256
mkdir -p "$HOME/tcg-release"
tar -xzf tcg-hub-release.tar.gz -C "$HOME/tcg-release"
install -m 700 "$HOME/tcg-release/deploy/tcgctl" "$PREFIX/bin/tcgctl"
```

## 4. DB·런타임 준비

아래의 세 값을 2단계에서 정한 실제 HTTPS origin, 팀 도메인, 64자리 앱 AUD로 바꾼다. `tcgctl install`은 서비스 패키지와 Python 가상환경을 설치하고 PostgreSQL을 먼저 기동한다. Ubuntu의 `/etc/tcg-hub`에는 앱 DB 암호와 JWT 서명 키를 저장한다. [cloudflared 서명 패키지](https://pkg.cloudflare.com/)

```bash
tcgctl install https://cards.example.com your-team.cloudflareaccess.com YOUR_64_HEX_APP_AUD
```

### Termux 배포처별 PostgreSQL

| 설치 환경 | PostgreSQL 실행 위치 | 데이터 디렉터리 |
| --- | --- | --- |
| A90 Google Play판 신규 설치 | Termux의 `postgresql`·`postgis` 패키지. A90에서 PostgreSQL 18과 PostGIS 3.6 조합을 확인했다. | Termux의 `$PREFIX/var/lib/tcg-hub-native/data` |
| F-Droid판 신규 설치와 기존 Ubuntu 클러스터 | Ubuntu 24.04의 PostgreSQL 16·PostGIS 3 | Ubuntu의 `/var/lib/postgresql/tcg-hub` |

A90의 Termux 네이티브 PostgreSQL 18 이상은 시작할 때 `io_method=sync`를 적용한다. A90에서 기본 설정으로 상주하던 I/O 워커 3개를 줄이기 위해서다. [PostgreSQL I/O 설정](https://www.postgresql.org/docs/18/runtime-config-resource.html#GUC-IO-METHOD)

Android 12에서 관리 앱이 DB나 워커를 '확인 필요'로 표시하면 Termux에서 `tcgctl status`를 실행해 감독 상태를 확인한다. Galaxy A90에서 웹 조회가 가능한 동안에도 Android 로그에 `Trimming phantom processes`가 기록되고 runit 감독자가 종료된 사례가 있었다. 기본 자식 프로세스 한도 32개는 기기의 모든 앱에 걸쳐 적용된다. [Termux의 Android 12 안내](https://github.com/termux/termux-app#installation)

Play판 PRoot에서 Ubuntu의 `initdb`가 `expected absolute path: "--shm-helper"`로 실패할 수 있다. PRoot가 공유 메모리 도우미를 `/proc/self/exe`로 시작할 때 이 경로가 Android 링커를 가리키기 때문이다. Termux의 PostgreSQL 패키지는 Android 공유 메모리 라이브러리를 사용한다. 두 구성 모두 Ubuntu의 Spring과 워커가 같은 루프백 주소로 SCRAM 인증을 수행한다. [PRoot 공유 메모리 구현](https://github.com/termux/proot/blob/v5.1.107.80/src/extension/sysvipc/sysvipc_shm.c#L141-L146) · [Play판 Termux 변경 사항](https://github.com/termux-play-store#readme) · [Ubuntu ARM64 PostGIS 패키지](https://packages.ubuntu.com/noble/postgresql-16-postgis-3)

`tcgctl status`에서 선택한 엔진과 DB 서비스 상태를 확인한다. 설치 시 선택값은 Termux 전용 `$PREFIX/var/lib/tcg-hub/db-engine`에 기록된다. 신규 설치에서 엔진을 지정할 때는 `TCG_DB_ENGINE=native tcgctl install --local` 또는 `TCG_DB_ENGINE=guest tcgctl install --local`을 실행한다. 기존 DB를 다른 엔진으로 옮길 때는 7단계의 논리 백업과 새 설치 복구를 사용한다. 네이티브 DB의 관리 암호 파일은 `$PREFIX/var/lib/tcg-hub-native/auth/postgres.pw`에 모드 0600으로 저장된다. Termux 패키지 업데이트로 PostgreSQL의 메이저 버전이 바뀔 예정이면 업데이트 전에 백업한다. 서버와 데이터 디렉터리의 메이저 버전이 다르면 기동 스크립트가 중단된다.

이미 `--local`로 설치한 경우에는 Cloudflare에서 도메인·Access 앱·공개 라우트를 구성한 뒤 아래 명령으로 전환한다. `configure-public`은 커넥터를 설치하고 공개 식별자만 `/etc/tcg-hub/access.env`에 기록하므로 기존 DB, JWT 서명 키와 소스 토큰을 보존한다. `tcgctl start`와 재부팅 시 터널 서비스 모두 HTTPS origin·Access 팀 도메인·AUD·커넥터 토큰을 확인한다. Access 정책과 터널 라우트의 실제 적용 여부는 5단계에서 외부 회선으로 확인한다.

```bash
tcgctl maintenance
tcgctl configure-public https://cards.example.com your-team.cloudflareaccess.com YOUR_64_HEX_APP_AUD
tcgctl token
tcgctl start
```

설치 전용 PostgreSQL 계정이 전용 DB `tcg_hub`와 PostGIS를 만들고 `tcg_app`에는 DB 접속과 public 스키마의 객체 생성 권한을 준다. Spring Flyway가 이 계정으로 마이그레이션을 실행한다. 새 DB에는 이미 PostGIS 객체가 있으므로 배포 프로필에서 Flyway baseline 버전을 **0**으로 설정해 V1부터 적용한다. 초기화 스크립트가 기존 업무 테이블을 발견하면 중단한다. 복구 설치는 다음 시작 명령을 실행하기 전에 7단계를 따른다.

```bash
tcgctl start-local
curl --fail http://127.0.0.1:8080/internal/ready
curl --fail http://127.0.0.1:8080/api/v1/games
tcgctl account admin@example.com ROLE_ADMIN
```

방문자는 웹에서 **회원가입**을 눌러 일반 계정을 만든다. 이메일은 로그인에 쓰며 가입 확인 메일은 발송하지 않는다. 비밀번호는 12자 이상, UTF-8 기준 72바이트 이내여야 하며 서버에는 BCrypt 해시가 저장된다.

공개 주소를 열기 전에 A90에서 운영자용 이메일로 관리자 계정을 먼저 만든다. 이미 사용 중인 이메일로 계정 생성 명령을 실행하면 기존 계정과 권한이 유지된다. 운영자용 이메일은 일반 회원가입에 사용하지 않는다. 관리자는 아래 절차에 따라 인증 앱을 등록한다.

### A90에서 로컬 관리자 로그인

첫 기동 때 계정을 자동 생성할 경우 API 프로세스에 `TCG_BOOTSTRAP_ADMIN_EMAIL`과 `TCG_BOOTSTRAP_ADMIN_PASSWORD`를 전달한다. A90에서는 Ubuntu의 `/etc/tcg-hub/web-config/` 아래에 `tcg.bootstrap.email`과 `tcg.bootstrap.password`를 한 줄씩 담은 비공개 파일로 둘 수 있다. 디렉터리는 0700, 파일은 0600으로 설정하고 API 계정만 읽을 수 있게 한다. 관리자 생성 후 두 초기화 파일을 삭제하고 Termux에서 `tcgctl password 본인이메일`을 실행한다. 현재 비밀번호와 새 비밀번호를 터미널의 숨김 입력으로 받으며, 변경이 성공하면 기존 갱신 세션과 로컬 관리자 세션이 만료된다. 기존 관리자 계정이 있으면 최초 기동 설정을 건너뛴다.

1. `tcgctl start-local`로 앱을 기동한다. 관리자 계정이 없으면 Termux에서 `tcgctl account admin@example.com ROLE_ADMIN`의 예시 이메일을 자신의 것으로 바꿔 실행한다. 비밀번호를 입력하는 동안 화면에는 글자가 표시되지 않는다. Enter를 누른 뒤 `Account created.`가 나오면 다음 단계로 간다. `Use at least 12 characters and at most 72 UTF-8 bytes`가 나오면 길이 조건에 맞는 새 비밀번호로 다시 실행한다.
2. Termux에서 `tcgctl totp admin@example.com`의 이메일을 등록한 주소로 바꿔 실행한다. 이미 **설정 키**가 보이면 그 창에서 이어간다. 같은 A90에서 Google OTP를 쓰는 경우 다음 순서로 등록한다.
   - Termux에서 **설정 키** 옆에 있는 영문·숫자 32자만 길게 눌러 복사한다.
   - 최근 앱으로 Google OTP를 열고 **코드 추가(+) → 설정 키 입력**을 누른다. 계정 이름은 `TCG 허브`, 내 키는 방금 복사한 값, 키 유형은 **시간 기준**으로 설정하고 **추가**를 누른다. 다른 인증 앱의 수동 설정값은 SHA-1, 6자리, 30초다. [Google OTP](https://play.google.com/store/apps/details?id=com.google.android.apps.authenticator2) · [TOTP 규격](https://www.rfc-editor.org/rfc/rfc6238.html)
   - 최근 앱에서 **기존 Termux 창**으로 돌아와 인증 앱의 현재 6자리 숫자를 공백 없이 입력하고 Enter를 누른다. 숫자를 입력하는 동안 화면은 비어 있다. **인증 앱 등록을 마쳤습니다**가 뜨면 완료다. 설정 키와 코드는 기기 안에서만 입력한다.
3. A90의 브라우저로 `http://127.0.0.1:8080/login?to=admin`을 연다. 관리자 이메일과 암호로 로그인하고 **다음 6자리 코드**를 입력한다. 등록 확인에 사용한 코드는 이미 소비됐다. 인증 앱의 시각이 어긋나면 Android의 자동 날짜 및 시간을 확인한다.
4. 인증 앱을 교체하거나 분실하면 기기를 직접 열고 `tcgctl totp admin@example.com --rotate`를 실행한다. 새 앱의 코드 확인과 교체가 성공하면 기존 로컬 관리자 세션이 만료된다. 교체가 취소되거나 코드가 틀리면 기존 앱과 세션을 계속 사용할 수 있다.

공개 HTTPS 배포에서는 Cloudflare Access가 관리자를 인증한다. 로컬 등록 명령은 `http://127.0.0.1:8080` 전용 설치에서만 실행할 수 있다.

### 오프라인 한국어 번역 모델

최초 설치 시 Meta의 M2M100 418M을 INT8로 변환한 모델과 SentencePiece 토크나이저를 받는다. 고정 리비전은 `e205afefce2fd6933a1dca3b92b5063894f2f2bb`이며 네 파일의 합계는 약 496 MB다. 설치기는 파일별 크기와 SHA-256을 확인한 뒤 `/var/lib/tcg-hub/models/m2m100-418m-int8`에 배치한다. 이후 설치에서 같은 파일이 확인되면 기존 모델을 사용한다. CTranslate2와 SentencePiece가 기기 안에서 추론한다. [원본 모델과 언어 목록](https://huggingface.co/facebook/m2m100_418M) · [고정된 INT8 모델](https://huggingface.co/auralmira/m2m100-418M-ct2-int8/tree/e205afefce2fd6933a1dca3b92b5063894f2f2bb) · [MIT 라이선스](../deploy/M2M100-LICENSE.txt)

폰에서 모델을 다운로드하기 어려우면 PC에서 먼저 준비한다. 아래 명령으로 생성한 `m2m100-418m-int8` 폴더를 A90의 `Download/tcg-hub/`로 복사한다.

```bash
python deploy/install-translation-model.py --destination "$HOME/tcg-models/m2m100-418m-int8"
```

A90의 Termux에서 `export TCG_TRANSLATION_MODEL_SOURCE="$HOME/storage/downloads/tcg-hub/m2m100-418m-int8"`를 설정한 뒤 1단계 설치 또는 7단계 업데이트를 진행한다. 전송용 복사본과 설치본을 함께 두는 동안 모델만 약 992 MB를 사용한다. 워커는 기기 전용 저장소의 모델을 읽는다. 릴리스 교체와 DB 백업은 이 파일을 유지하며, 새 기기에서는 동일 리비전을 다시 설치할 수 있다.

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

`tcgctl start`는 실행 중인 Spring이 DB에 연결되고 관리자 인증 모드를 `CLOUDFLARE`로 보고하는지 검사한다. 커넥터가 Cloudflare에 연결되는지도 로컬 지표에서 최대 60초간 확인한다. 처음 활성화할 때 연결에 실패하면 터널을 다시 비활성화하므로 로그와 네트워크를 확인한 뒤 명령을 재실행한다. 앞서 활성화한 터널은 일시적으로 연결이 끊겨도 재접속을 시도한다. 기기 재부팅 후에도 터널 서비스는 같은 원본 검사를 통과한 뒤 연결한다. `tcgctl status`에서 현재 연결을 확인할 수 있다. [커넥터 준비 상태](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/deployment-guides/kubernetes/)

APK의 공개 서버 켜기와 `tcgctl start`는 커넥터 연결 후 실제 공개 HTTPS 주소로 익명 요청을 보낸다. 도감 API의 여섯 종목, 관리자 화면·API의 접근 거부 또는 설정된 Access 로그인 경로, 내부 상태 경로의 접근 거부를 검사한다. 처음 터널을 켜는 중 이 검사가 실패하면 터널을 다시 끈다. 실행 중인 서버를 다시 점검할 때는 A90에서 `tcgctl check-public`을 실행한다. 다른 회선에 있는 PC에서는 저장소 또는 서버 배포본의 `python3 deploy/check-public.py https://cards.example.com your-team.cloudflareaccess.com`으로 동일한 익명 검사를 실행할 수 있다.

Cloudflare가 검사 요청에 브라우저 확인 페이지(`cf-mitigated: challenge`)를 보내면 터널을 유지하고 해당 경로를 수동 확인 대상으로 표시한다. `tcgctl check-public`의 종료 코드 3은 브라우저 확인 대기를 뜻한다. 익명 요청의 401·403 응답만으로는 Cloudflare와 Spring 중 어느 쪽에서 거절했는지 알 수 없다. [Cloudflare 확인 페이지 식별](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/)

최종 확인은 **A90과 다른 휴대전화의 데이터 회선**에서 한다. 공개 주소로 도감을 열고 카드 검색·이미지 표시·PWA 설치를 확인한다. 관리자 경로에서는 허용된 관리자 계정으로 Access와 서비스 로그인을 거친 후 관리 상태를 조회한다. A90 내부의 `http://127.0.0.1:8080/internal/ready`는 HTTP 200이어야 한다.

## 6. 메모리와 서비스 상태

| 항목 | 기본값과 확인 방법 |
| --- | --- |
| Spring | `-Xms256m -Xmx1024m -XX:ActiveProcessorCount=2`, Hikari 최대 4개, Tomcat 최대 16개. RSS에는 힙 외에 스레드·클래스·네이티브 메모리가 포함된다. |
| PostgreSQL | 네이티브·Ubuntu 구성 모두 `shared_buffers=96MB`, `work_mem=2MB`, `maintenance_work_mem=32MB`, 최대 연결 16개, 병렬 쿼리 워커 0개. `work_mem`은 정렬·해시 같은 개별 쿼리 연산에 적용된다. |
| Python | 프로세스 1개에서 도감 작업 1건과 소식 작업 1건을 병행한다. 이미지 처리와 워커 상태 갱신을 담당하는 루프는 유휴 시 최대 10초 간격으로 돈다. 공개 WebP는 `/var/lib/tcg-hub/media`, 비공개 이미지 대기열은 `spool`, 다시 받을 수 있는 원천 자료는 `catalog-cache`에 둔다. |
| 로그 | Termux의 `$PREFIX/var/log/tcg-{db,api,worker,tunnel}/current`. 서비스별 1 MiB 단위·이전 로그 4개 회전. |
| 제어 | `tcgctl status`, `tcgctl maintenance`(DB만 가동), `tcgctl stop`(모두 중지), `tcgctl start`(DB→API→워커·터널). 재부팅 시 마지막 활성화 상태를 복원한다. |

실기기에서는 스프라이트 한 시트를 처리하면서 Termux의 `top`과 Android 설정의 메모리·배터리 사용량을 확인한다. 화면을 끈 상태, Wi-Fi 재연결 후, 재부팅·잠금 해제 후에 외부 카드 조회와 워커 동작을 각각 확인한다. Android 12 이상은 백그라운드 프로세스 수나 CPU 사용량에 따라 Termux 프로세스를 종료할 수 있다. [Android Doze](https://developer.android.com/training/monitoring-device-state/doze-standby) · [Termux Android 12 안내](https://github.com/termux/termux-app#readme)

## 7. 백업·복구·업데이트

백업은 DB 데이터 디렉터리와 독립적인 논리 덤프다. 선택한 서버에 맞는 `pg_dump`와 `pg_restore`를 사용한다. PostgreSQL 18 서버를 Ubuntu 기본 클라이언트 16으로 덤프하면 버전 검사에서 실패한다. PostgreSQL 16에서 만든 덤프를 18로 옮길 때에는 대상에 호환되는 PostGIS를 설치한 뒤 복구한다. 반대 방향의 메이저 버전 다운그레이드는 PostgreSQL이 복원을 보장하지 않는다. 새 엔진에서 PostGIS 버전, 도감 수와 스프라이트를 확인할 때까지 원본 백업을 보관한다. [pg_dump 버전 호환성](https://www.postgresql.org/docs/18/app-pgdump.html#PG-DUMP-NOTES) · [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html)

- **백업** — `tcgctl backup`은 터널·워커·API를 잠시 중지하고 PostgreSQL custom-format dump, 공개 미디어와 미처리 spool, SHA-256 목록을 `$HOME/tcg-backups/<백업명>/`에 만든 뒤 이전 서비스 활성 상태를 복원한다. 백업 중에는 서비스가 잠시 오프라인이다. 덤프에는 계정·콘텐츠와 등록된 TOTP 비밀 키가 포함되므로 기기 밖에 보관할 복사본은 암호화한다. 터널 토큰·DB 비밀번호·JWT 키는 별도로 관리한다.
- **복구** — 새 설치의 4단계에서 `tcgctl install`까지만 실행한다. 백업 디렉터리를 Termux 전용 `$HOME/tcg-backups/`로 옮기고 `tcgctl restore 20261124T120000Z-1234`처럼 실제 백업명을 전달한다. 자신이 생성해 보관한 백업을 사용한다. 복구는 빈 미디어 디렉터리와 아직 Flyway를 실행하지 않은 전용 DB에서 동작한다. 중간에 끊기면 같은 백업명으로 재실행한다. 이어서 `tcgctl start-local`로 카드 수·이미지·계정 및 대기열을 확인하고, 새 토큰을 입력한 뒤 `tcgctl start`로 공개한다.
- **업데이트** — 체크섬을 확인한 새 배포본을 Termux 전용 빈 디렉터리에 풀고, 해당 디렉터리의 `MANIFEST.sha256`도 확인한다. 이전 배포본을 사용 중인 A90의 첫 업데이트에서는 아래 명령으로 실행 중인 서비스에 종료 처리를 먼저 등록한다. 이어 백업과 유지보수 모드를 거쳐 설치한다. 로컬 배포는 `install --local`과 `start-local`을 사용한다. 이미 외부에 공개 중인 배포는 마지막 두 명령을 `tcgctl install`, `tcgctl start`로 바꾼다. 스키마를 변경한 버전의 롤백은 이전 릴리스와 배포 직전 백업을 새 설치에 복원한다.

```bash
export TCG_RELEASE_DIR="$HOME/tcg-release-next"
(cd "$TCG_RELEASE_DIR" && sha256sum --quiet --check MANIFEST.sha256) &&
  install -m 0700 "$TCG_RELEASE_DIR/deploy/tcgctl" "$PREFIX/bin/tcgctl" &&
  tcgctl service-controls &&
  tcgctl backup &&
  tcgctl maintenance &&
  tcgctl install --local &&
  tcgctl start-local
```

`service-controls`는 워커·API·터널 각각의 runit 디렉터리에 종료 처리를 등록한다. `maintenance`와 `backup`은 PRoot 하위에서 실제 실행 중인 서비스 프로세스에 TERM을 전달한 뒤 종료를 기다린다. 워커가 진행 중인 HTTP 요청과 DB 작업을 정리할 수 있도록 최대 180초를 기다린다.

## 8. 자동 수집과 모바일 운영

A90에서 첫 수집이 끝났는지 보려면 Termux에서 `tcgctl media check-catalogs`를 실행한다. 게임마다 자동 수집한 공개 카드 수(`published`), 마지막으로 수집을 마친 시각(`last_success_at`), 현재 상태(`state`)가 표시된다. 여섯 게임 모두 수집 완료 이력과 공개 카드가 있으면 `initial_sync_complete`가 `true`다. 첫 수집 중에는 종료 코드 3을 반환하며 워커는 계속 작업한다. 이후 갱신 상태는 아래 관리자 화면에서 확인한다.

관리자로 로그인해 관리 화면에서 소스별 지난 성공·실패 시각, 실제로 확인한 행 수, 새로 저장한 행 수, 다음 실행 시각을 본다. 지금 실행과 재시도는 큐에 요청을 남긴다. 제공자의 호출 제한이 남아 있으면 그 이후 실행한다. 일시정지는 이미 커밋한 카드와 소식을 유지한다. 긴 도감 수집은 배치 사이에서 중단되고 다음 실행에서 기존 카드 키와 대조한다.

워커 재시작은 DB에 요청을 남기고 실행 중인 워커가 안전한 시점에 종료하면 runit이 새 프로세스를 띄운다. 대량 도감을 받는 동안에도 소식 수집과 heartbeat가 진행된다. 마지막 heartbeat가 오래된 경우 Termux에서 `tcgctl status`와 워커 로그를 확인한다. `tcgctl stop`으로 명시적으로 중단한 서비스는 `tcgctl start`로 다시 활성화한다. Windows에서 포그라운드 서비스를 실행하는 절차는 [Windows 실행 가이드](../deploy/WINDOWS.md)에 있다.

| 소식 출처 | 수집하는 내용 |
| --- | --- |
| 유희왕 | YGOPRODeck 도감에서 새로 등록한 카드·팩을 세 언어로 요약한다. KONAMI 북미 웹 공지는 이용 조건에 따라 자동 조회와 공개를 중지한다. [수집·이력 안내](COLLECTION.md) · [한국 공식 공지](https://www.yugioh.co.kr/board/board_list.php?b_category=notice) · [아시아 공식 공지](https://www.yugioh-card.com/asia/news/) |
| 포켓몬 | 공식 일본어 카드게임 뉴스 목록. 같은 상품의 여러 발표는 제목과 날짜로 구분한다. [포켓몬 카드](https://www.pokemon-card.com/info/) |
| 바이스 슈발츠 | 영어판 공식 공지 RSS의 최근 40개 제목과 원문 링크. [Bushiroad](https://en.ws-tcg.com/information/feed/) |
| 니벨아레나 | 한국어 공식 홈페이지의 공지 목록과 발행사가 직접 올린 일본 게임마켓 부스 공지. 한국어 홈페이지는 공개 HTTP를 사용한다. [한국 공식 공지](http://nivelarena.co.kr/bbs/board.php?bo_table=notice) · [발행사 부스](https://www.gamemarket.jp/booth/blog/5657) |
| 리프트바운드 | Riot 공식 발행 목록에 실린 게임 공지 제목과 발행시각. [Riftbound](https://playriftbound.com/en-us/news/) |

**X 공식 계정**은 X API 접근 권한이 있는 프로젝트의 app-only Bearer Token을 사용한다. A90의 Termux에서 `tcgctl x-token`을 실행해 비밀 입력으로 등록한 후 관리 화면에서 워커를 재시작하고 해당 소스를 재시도한다. 워커는 `/etc/tcg-hub/x.token`을 `X_BEARER_TOKEN`으로 읽는다. 첫 실행은 최근 타임라인 한 페이지를 가져오고 이후 `since_id`와 페이지 토큰으로 중단 지점을 이어 간다. 뉴스에는 계정명, 분류, 게시시각과 원문 링크를 저장한다. 토큰 누락, 이용권한·크레딧 부족, 호출 제한은 해당 소스 상태에 표시된다. [X 계정 타임라인 API](https://docs.x.com/x-api/users/get-posts)

**디시인사이드 TCG 갤러리**는 디시인사이드의 사전 서면 동의가 있을 때 운영한다. 동의 범위에 `tcggame` 목록의 자동 수집이 포함된 경우 Ubuntu의 `/etc/tcg-hub/feeds.env`에 `export DCINSIDE_WRITTEN_PERMISSION=tcggame`을 설정하고 파일 소유자를 `tcgapp`, 모드를 0600으로 지정한다. 워커를 재시작한 뒤 소스를 재시도한다. 수집기는 매회 robots 정책을 확인하고 공개 목록의 게시번호·제목·일시·원문 링크를 저장한다. 기본 검수 상태는 `PENDING`이다. [서비스 이용약관 제16조](https://nstatic.dcinside.com/dc/w/policy/policy_index.html) · [갤러리 robots 정책](https://gall.dcinside.com/robots.txt)

현장에서 소스 하나를 점검할 때는 `tcgctl media check-feed OFFICIAL_NEWS nivel-notice-kr`처럼 실행한다. 이 명령은 실제 한 번의 조회 결과와 첫 원문 링크를 출력한다. 정상적인 예약 수집은 DB 체크포인트·중복 제거·백오프를 적용한다. 이미지 권리가 확인된 운영자 파일은 5단계 `enqueue`로 처리하고, 외부 도감은 출처와 메타데이터를 저장한다.
## 카드 데이터 공급자 설정

배포 환경변수 예시는 [설정 템플릿](../.env.example)에 있다. A90에서는 Ubuntu의 기존 `/etc/tcg-hub/runtime.env`에 필요한 변수만 `export`로 추가한 뒤 워커를 재시작한다. 기존 DB 비밀번호·JWT 키와 파일 권한을 유지한다. `APITCG_API_KEY`, `TRADINGCARDSTUDIO_API_KEY`, `RIOT_API_KEY`, `POKEWALLET_API_KEY`는 해당 공급자의 읽기 권한이 있는 서버 키다. 키가 준비되면 워커가 연결 상태를 갱신하며 관리자 화면의 수집 출처에서 해당 작업을 요청할 수 있다. 등록 여부와 실제 요청 결과는 각각 공급자 상태와 소스의 마지막 성공 시각에서 확인한다.

기본 자동 동기화는 API 응답을 비공개 카탈로그 캐시에 저장하고 HTTP 호출 사이의 지연 및 서버의 재시도 시간을 적용한다. 나무위키는 배포된 출처 색인을 사용하며, 운영자가 검증한 갱신 색인이 있으면 `TCG_WIKI_INDEX_FILE`에 워커가 읽을 수 있는 절대 경로를 설정한다. 주간 작업이 SHA-256이 바뀐 파일을 읽어 같은 인쇄본의 변경 행을 갱신한다.
