# 카드 도감 이관과 이미지 워커

여섯 게임의 실데이터 제공자, 언어 범위와 갱신 방식은 [도감 출처](../docs/CARD_SOURCES.md)에서 확인할 수 있다.

Spring Boot가 Flyway 마이그레이션을 마친 후 이 폴더에서 실행한다. Ubuntu에서는 Python 3.12와 PostgreSQL 클라이언트 라이브러리(`libpq5`)를 사용한다. Pillow는 WebP를 지원해야 한다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "from PIL import features; assert features.check('webp')"
```

DB 연결은 배포 환경의 `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` 또는 PostgreSQL URI 형식의 `DATABASE_URL`을 읽는다. `MEDIA_ROOT` 기본값은 `/var/lib/tcg-hub/media`, `SPOOL_ROOT` 기본값은 `/var/lib/tcg-hub/spool`이다. Spring의 `/media/` 경로는 `MEDIA_ROOT`를 제공한다. 같은 서비스 계정으로 두 프로세스를 실행하고 스풀은 웹 공개 경로 밖에 둔다.

## 기존 정적 사이트 가져오기

```sh
.venv/bin/python -m tcg_worker check-legacy /absolute/path/to/legacy-site
.venv/bin/python -m tcg_worker import-legacy /absolute/path/to/legacy-site
```

원본 폴더에는 `js/app.js`, `imgd/`, `pk/`가 있어야 한다. 검사는 데이터 선언의 JSON만 읽고 WebP 파일과 모든 좌표를 확인한다. 제공된 스냅샷은 23개 섹션, 카드 994개, 시트 82개, 고유 배너 11개다. 검사 결과에는 원본 JavaScript와 이미지 매니페스트의 SHA-256이 포함된다. 가져오기는 시트와 배너를 콘텐츠 해시로 복사하고 같은 트랜잭션에서 카드와 변형을 등록한다. 팩 메타데이터에 원본 배너 경로를 유지한다. 같은 스냅샷을 다시 가져와도 기존 카드와 관리자가 바꾼 이미지를 보존한다. 원본이 행 순서를 재배치한 별도 버전이라면 행 순번 기반 키를 먼저 대조해야 한다.

기존 유희왕 시트에서 사용 중인 950개 좌표를 판독한 결과는 일본어 892개, 영어 57개, 미확인 1개다. 도감과 솔로 연습 API는 이미지의 WebP 해시와 행·열이 일치할 때 해당 그림의 `image.language`를 반환한다. 워커는 공개 셀만 남겨 재패킹할 때 실제 복사한 셀의 판독값을 새 시트로 옮긴다. 다른 이미지로 교체하면 새 이미지의 해시와 좌표를 기준으로 다시 조회한다.

한국어명이 비어 있으면 원어명을 표시한다. 한국 발매 예정 문구와 정확한 일본 발매일은 구분하여 보존한다. 카드별 표기, 효과, 게임별 필드, 같은 이미지 좌표를 공유하는 레어도와 추가 아트도 유지한다. 원래 시트 연결이 없는 90개 항목은 좌표를 NULL로 두고 이후 같은 변형에 이미지를 등록할 수 있다. 그중 별도 이미지 참조가 남은 항목은 검사·가져오기 결과의 `unresolved_images`에서 섹션 ID, 항목 키, 누락 이유를 확인할 수 있다.

## 이미지 등록과 배치 실행

```sh
# 첫 인자는 card_variant.id다. 서비스 계정에서 읽을 수 있는 파일을 지정한다.
.venv/bin/python -m tcg_worker enqueue 27 /absolute/path/to/card.jpg
.venv/bin/python -m tcg_worker once
# 상시 운영
.venv/bin/python -m tcg_worker run
```

- JPEG, PNG, WebP 확장자와 실제 이미지 포맷을 함께 확인한다. 파일 한도는 8 MiB, 디코딩 한도는 1,200만 화소, 입력은 한 프레임이다. EXIF 방향을 적용하고 비율을 유지해 300×438 셀에 맞춘다.
- 공개 시트에는 `PUBLISHED` 카드만 넣는다. 큐 등록과 시트 작성 시 각각 게시 상태를 확인하므로 대기 중 비공개 처리한 카드는 `FAILED`가 된다. 2단계 관리자 검수용 미리보기는 별도 비공개 저장소에 둬야 한다. 이미 배포된 카드의 이미지를 철회할 때는 남은 카드로 시트를 다시 만들고 이전 URL과 캐시를 회수해야 한다.
- `enqueue`는 정규화된 PNG 한 장만 비공개 스풀에 기록하고 DB 작업 ID를 출력한다. 같은 변형에 직전에 넣은 이미지와 셀 내용이 같으면 기존 작업 ID를 반환한다. 실패한 작업에는 같은 입력을 다시 넣을 수 있다.
- `once`는 최대 12개를 4열×3행으로 합쳐 품질 80의 WebP 한 장을 발행한다. 1~11개도 즉시 처리한다. `run`은 큐가 비면 `WORKER_POLL_SECONDS`초(기본 15초) 대기한다. API는 0부터 시작하는 열과 행을 사용한다.
- 최종 파일이 완성된 후 시트 ID·좌표·작업 완료를 한 트랜잭션으로 기록한다. 중단되면 PostgreSQL이 잠금을 해제하고 다음 실행이 대기 중인 작업을 다시 처리한다. 완료된 작업의 스풀 정리는 재시작 후에도 이어진다. 스풀을 잃은 작업은 `FAILED`로 표시하며 같은 배치의 정상 파일은 처리한다. DB 트랜잭션 밖에 남은 미참조 파일은 서비스 중단 후 백업·정리할 수 있다.

## 검증

```sh
.venv/bin/python -m unittest discover -v -s tests
```

PostGIS가 이미 설치된 **전용 테스트 DB**의 DSN을 `TCG_TEST_DSN`으로 지정하면 임시 스키마를 만들어 DB 연동 테스트도 수행한다. `TCG_TEST_LEGACY`에 원본 폴더 경로를 지정하면 두 번 가져온 후의 카드·변형 수와 미디어 파일을 검증한다.
