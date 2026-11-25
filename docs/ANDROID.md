# Android에서 TCG 허브 열기와 A90 서버 제어

`TCG 허브` 앱 1.3.2는 방문자가 공개 사이트를 열고 운영자가 A90에서 서버를 설치·관리하는 Android 앱이다. 1.1부터 1.3.1까지의 앱에서 업데이트하면 저장한 주소와 폴더 권한을 이어서 사용한다.

## 다른 휴대폰에서 공개 사이트 열기

1. 운영자가 보내 준 HTTPS 링크를 브라우저에서 열거나, 같은 릴리스의 `tcg-server-control.apk`를 설치해 앱을 연다. [Android APK 다운로드](https://github.com/jsb3182/tcg_hub_platform/releases/latest/download/tcg-server-control.apk)
2. 첫 화면의 **공개 사이트 주소**에 링크를 붙여 넣고 **브라우저로 열기**를 누른다. 앱은 HTTPS 도메인의 첫 화면을 기본 브라우저에 열고 다음 실행을 위해 그 주소만 기억한다. 일반 휴대폰은 Termux 설치나 폴더 권한 없이 쓸 수 있다.
3. A90 운영자는 공개 배포를 설정한 뒤 **A90 서버 관리 → 상태 새로고침 → 공개 주소 복사** 또는 **공개 주소 공유**로 링크를 전달한다. 해당 기기의 배포 모드가 공개로 확인되면 두 버튼이 나타난다.

## PC 없이 처음 설치하거나 로컬 서버 업데이트하기

A90에 Termux를 설치하고 한 번 연다. 첫 설치에서는 Ubuntu와 번역 모델(약 496 MB)을 받으므로 전원과 인터넷 연결을 유지한다. 기존 로컬 서버를 업데이트하면 도우미가 백업을 만들고 새 버전을 시작한다. 이미 외부에 공개한 서버는 공개 설정을 유지하는 업데이트 절차를 따른다. [공개 서버 업데이트](DEPLOYMENT.md#7-백업복구업데이트)

1. A90에 이 릴리스의 APK를 설치하고 **TCG 허브 → A90 서버 관리**를 연다. 새 기기는 **설치 명령 복사**를 누른다. 이전에 제어 폴더를 연결한 기기는 **서버 업데이트 안내 → 업데이트 명령 복사**를 누른다. [APK 다운로드](https://github.com/jsb3182/tcg_hub_platform/releases/latest/download/tcg-server-control.apk)
2. **Termux 열기**를 눌러 터미널에 붙여 넣고 Enter를 누른다. 명령은 설치 도우미와 서버 압축 파일을 각각 앱에 고정된 SHA-256과 대조한 뒤 설치한다. 다운로드나 설치가 중단되면 같은 명령으로 다시 진행한다.
3. 설치 완료 주소가 표시되면 앱으로 돌아와 아래 절차로 제어 폴더를 한 번 연결한다. 이후 서버 시작·중지는 앱에서 할 수 있다. [제어 폴더 연결](#a90-제어-폴더를-처음-연결할-때)

**Termux에서 직접 설치하는 방법**도 있다. A90 브라우저로 사용할 GitHub 릴리스를 열어 같은 태그의 `setup-termux.sh`와 파일의 SHA-256을 확인한다. 아래의 예시는 `a90-2026.11.25.5` 배포본을 휴대폰의 개인 폴더에 받는다. [릴리스 파일](https://github.com/jsb3182/tcg_hub_platform/releases)

```bash
tag=a90-2026.11.25.5
pkg install -y curl coreutils &&
  curl --proto '=https' --proto-redir '=https' -fL --retry 2 \
    "https://github.com/jsb3182/tcg_hub_platform/releases/download/$tag/setup-termux.sh" \
    -o "$HOME/setup-termux.sh" &&
  sha256sum "$HOME/setup-termux.sh"
```

출력된 SHA-256이 릴리스에 표시된 값과 일치하면 아래 명령을 실행한다.

```bash
bash "$HOME/setup-termux.sh" --release a90-2026.11.25.5
```

Termux에서 설치가 끝나면 A90 브라우저로 `http://127.0.0.1:8080/`을 연다. 카드와 소식은 워커가 백그라운드에서 수집한다. `tcgctl media check-catalogs`를 실행하면 다섯 도감에 실제로 저장된 자동 수집 카드 수와 첫 수집 완료 여부를 볼 수 있다. 기존 로컬 배포의 백업은 `$HOME/tcg-backups/`에 보관된다.

## A90 제어 폴더를 처음 연결할 때

1. 최신 서버 배포본으로 A90을 설치 또는 업데이트한다. `tcgctl install`이 Termux 전용 `$HOME/tcg-control` 폴더와 runit 서비스 `tcg-mobile`을 설치한다. 이미 호환되는 서버를 실행 중이라면 검증된 새 배포본을 Termux의 개인 폴더에 풀고 그 디렉터리에서 `bash deploy/install-mobile-control.sh`만 실행해도 된다. Termux를 한 번 열어 둔다.
2. 배포받은 `tcg-server-control.apk`의 SHA-256을 배포자가 제공한 체크섬과 대조하고 A90에서 APK를 연다. Android가 요청하면 해당 파일 앱에 **이 출처 허용**을 승인해 설치한다. 설치 후 이 출처 권한을 해제해도 된다. 이후 같은 서명으로 빌드한 APK를 열면 기존 앱을 업데이트한다.
3. **TCG 허브 → A90 서버 관리 → Termux 제어 폴더 연결**을 누른다. 시스템 파일 선택기에서 **Termux → tcg-control → 이 폴더 사용 → 허용**을 선택한다. 이 폴더의 읽기·쓰기 권한이 서버 제어 권한이다. 앱은 선택한 폴더의 제공자와 경로를 확인한 뒤 접근 권한을 저장한다. 연결 해제는 Android 설정의 앱 정보에서 TCG 허브의 저장 데이터를 지우거나 앱을 삭제한다.

Google Play판 Termux는 Android 문서 제공자 `com.termux.documents`를 공개한다. 이 앱은 시스템 문서 선택기를 통해 그 제공자에 연결한다. 앱 매니페스트의 설치·런타임 권한 목록은 비어 있다. [Google Play판 Termux 매니페스트](https://github.com/termux-play-store/termux-apps/blob/main/termux-app/src/main/AndroidManifest.xml) · [Android 폴더 접근과 권한 유지](https://developer.android.com/training/data-storage/shared/documents-files#grant-access-directory)

## 평소 사용

- **서버 켜기**를 누르면 현재 배포 주소가 표시된다. 로컬 모드에서는 A90 안에서만 시작한다. Cloudflare 공개 배포는 확인 창에 공개할 HTTPS 주소를 보여 주고 `tcgctl start`를 실행한다. 확인한 뒤 배포 모드가 바뀌면 상태를 갱신한 다음 다시 확인한다.
- **서버 끄기**를 확인하면 터널, 워커, 웹 서버, DB가 차례로 종료된다. 이후에도 Termux의 `tcg-mobile`은 제어 요청을 기다리므로 같은 버튼으로 서버를 다시 켤 수 있다. 실행이 오래 걸리면 홈 화면으로 나갔다가 앱을 다시 열어 결과를 확인할 수 있다.
- 관리 화면 오른쪽 위 **상태 새로고침** 버튼으로 각 서비스의 상태를 확인한다. **관리자 화면 열기**는 서버가 응답할 때 설정된 접속 주소의 `/login?to=admin`을 기본 브라우저에서 연다. 기존 계정과 로컬 TOTP 또는 Cloudflare Access로 로그인한다.
- 관리자 계정은 도감 편집과 수집 설정을 맡는 운영자 계정이다. A90 내부에서 처음 등록할 때 정한 비밀번호와 인증 앱에 30초마다 표시되는 6자리 숫자로 로그인한다. [관리자 계정 만들기](DEPLOYMENT.md#a90에서-로컬-관리자-로그인)
- 응답 대기가 끝났다면 A90에서 Termux를 열고 `sv status "$PREFIX/var/service/tcg-mobile"`과 `tcgctl status`를 확인한다. Android에서 Termux를 강제 중지했을 때도 먼저 Termux를 직접 열어 runit을 재개한다.

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
