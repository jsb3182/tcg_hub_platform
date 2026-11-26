# Windows에서 API와 워커 실행

Windows에서는 준비된 PostgreSQL·PostGIS에 연결해 압축 해제한 릴리스의 Spring API와 수집 워커를 한 PowerShell 창에서 실행할 수 있다. Galaxy A90에서 실행하려면 [Termux·Ubuntu 배포 가이드](../docs/DEPLOYMENT.md)를 따른다.

이미 A90에서 구동 중인 도감을 PC 브라우저로 조회하려면 [Windows PC에서 USB로 A90 도감 열기](../docs/ANDROID.md#windows-pc에서-usb로-a90-도감-열기)를 따른다.

## 준비

PowerShell 5.1 이상, JDK 17 이상, Python 3.10 이상을 준비한다. 릴리스를 매번 새 디렉터리에 풀고 배포본의 `crawler-middleware/requirements.txt`를 해당 Python 환경에 설치한다. Windows에서 시스템 libpq를 별도로 설치하지 않은 경우 바이너리 패키지를 함께 설치할 수 있다.

```powershell
$release = 'D:\tcg\release-01'
$venv = 'D:\tcg\runtime\.venv'
py -3 -m venv $venv
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install -r (Join-Path $release 'crawler-middleware\requirements.txt') 'psycopg[binary]>=3.2,<4'
```

한국어 번역 모델을 릴리스 바깥의 재사용 가능한 폴더에 설치한다. 최초 다운로드 크기는 약 496 MB다. 워커와 같은 PowerShell에서 환경 변수를 설정한다. 이미 받은 네 파일이 다른 폴더에 있다면 설치기에 `--source 'D:\tcg\model-transfer'`를 추가한다.

```powershell
$env:TCG_TRANSLATION_MODEL = 'D:\tcg\runtime\models\m2m100-418m-int8'
& $python (Join-Path $release 'deploy\install-translation-model.py') --destination $env:TCG_TRANSLATION_MODEL
```

설치기는 리비전 `e205afefce2fd6933a1dca3b92b5063894f2f2bb`의 SHA-256을 확인한다. M2M100의 INT8 가중치와 SentencePiece를 사용하는 CPU 번역은 인터넷 연결 없이 실행된다. [모델 출처](https://huggingface.co/auralmira/m2m100-418M-ct2-int8/tree/e205afefce2fd6933a1dca3b92b5063894f2f2bb) · [MIT 라이선스](M2M100-LICENSE.txt)

이미 PostGIS 확장을 설치한 전용 DB와 마이그레이션 권한이 있는 계정을 사용한다. API와 워커에는 같은 DB와 미디어 루트를 지정한다. 워커 이미지를 임시 보관할 폴더는 미디어 루트와 서로 겹치지 않는 절대 경로여야 한다.

새 전용 DB의 `public` 스키마에 PostGIS만 설치했다면 최초 실행 전에 같은 PowerShell에서 `$env:SPRING_FLYWAY_BASELINE_ON_MIGRATE='true'`, `$env:SPRING_FLYWAY_BASELINE_VERSION='0'`을 설정한다. Flyway는 버전 0을 기준으로 V1부터 적용한다.

| 환경 변수 | 용도 |
| --- | --- |
| `DB_URL`, `DB_USER`, `DB_PASSWORD` | API의 PostgreSQL JDBC URL, DB 계정, 비밀번호 |
| `PGHOST`, `PGPORT`, `PGDATABASE` | 같은 DB에 대한 워커의 libpq 연결 설정 |
| `PGUSER`, `PGPASSWORD` | 별도의 워커 계정을 사용할 때 지정한다. 기본값은 API의 DB 계정과 비밀번호다. |
| `MEDIA_ROOT`, `SPOOL_ROOT` | WebP 저장소와 비공개 작업 디렉터리의 Windows 절대 경로 |
| `TCG_TRANSLATION_MODEL` | 검증한 한국어 번역 모델 디렉터리의 Windows 절대 경로 |
| `JWT_SECRET` | 32바이트 이상 랜덤 키의 Base64 값 |
| `PUBLIC_ORIGIN` | 브라우저가 사용한 정확한 오리진. 로컬 기본값 예시는 `http://localhost:8080`이다. |
| `PORT` | API의 루프백 포트. 기본값은 8080이다. |
| `CF_TEAM_DOMAIN`, `CF_AUDIENCE` | 관리자용 Cloudflare Access 애플리케이션 값 |
| `X_BEARER_TOKEN` | X API 사용 권한이 있을 때 워커에 전달할 토큰 |

비밀번호·JWT 키·X 토큰은 프로세스 환경을 통해 전달한다. 공유 스크립트나 명령행 인수에 비밀값을 저장하지 않는다. 외부에서 접속할 때는 A90 가이드와 동일하게 터널 및 Access 정책을 구성하고 `PUBLIC_ORIGIN`에 실제 HTTPS 주소를 지정한다.

## 실행과 종료

```powershell
& (Join-Path $release 'deploy\windows-run.ps1') -ReleasePath $release -Java java.exe -Python $python
```

API가 DB 준비 상태를 보고한 뒤 워커를 시작한다. 관리자 화면에서 워커 재시작을 요청하면 워커는 현재 작업을 마치고 종료하며 감독 프로세스가 다시 띄운다. 워커 오류 종료 후에는 10초 동안 기다린다. 실행 중인 API가 종료되면 워커도 정리하고 두 서비스를 다시 시작한다. 초기 API 기동 실패나 DB 준비 시간 초과 시 스크립트가 오류로 종료된다. 느린 마이그레이션에는 `-StartupTimeoutSeconds`를 지정할 수 있다.

같은 창에서 Ctrl+C를 누르면 API와 워커의 프로세스 트리가 종료된다. Windows 가상환경 실행기가 별도로 시작한 Python 인터프리터도 함께 정리된다. 콘솔에는 PID·준비 상태·종료 코드가 나타난다.
