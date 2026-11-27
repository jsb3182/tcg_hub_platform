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

## 공개 카드 그림 배치

워커는 90초 간격으로 종목별 공개 카드 최대 96장의 인쇄본·언어별 그림 출처를 확인하고, 그 종목에서 대기 중인 그림을 최대 한 장 내려받는다. 기기의 남은 용량이 768 MiB 미만이면 다운로드를 쉰다. 운영 중 한 차례 실행하려면 `python -m tcg_worker cache-card-art --game POKEMON`을 사용한다. 자동 배치와 수동 배치는 같은 데이터베이스 잠금을 사용한다.

원본은 메모리에서 파일 형식과 크기를 검사한다. 단일 프레임의 JPEG·PNG·WebP만 허용하며 입력 상한은 8 MiB, 1,200만 화소다. 최대 480×700 안에서 종횡비를 유지한 WebP(품질 80)를 `MEDIA_ROOT/cards/`에 저장한다. 이미지 경로는 결과 파일의 SHA-256으로 결정한다. 배치는 출처, 원본 SHA-256, 시각 검색용 64비트 해시, 다음 확인 시점을 기록한다. 같은 출처의 여러 인쇄본은 파일을 공유한다. 성공한 원본은 90일 뒤에 다시 확인하며, 서버가 지정한 재시도 간격은 해당 호스트 전체에 반영한다.

브라우저는 해당 그림에 연결된 공개 카드가 있을 때 `/media/cards/<sha256>.webp`를 읽는다. 기존 시트와 업로드한 그림은 `/media/sheets/`에서 계속 제공한다. 캐시 복구 시 데이터베이스와 `MEDIA_ROOT`를 함께 복원한다. 외부 카드 상세 주소는 출처 확인에 사용한다.

## 유희왕 지역별 덱 수량 검증

덱 편집기의 **OCG(일본)**은 2026년 10월 1일 시행한 일본 금제표를, **TCG Advanced**는 10월 19일 시행한 금제표를 기준으로 한다. 한국 OCG는 일본과 적용 카드가 다르다. 적용일은 API의 `effectiveOn`, 공식 원문 링크는 `sourceUrl`에서 확인한다. [일본 OCG 10월 원문](https://www.yugioh-card.com/japan/event/limitregulation/?list=202610) · [TCG Advanced 10월 원문](https://www.yugioh-card.com/en/limited/list_2026-10-19/)

V32의 카드 식별자와 허용 수량은 Project Ignis의 숫자 패스코드와 YAML Yugi의 코나미 카드 ID(CID)를 대조하여 생성했다. 검증일은 2026년 11월 27일이다. 공식 표와 일치한 OCG 금지·제한·준제한 카드는 각각 94·95·13종이고 TCG는 156·93·7종이다. 동일 카드의 다른 그림에 붙은 내부 번호는 한 CID에 한 번만 센다. 공식 NEURON은 운영자의 원문 확인 링크로 제공한다. [Project Ignis 고정 리비전](https://github.com/ProjectIgnis/LFLists/tree/1c126747bf9f424d56df9ec2367e09051bb4872d) · [YAML Yugi 고정 리비전](https://github.com/DawnbrandBots/yaml-yugi/tree/2355f8324797b38596dbf31eb21711f411299882/data/cards)

유희왕 정상 수집은 공개 Project Ignis 지역 파일 두 개를 하루 동안 캐시한다. 배포 때 검증한 SHA-256과 일치하면 파일을 실제 내려받은 날짜로 확인 기록을 갱신한다. 파일 변경·조회 실패·마지막 확인 후 7일 경과 시 `UNAVAILABLE`로 표시하고 이전 판정의 시행일을 유지한다. 변경된 파일은 새 공식 시행일과 **전체** CID·수량을 독립 대조한 후 다음 마이그레이션에 담는다. 이 경로는 공식 사이트에 예약 요청을 보내지 않는다.

덱 미리보기는 메인·엑스트라·사이드에서 같은 카드를 합산한다. 공식 제한표에 없으면 해당 지역 발매일·포맷이 있는 수집 카드 또는 그 CID와 대조된 기존 카드를 확인한다. 개별 카드 확인이 안 되면 `PARTIAL`과 `unknownCardIds`를 반환한다. 지역을 지정한 덱은 금제 위반이나 미확인 항목이 있어도 초안으로 보관할 수 있다. 지역 미지정 덱은 저장 당시의 일반 구성 규칙을 유지한다.

V33부터 정상 유희왕 전체 수집의 마지막 트랜잭션이 한국 수록 번호와 검증한 국내 상품 발매일도 반영한다. 이미 도감을 수집한 A90은 새 버전 설치 후 `tcgctl media seed-ygo-kr-prints`로 기기에 남아 있는 v3 수록 자료를 한 번 읽어 비어 있는 한국 인쇄 색인을 채울 수 있다. 명령은 게임 수집 잠금과 소스 행 잠금을 얻고 앞선 수집 성공을 확인한다. 수집 중이면 정상 수집을 기다린다. 재실행 시 기존 색인을 유지하고 이후 정정·철회는 정상 전체 수집이 적용한다. 이 초기화에는 외부 요청·서비스 재시작이 필요하지 않다. 결과의 `revision`은 사용한 원본 리비전이다. [한국 수록 근거와 자료 이용 조건](../docs/CARD_SOURCES.md#유희왕-한국-수록-근거)
