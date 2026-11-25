# A90에서 TCG 서버 제어

`TCG 서버` 앱에서 로컬 서버나 이미 설정한 Cloudflare 서버를 켜고 끌 수 있다. 상태 화면에는 데이터베이스, 웹 서버, 수집 워커, 터널의 프로세스 상태가 각각 표시된다. 상단의 서버 실행 여부는 내부 웹 서버의 DB 연결 검사 결과다.

## 처음 연결할 때

1. 최신 서버 배포본으로 A90을 설치 또는 업데이트한다. `tcgctl install`이 Termux 전용 `$HOME/tcg-control` 폴더와 runit 서비스 `tcg-mobile`을 설치한다. 이미 호환되는 서버를 실행 중이라면 검증된 새 배포본을 Termux의 개인 폴더에 풀고 그 디렉터리에서 `bash deploy/install-mobile-control.sh`만 실행해도 된다. Termux를 한 번 열어 둔다.
2. 배포받은 `tcg-server-control.apk`의 SHA-256을 배포자가 제공한 체크섬과 대조하고 A90에서 APK를 연다. Android가 요청하면 해당 파일 앱에 **이 출처 허용**을 승인해 설치한다. 설치 후 이 출처 권한을 해제해도 된다. 이후 같은 서명으로 빌드한 APK를 열면 기존 앱을 업데이트한다.
3. **TCG 서버 → Termux 제어 폴더 연결**을 누른다. 시스템 파일 선택기에서 **Termux → tcg-control → 이 폴더 사용 → 허용**을 선택한다. 이 폴더의 읽기·쓰기 권한이 서버 제어 권한이다. 앱은 선택한 폴더의 제공자와 경로를 확인한 뒤 접근 권한을 저장한다. 연결 해제는 Android 설정의 앱 정보에서 TCG 서버의 저장 데이터를 지우거나 앱을 삭제한다.

Google Play판 Termux는 Android 문서 제공자 `com.termux.documents`를 공개한다. 이 앱은 시스템 문서 선택기를 통해 그 제공자에 연결한다. 앱 매니페스트의 설치·런타임 권한 목록은 비어 있다. [Google Play판 Termux 매니페스트](https://github.com/termux-play-store/termux-apps/blob/main/termux-app/src/main/AndroidManifest.xml) · [Android 폴더 접근과 권한 유지](https://developer.android.com/training/data-storage/shared/documents-files#grant-access-directory)

## 평소 사용

- **서버 켜기**를 누르면 현재 배포 주소가 표시된다. 로컬 모드에서는 A90 안에서만 시작한다. Cloudflare 공개 배포는 확인 창에 공개할 HTTPS 주소를 보여 주고 `tcgctl start`를 실행한다. 확인한 뒤 배포 모드가 바뀌면 상태를 갱신한 다음 다시 확인한다.
- **서버 끄기**를 확인하면 터널, 워커, 웹 서버, DB가 차례로 종료된다. 이후에도 Termux의 `tcg-mobile`은 제어 요청을 기다리므로 같은 버튼으로 서버를 다시 켤 수 있다. 실행이 오래 걸리면 홈 화면으로 나갔다가 앱을 다시 열어 결과를 확인할 수 있다.
- **상태 새로고침**으로 현재 상태를 확인한다. **관리자 화면 열기**는 서버가 응답할 때 설정된 접속 주소의 `/login?to=admin`을 기본 브라우저에서 연다. 기존 계정과 로컬 TOTP 또는 Cloudflare Access로 로그인한다.
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

GitHub Releases로 배포할 때는 같은 릴리스에 서명된 APK와 `.sha256` 파일을 각각 첨부하고, 릴리스 설명에 서명 인증서 SHA-256을 기록한다. A90에서는 릴리스의 **Assets**에서 APK를 받을 수 있다. Android SDK가 있는 PC에서는 `apksigner verify --verbose --print-certs tcg-server-control.apk`로 이전에 신뢰한 인증서와 대조한다. [GitHub 릴리스 파일](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
