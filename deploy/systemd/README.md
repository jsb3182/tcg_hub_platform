# Linux 호스트 부팅 및 서비스 제어

Ubuntu 24.04에서 사용할 수 있는 systemd 구성이다. 앱은 이미 켜져 있는 호스트의 HTTPS 도감에 접속한다. WoL이 켜진 유선 PC는 부팅 후 systemd가 API와 워커를 시작한다. 관리자 요청으로 서비스만 종료해도 호스트, 데이터베이스, 터널은 계속 실행된다.

## 최초 설치

1. 서버 릴리스 압축 파일의 SHA-256을 확인하고 운영자 개인 디렉터리에 푼다. Ubuntu에서 Java 17, PostgreSQL 16·PostGIS, Python 3.12를 설치한다.

   ```bash
   sudo apt-get install openjdk-17-jre-headless postgresql-16 postgresql-16-postgis-3 python3-venv libpq5 curl ca-certificates
   sudo systemctl enable --now postgresql
   sudo -u postgres createuser --pwprompt tcg_app
   sudo -u postgres createdb --owner=tcg_app tcg_hub
   sudo -u postgres psql -v ON_ERROR_STOP=1 -d tcg_hub -c 'CREATE EXTENSION IF NOT EXISTS postgis'
   sudo install -d -m 0750 /etc/tcg-hub
   sudo install -m 0600 /dev/null /etc/tcg-hub/host.env
   sudo install -m 0600 /dev/null /etc/tcg-hub/worker.env
   ```

   위 빈 파일·역할 생성은 새 서버의 최초 1회에만 실행한다. 업그레이드는 기존 설정과 DB를 유지하고 백업을 만든 뒤 3단계부터 실행한다.

2. `sudoedit /etc/tcg-hub/host.env`로 아래 값을 입력한다. 비밀번호와 JWT 키는 호스트마다 생성한다. JWT 키 생성 예시는 `openssl rand -base64 48`이다. `PUBLIC_ORIGIN`에는 공개 HTTPS 호스트를, `CF_TEAM_DOMAIN`과 `CF_AUDIENCE`에는 Cloudflare Access 애플리케이션 값을 사용한다. 로컬 검증은 `PUBLIC_ORIGIN=http://127.0.0.1:8080`과 빈 Access 두 값으로 시작할 수 있다. 호스트 env 파일은 systemd의 `NAME=value` 형식이다.

   ```text
   DB_URL=jdbc:postgresql://127.0.0.1:5432/tcg_hub
   DB_USER=tcg_app
   DB_PASSWORD=<DB 역할 암호>
   JWT_SECRET=<Base64 키>
   PUBLIC_ORIGIN=<플랫폼 주소>
   CF_TEAM_DOMAIN=<팀 도메인>
   CF_AUDIENCE=<AUD>
   MEDIA_ROOT=/var/lib/tcg-hub/media
   SPOOL_ROOT=/var/lib/tcg-hub/spool
   SPRING_FLYWAY_BASELINE_ON_MIGRATE=true
   SPRING_FLYWAY_BASELINE_VERSION=0
   ```

   `sudoedit /etc/tcg-hub/worker.env`에 워커 설정을 넣는다.

   ```text
   PGUSER=tcg_app
   PGPASSWORD=<DB 역할 암호>
   PGHOST=127.0.0.1
   PGPORT=5432
   PGDATABASE=tcg_hub
   MEDIA_ROOT=/var/lib/tcg-hub/media
   SPOOL_ROOT=/var/lib/tcg-hub/spool
   CATALOG_CACHE_ROOT=/var/lib/tcg-hub/catalog-cache
   TCG_TRANSLATION_MODEL=/var/lib/tcg-hub/models/m2m100-418m-int8
   ```

3. 압축을 푼 루트에서 아래 명령으로 설치하고 확인한다. 설치 프로그램은 매니페스트 검증 후 root 소유 릴리스에 가상환경과 고정 번역 모델을 준비한다. Spring은 전용 DB에 Flyway를 적용한다.

   ```bash
   sudo bash deploy/systemd/install-host.sh
   systemctl status tcg-hub-api tcg-hub-worker tcg-hub-control.socket
   curl -fsS http://127.0.0.1:8080/api/v1/games
   ```

4. 공개 시에는 Cloudflare Tunnel의 HTTP origin을 `http://127.0.0.1:8080`으로 설정한다. 관리자 화면, 두 관리자 API 경로, 내부 상태 경로 보호를 구성한다. 앱 **운영 콘솔 열기**에서 로그인과 해당 2차 인증을 완료한다. [터널 및 Access 설정](../../docs/DEPLOYMENT.md)

## 서비스 수명과 복구

앱의 관리자 화면에서 재시작·종료를 승인하면 Spring이 Linux 로컬 소켓에 고정 명령을 보낸다. systemd는 전용 API 계정의 UID를 확인한 뒤 예약 명령을 실행한다. DB와 터널은 별도 단위다. OS가 재부팅되면 API와 워커가 다시 실행된다.

| 작업 | 호스트에서 확인할 내용 |
| --- | --- |
| API 재시작 | `systemctl status tcg-hub-api tcg-hub-worker` 및 도감 응답 |
| 서비스 종료 후 같은 부팅 세션에서 복구 | `sudo systemctl start tcg-hub-api` |
| 서비스 로그 | `journalctl -u tcg-hub-api -u tcg-hub-worker` |
| 에러 또는 중복 작업 | 진행 중 작업이 끝난 뒤 상태를 새로고침 |

서버 전원을 끈 PC는 같은 신뢰 Wi-Fi에서 Android 앱의 **부팅 신호 보내기**를 사용한다. 실제 깨우기 지원 범위는 PC의 UEFI, 유선 랜카드, 대기 전원 및 공유기 브로드캐스트 설정에 따라 결정된다.
