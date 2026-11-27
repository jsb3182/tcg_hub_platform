# Android 플랫폼과 서버 운영

`TCG 허브` 2.0.12는 Android 9 이상에서 카드 도감·바인더·덱·연습·소식·매장을 앱 안에 연다. 앱 아이콘으로 다시 열면 마지막에 직접 열었던 플랫폼으로 돌아간다.

**내 덱 → 새 덱 만들기 → 전체 레시피 캡처**에서 Android 파일 선택기로 레시피를 고른다. 분석 후 후보를 확인하고 원하는 덱으로 저장한다. A90에서 덱이나 팩의 **PNG 저장 → 갤러리에 저장**을 고르면 그림이 갤러리의 **TCG Hub** 앨범(`Pictures/TCG Hub`)에 들어간다. **폴더 선택**으로 다운로드 등 다른 위치를 고를 수도 있다. Android 9에서는 파일 선택기가 바로 열린다. 내 덱 목록의 **JSON**·**Excel**도 Android 파일 선택기로 저장한다. [캡처 형식과 인식 범위](RECIPE_CAPTURE.md)

**발매 일정 → 내 일정**에서 로그인하고 개인 일정을 추가한다. 기기로 알림을 받으려면 알림 시간을 선택해 일정을 저장한 다음 **캘린더로 내보내기**를 누른다. Android 파일 선택기에서 `.ics`를 저장하고, 기기 캘린더 앱의 가져오기 기능으로 파일을 연다. 해당 앱에서 알림 권한과 가져온 일정을 확인한다.

- **서버를 운영하는 A90**에서 제어 폴더를 연결하고 **카드 플랫폼 열기**로 로컬 도감을 한 번 열면 다음 실행에도 그 도감이 열린다. 이후 **플랫폼 연결**에서 공개 HTTPS 주소를 직접 열면 그 주소를 기억한다. 2.0.4에서 처음 업데이트할 때는 기존에 저장한 공개 주소를 우선한다. 공개 주소를 저장하지 않은 A90은 제어 폴더 권한이 유효하면 기존에 확인한 공개 서버 주소 또는 로컬 도감을 연다.
- **일반 방문자**는 처음 실행할 때 **플랫폼 연결**에 운영자가 알려 준 HTTPS 주소를 입력한다. 다음 실행에는 저장한 사이트가 열린다.
- 서버가 꺼져 있으면 **플랫폼에 연결할 수 없습니다**가 표시된다. A90에서는 **연결 설정 → A90 서버 관리 → 서버 켜기**를 누른 뒤 다시 도감을 연다. 연결만 잠시 끊겼다면 **다시 시도**를 누른다. 로컬 도감을 쓰다가 제어 폴더 권한을 해제한 경우에는 **플랫폼 연결**에서 폴더를 다시 연결할 수 있다.

## 다른 휴대폰에서 공개 사이트 열기

1. 운영자가 보내 준 HTTPS 링크를 브라우저에서 열거나, 같은 릴리스의 `tcg-server-control.apk`를 설치해 앱을 연다. [Android APK 다운로드](https://github.com/jsb3182/tcg_hub_platform/releases/latest/download/tcg-server-control.apk)
2. 첫 화면의 **공개 사이트 주소**에 링크를 붙여 넣고 **플랫폼 열기**를 누른다. 주소를 저장하면 다음 실행부터 해당 플랫폼이 열린다. 상단 뒤로 버튼에서 연결 주소를 변경할 수 있다. 상단 브라우저 버튼은 파일 내보내기나 외부 로그인이 필요할 때 사용한다. 일반 휴대폰은 Termux 설치나 폴더 권한 없이 쓸 수 있다.
3. A90 운영자는 공개 배포를 설정한 뒤 **A90 서버 관리 → 상태 새로고침 → 공개 주소 복사** 또는 **공개 주소 공유**로 링크를 전달한다. 해당 기기의 배포 모드가 공개로 확인되면 두 버튼이 나타난다.

## 원격 서버와 PC 전원

1. 플랫폼 주소를 저장한 뒤 **연결 설정 → 원격 서버**를 연다. **연결 확인**은 저장한 HTTPS 서버의 도감 API를 검사한다. 상시 구동 중인 서버에는 앱 실행 시 바로 접속한다.
2. **운영 콘솔 열기**는 같은 서버의 관리자 화면을 기본 브라우저에 연다. 관리자 로그인과 설정된 Cloudflare Access 또는 로컬 2차 인증을 마친 뒤 동기화, 수집 시작·중지, 일정 일시정지·재개, 상태 조회를 쓴다. Linux 관리 소켓을 설치하면 서버 재시작과 서비스 종료도 사용할 수 있다. [Linux 호스트 설치](../deploy/systemd/README.md)
3. PC 전원 켜기를 사용하려면 PC의 UEFI와 유선 랜카드에서 Wake-on-LAN 및 종료 상태 깨우기를 활성화한다. 대기 전원, 유선 연결, 무선·유선 사이 브로드캐스트 허용이 필요하다. PC와 같은 신뢰 Wi-Fi에서 **대상 PC 설정**을 열어 유선 MAC 주소를 저장한다. **부팅 신호 보내기**에서 현재 네트워크와 대상을 확인한다.
4. 앱은 활성 Wi-Fi의 등록된 IPv4 서브넷에 UDP 9 패킷을 한 번 보내고 최대 2분 동안 도감 API를 확인한다. **서버 응답 중**은 API가 응답한 시점을 의미한다. 셀룰러·VPN이나 다른 서브넷에서는 부팅 요청을 보낼 수 없다. 공유기 포트포워딩은 사용하지 않는다. 종료된 PC는 부팅 시 systemd를 통해 서버를 시작한다. 전원이 켜진 Linux에서 서비스만 종료한 경우 담당자가 `sudo systemctl start tcg-hub-api`로 복구한다.

안드로이드 WebView는 사용자가 정한 단일 origin과 정해진 카드·지도 리소스만 사용한다. 웹 문서에 네이티브 명령·파일·Termux 권한을 제공하지 않는다. A90에서 **A90 서버 관리 → 카드 플랫폼 열기**를 선택하면 제어 폴더가 확인한 로컬 플랫폼도 앱 안에서 열린다.

## PC 없이 처음 설치하거나 로컬 서버 업데이트하기

A90에 Termux를 설치하고 한 번 연다. 첫 설치에서는 Ubuntu와 번역 모델(약 496 MB)을 받으므로 전원과 인터넷 연결을 유지한다. 기존 로컬 서버를 업데이트하면 도우미가 백업을 만들고 새 버전을 시작한다. 이미 외부에 공개한 서버는 공개 설정을 유지하는 업데이트 절차를 따른다. [공개 서버 업데이트](DEPLOYMENT.md#7-백업복구업데이트)

1. A90에 이 릴리스의 APK를 설치하고 **TCG 허브 → A90 서버 관리**를 연다. 새 기기는 **설치 명령 복사**를 누른다. 이전에 제어 폴더를 연결한 기기는 **서버 업데이트 안내 → 업데이트 명령 복사**를 누른다. [APK 다운로드](https://github.com/jsb3182/tcg_hub_platform/releases/latest/download/tcg-server-control.apk)
2. **Termux 열기**를 눌러 터미널에 붙여 넣고 Enter를 누른다. 명령은 설치 도우미와 서버 압축 파일을 각각 앱에 고정된 SHA-256과 대조한 뒤 설치한다. 다운로드나 설치가 중단되면 같은 명령으로 다시 진행한다.
3. 설치 완료 주소가 표시되면 앱으로 돌아와 아래 절차로 제어 폴더를 한 번 연결한다. 이후 서버 시작·중지는 앱에서 할 수 있다. [제어 폴더 연결](#a90-제어-폴더를-처음-연결할-때)

**Termux에서 직접 설치하는 방법**도 있다. A90 브라우저로 사용할 GitHub 릴리스를 열어 같은 태그의 `setup-termux.sh`와 파일의 SHA-256을 확인한다. 아래의 예시는 `a90-2026.11.28.3` 배포본을 휴대폰의 개인 폴더에 받는다. [릴리스 파일](https://github.com/jsb3182/tcg_hub_platform/releases)

```bash
tag=a90-2026.11.28.3
pkg install -y curl coreutils &&
  curl --proto '=https' --proto-redir '=https' -fL --retry 2 \
    "https://github.com/jsb3182/tcg_hub_platform/releases/download/$tag/setup-termux.sh" \
    -o "$HOME/setup-termux.sh" &&
  sha256sum "$HOME/setup-termux.sh"
```

출력된 SHA-256이 릴리스에 표시된 값과 일치하면 아래 명령을 실행한다.

```bash
bash "$HOME/setup-termux.sh" --release a90-2026.11.28.3
```

Termux에서 설치가 끝나면 A90 브라우저로 `http://127.0.0.1:8080/`을 연다. 카드와 소식은 워커가 백그라운드에서 수집한다. `tcgctl media check-catalogs`를 실행하면 여섯 도감에 실제로 저장된 자동 수집 카드 수와 첫 수집 완료 여부를 볼 수 있다. 기존 로컬 배포의 백업은 `$HOME/tcg-backups/`에 보관된다.

## Windows PC에서 USB로 A90 도감 열기

USB 케이블을 연결한 동안 PC 브라우저에서 A90의 공개 도감·소식·지도를 볼 수 있다. A90 자체의 주소는 `http://127.0.0.1:8080/`이다. 로컬 회원가입·로그인, 바인더·덱 저장과 관리자 인증은 A90에서 진행한다.

1. A90에서 로컬 서버를 켜고 폰 브라우저에서 도감이 열리는지 확인한다. 신뢰하는 Windows PC에 Android SDK Platform-Tools를 준비하고, A90의 개발자 옵션에서 **USB 디버깅**을 켠다. 데이터 전송이 가능한 USB 케이블로 연결한 뒤 A90에서 이 PC의 디버깅을 허용한다. [공식 다운로드](https://developer.android.com/tools/releases/platform-tools) · [Android USB 연결 및 포트 전달](https://developer.android.com/tools/adb#forwardports)
2. Windows PowerShell에서 서버 배포본을 푼 폴더 또는 저장소 루트를 열고 아래 명령을 실행한다. 서버가 준비되면 기본 브라우저에 도감이 열린다. [PC 연결 스크립트](../deploy/open-a90.ps1)

   ```powershell
   .\deploy\open-a90.ps1
   ```

기본 PC 주소는 [127.0.0.1:18085](http://127.0.0.1:18085/)이다. 케이블을 다시 연결했을 때도 같은 명령을 쓴다. 도우미는 실행 중인 ADB와 기존 USB 연결을 확인한다. A90이 여러 대면 표시된 일련번호 중 사용할 기기를 `-Serial`로 고른다. PC 포트가 이미 다른 용도라면 `.\deploy\open-a90.ps1 -Port 18086`처럼 빈 포트를 지정한다.

Windows PowerShell에서 로컬 스크립트 실행이 꺼져 있으면, 검증한 배포 폴더에서 `powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\deploy\open-a90.ps1`로 이번 실행에만 적용한다.

별도 ADB를 쓰는 환경은 `-AdbPort 5065` 또는 `-AdbPath 'C:\Android\platform-tools\adb.exe'`로 지정한다. 지정한 포트에 ADB 서버가 이미 있으면 그 실행 파일을 사용한다. 연결만 검사하려면 `-NoBrowser`를 붙인다. A90이 보이지 않으면 데이터 케이블과 휴대폰의 USB 디버깅 승인 여부를 확인한다.

## A90 제어 폴더를 처음 연결할 때

1. 최신 서버 배포본으로 A90을 설치 또는 업데이트한다. `tcgctl install`이 Termux 전용 `$HOME/tcg-control` 폴더와 runit 서비스 `tcg-mobile`을 설치한다. 이미 호환되는 서버를 실행 중이라면 검증된 새 배포본을 Termux의 개인 폴더에 풀고 그 디렉터리에서 `bash deploy/install-mobile-control.sh`만 실행해도 된다. Termux를 한 번 열어 둔다.
2. 배포받은 `tcg-server-control.apk`의 SHA-256을 배포자가 제공한 체크섬과 대조하고 A90에서 APK를 연다. Android가 요청하면 해당 파일 앱에 **이 출처 허용**을 승인해 설치한다. 설치 후 이 출처 권한을 해제해도 된다. 이후 같은 서명으로 빌드한 APK를 열면 기존 앱을 업데이트한다.
3. **TCG 허브 → A90 서버 관리 → Termux 제어 폴더 연결**을 누른다. 시스템 파일 선택기에서 **Termux → tcg-control → 이 폴더 사용 → 허용**을 선택한다. 이 폴더의 읽기·쓰기 권한이 서버 제어 권한이다. 앱은 선택한 폴더의 제공자와 경로를 확인한 뒤 접근 권한을 저장한다. 연결 해제는 Android 설정의 앱 정보에서 TCG 허브의 저장 데이터를 지우거나 앱을 삭제한다.

Google Play판 Termux는 Android 문서 제공자 `com.termux.documents`를 공개한다. 이 앱은 시스템 문서 선택기를 통해 그 제공자에 연결한다. 앱의 네트워크 권한은 `INTERNET`, `ACCESS_NETWORK_STATE`다. [Google Play판 Termux 매니페스트](https://github.com/termux-play-store/termux-apps/blob/main/termux-app/src/main/AndroidManifest.xml) · [Android 폴더 접근과 권한 유지](https://developer.android.com/training/data-storage/shared/documents-files#grant-access-directory)

## 기존 관리자의 비밀번호 변경과 인증 앱 등록

1. 로컬 서버가 실행 중일 때 **A90 서버 관리 → 비밀번호 변경·인증 앱 등록 → Termux에서 시작**을 누른다. 연결한 A90의 제어 서비스가 전용 설정 세션 하나를 연다. 이메일과 비밀번호, 인증 앱의 설정 키와 코드는 Termux 창에서만 입력하거나 확인한다.
2. `관리자 이메일:`에 기존 계정의 이메일을 입력한다. `1`을 선택하면 현재 비밀번호, 새 비밀번호, 새 비밀번호 확인을 차례로 묻는다. 비밀번호 입력 중에는 글자가 보이지 않는다. `Password changed.`가 비밀번호 변경 성공을 뜻한다. 비밀번호 변경을 이미 마쳤다면 `2`를 선택한다.
3. 인증 앱에서 **시간 기반**을 선택하고 Termux에 표시된 설정 키를 등록한 뒤, 인증 앱의 6자리 숫자를 Termux에 입력한다. `인증 앱 등록을 마쳤습니다`가 나오면 앱의 **관리자 화면 열기**에서 로그인하고 다음 6자리 코드를 사용한다. 이미 등록한 인증 앱이 있으면 그대로 사용한다.

Termux에 `Max terminal sessions reached`가 나오거나 10초가 지나도 `관리자 이메일:`이 나타나지 않으면 앱으로 돌아가 **비밀번호 변경·인증 앱 등록 → 명령 복사**를 누른다. Termux에서 입력을 기다리는 `$` 프롬프트에 `tcgctl admin-setup`을 붙여 넣고 Enter를 누른다. 이미 실행 중인 설정 창이 있다면 그 창에서 계속한다. 구버전 서버는 **비밀번호 명령 복사**, **인증 앱 명령 복사**를 표시한다. 복사한 명령 뒤에 공백과 본인 이메일을 넣어 각각 실행한다.

## 평소 사용

- **서버 켜기**를 누르면 현재 배포 주소가 표시된다. 로컬 모드에서는 A90 안에서만 시작한다. Cloudflare 공개 배포는 확인 창에 공개할 HTTPS 주소를 보여 주고 `tcgctl start`를 실행한다. 확인한 뒤 배포 모드가 바뀌면 상태를 갱신한 다음 다시 확인한다.
- **서버 끄기**를 확인하면 터널, 워커, 웹 서버, DB가 차례로 종료된다. 이후에도 Termux의 `tcg-mobile`은 제어 요청을 기다리므로 같은 버튼으로 서버를 다시 켤 수 있다. 실행이 오래 걸리면 홈 화면으로 나갔다가 앱을 다시 열어 결과를 확인할 수 있다.
- 관리 화면 오른쪽 위 **상태 새로고침** 버튼으로 각 서비스의 상태를 확인한다. **관리자 화면 열기**는 서버가 응답할 때 설정된 접속 주소의 `/login?to=admin`을 기본 브라우저에서 연다. 기존 계정과 로컬 TOTP 또는 Cloudflare Access로 로그인한다.
- 관리자 계정은 도감 편집과 수집 설정을 맡는 운영자 계정이다. A90 내부에서 처음 등록할 때 정한 비밀번호와 인증 앱에 30초마다 표시되는 6자리 숫자로 로그인한다. [관리자 계정 만들기](DEPLOYMENT.md#a90에서-로컬-관리자-로그인)
- 상태 조회가 60초 안에 끝나지 않으면 앱은 대기를 해제하고 **상태 새로고침**, **서버 켜기**, **서버 끄기**를 다시 활성화한다. 상태를 모를 때의 켜기는 로컬 모드만 요청한다. 앱이 계속 제어 폴더에 접근하지 못하면 A90의 기존 Termux 창에서 `tcgctl status`로 확인한다. 로컬 서버를 재시작하려면 같은 창에서 `tcgctl stop && tcgctl start-local`을 실행한다. Android에서 Termux를 강제 중지했을 때는 먼저 Termux를 직접 열어 runit을 재개한다.

제어 서비스는 Android 앱이 만든 고정된 요청 이름만 처리한다. 폴더에는 상태와 접속 주소가 기록된다. 중복 요청은 기존 응답을 사용하고 90초가 지난 미처리 요청은 만료된다. 명령 실행 중 제어 서비스가 재시작되면 앱에서 상태를 새로고침한다. 리스너는 Termux 개인 폴더의 파일 변경을 기다린다.

## Windows에서 APK 빌드

JDK 17과 Android SDK의 `platforms;android-35`, `build-tools;35.0.0`을 설치한다. PowerShell에서 저장소 루트 기준으로 실행한다.

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:ANDROID_SDK_ROOT = "$env:LOCALAPPDATA\Android\Sdk"
.\android\build.ps1
```

APK와 해시 파일은 `dist/tcg-server-control.apk`, `dist/tcg-server-control.apk.sha256`에 생성된다. 빌드 마지막에 APK 서명 검증 결과와 인증서 SHA-256을 출력한다. `-SigningDirectory`로 지정한 디렉터리 또는 기본 `%LOCALAPPDATA%\TCG-Hub\signing`에서 서명키를 재사용한다. 이 디렉터리는 현재 Windows 사용자에게만 접근을 허용하며 키 암호는 Windows DPAPI로 보호한다. 같은 Windows 계정·프로필과 기존 서명키가 있어야 기본 업데이트 경로를 유지할 수 있다. 서명키나 암호 파일은 공개 배포물에 포함하지 않는다.

새 APK를 배포할 때는 서버 압축 파일을 먼저 완성하고 해당 태그와 SHA-256을 Android 빌드에 반영한다. 같은 릴리스에 설치 도우미, 서버 배포본, 서명된 APK와 체크섬을 올리고 릴리스 설명에 서명 인증서 SHA-256을 기록한다. A90에서는 릴리스의 **Assets**에서 APK를 받을 수 있다. Android SDK가 있는 PC에서는 `apksigner verify --verbose --print-certs tcg-server-control.apk`로 이전에 신뢰한 인증서와 대조한다. [GitHub 릴리스 파일](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
