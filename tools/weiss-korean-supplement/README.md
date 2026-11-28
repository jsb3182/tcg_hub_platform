# 바이스 슈발츠 영문판 390장의 한국어 참고명

이 도구는 2.0.19의 바이스 번역 메모를 적용한 뒤에도 한국어 이름이 비어 있는 영문 인쇄본 390장에 참고명을 채운다. 서로 다른 인쇄번호에 같은 이름이 실린 경우가 있어 고유 번역은 372개다. 화면에서는 자동 번역(`MACHINE_TRANSLATION`)으로 표시한다. 한국어판 수록 여부와 인쇄면의 언어는 기존 도감 정보를 따른다.

## 수록 내용과 근거

한 줄에 인쇄본 하나를 기록한 [readings.jsonl](readings.jsonl)에서 번호, 영문명, 한국어 참고명, 정확한 상품명, 부시로드의 인쇄번호별 링크와 대조 근거를 볼 수 있다. 영문 번호와 상품명은 [영문 도감 고정판 f0868c5](https://github.com/CCondeluci/WeissSchwarz-ENG-DB/tree/f0868c5ffdef7b396ae2e4ed23274a09a9175319)를 기준으로 했다. 예를 들어 `5HY/W101-E067`의 “Gentle Teasing, Ichika Nakano”는 “가벼운 놀림, 나카노 이치카”로 읽을 수 있다. [해당 영문 인쇄본](https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno=5HY%2FW101-E067)

| 참고명의 근거 | 인쇄본 | 확인 범위 |
|---|---:|---|
| BanG Dream!의 동일 캐릭터·동일 게임 카드 | 200 | 캐릭터 ID, 게임 카드 ID, 영어 제목과 한국어 제목 |
| BanG Dream!의 동일 캐릭터 | 37 | 캐릭터 표기는 게임 자료와 대조하고 앞의 수식어는 영어에서 번역 |
| 블루 아카이브 | 48 | 캐릭터 ID, 성을 포함한 이름과 의상 표기를 고정 자료에서 대조. 23장은 국내 니벨아레나 인쇄물에서 이름도 확인 |
| 니케 | 10 | 부시로드의 영문·한국어 소개에서 인물 표기를 대조하고 수식어는 영어에서 번역 |
| 기존 작품별 인명 사전 | 41 | 해당 작품 안의 인물과 원문 수식어를 조합 |
| 여러 인물이 등장하는 제목 | 4 | 각 인물을 작품별로 대조 |
| 영어 제목 전체를 번역 | 50 | 영문 인쇄명을 직접 옮긴 참고명 |

캐릭터와 게임 내 카드 표기는 각 작품 자료에서 확인했다. 이 자료가 뒷받침하는 범위는 개별 행의 `evidence`에 기록했다. [Bestdori 캐릭터 목록](https://bestdori.com/api/characters/all.2.json) · [Bestdori 게임 카드 목록](https://bestdori.com/api/cards/all.3.json) · [블루 아카이브 캐릭터 고정판](https://github.com/ba-archive/blue-archive/blob/e062cf0e4a5a1d8d59762624a80408e0e68cee43/apps/blue-archive-story-viewer/public/config/yaml/students.yaml) · [부시로드 한국어 니케 소개](https://ws-tcg.com/ex/nik_kr/) · [영문 소개](https://en.ws-tcg.com/ex/nik_en/) · [작품별 인명 자료와 적용 기준](../../docs/CARD_SOURCES.md)

## 적용

2.0.19 워커의 Python 환경과 V61 이상 데이터베이스가 필요하다. 먼저 영문 도감을 수집하고 기본 메모를 적용한다. 출력의 `missingFullMemoOrDifferentValue`는 기본 메모에 단어가 없거나 이미 다른 값이 있음을 나타낸다. `protectedName`은 기존 한국어 이름·검수·판본 정보가 있는 수량이다. `missingOrSourceChanged`는 공개 영문 인쇄번호·출처·상품·원문 또는 해당 번역 행이 일치하지 않는 수량이다. [도감 및 기본 메모 준비 방법](../../docs/CARD_SOURCES.md)

저장소 루트에서 워커가 사용하는 PostgreSQL 접속 환경(`PG*` 또는 `DATABASE_URL`)을 설정한 상태로 실행한다. 도구는 외부 사이트에 접속하지 않는다.

```sh
export PYTHONPATH="$PWD/crawler-middleware"
python tools/weiss-korean-supplement/apply_readings.py --verify-data
python tools/weiss-korean-supplement/apply_readings.py
python tools/weiss-korean-supplement/apply_readings.py --apply
```

첫 명령은 파일의 무결성과 390개 번호·372개 메모 키를 데이터베이스 연결 없이 확인한다. 둘째 명령은 예상 변경 수를 보여 준다. 마지막 명령만 변경을 저장한다. 인쇄번호, 원문 이름, 발행사 링크와 상품명이 모두 맞고 한국어 이름이 비어 있어야 한다. 원래 번역 메모도 같은 원문·해시에 대해 값이 비어 있거나 이번 참고명과 일치해야 한다. 번역 워커가 사용 중이면 종료 코드 3을 반환한다. 24장씩 트랜잭션을 마치므로 작업이 중단되면 같은 명령으로 이어갈 수 있다.

19,321장 기준으로 한국어 이름은 12,987장에서 13,377장으로 늘고 5,944장은 계속 영문으로 읽는다. 한국어 효과가 있는 카드는 16,325장이다. 격리 PostgreSQL에서 전체 인쇄본으로 적용·재실행했을 때 두 번째 적용은 0건이었고 카드 원본·효과와 운영자 검수 데이터가 일치했다.

회귀 테스트에는 별도의 PostgreSQL 테스트 DB를 지정한다. 테스트는 해당 세션의 임시 테이블만 사용한다.

```sh
python -m unittest discover -s tools/weiss-korean-supplement -v
# TCG_TEST_DSN이 설정되면 임시 PostgreSQL 테이블을 사용하는 세 검사도 실행한다.
```

## 2.0.19 전체 기본 메모를 다시 만드는 경우

390장 보충을 이미 기본 메모가 적용된 서버에서 실행할 때는 이 단계가 필요 없다. 기본 메모를 분실한 경우 PC에서 같은 판본을 복원할 수 있다. 영어 원문 ZIP과 번역 모델은 따로 구한다. ZIP의 SHA-256은 `f1b341a6b3e3df359ca4c3bd55fc823c2510b60df66dfb7e04be851b8c81c720`이다. 모델 파일들의 체크섬은 기존 설치기가 확인한다. [영문 도감 ZIP](https://codeload.github.com/CCondeluci/WeissSchwarz-ENG-DB/zip/f0868c5ffdef7b396ae2e4ed23274a09a9175319) · [고정 번역 모델](https://huggingface.co/auralmira/m2m100-418M-ct2-int8/tree/e205afefce2fd6933a1dca3b92b5063894f2f2bb) · [모델 설치기](../../deploy/install-translation-model.py)

```sh
# 저장소 루트, 2.0.19 워커와 CUDA·CTranslate2 4.9.1을 갖춘 PC
export PYTHONPATH="$PWD/crawler-middleware"
python -m tcg_worker.weiss_memory weiss.zip model-dir fresh.sqlite generated.jsonl.gz --device cuda --threads 4
python tools/weiss-korean-supplement/restore_219.py weiss.zip generated.jsonl.gz base-219.jsonl.gz
sha256sum base-219.jsonl.gz
```

실제 19,321장으로 빈 SQLite에서 전수 추론했을 때 메모 키는 37,750개였다. 과거에 여러 배치로 생성된 출고본은 37,754개다. 공통 키 중 이름 304개와 규칙 2개의 결과가 달랐고, 현재 사전이 먼저 처리하는 이름 2개와 규칙 2개는 추론 단계에서 빠졌다. 두 메모의 원문 대조용 [차이표](memo-219-delta.jsonl)는 이 310개 키의 해시와 출고 당시 값만 담는다. 빠진 키의 영문은 제공된 고정 ZIP에서 다시 찾는다. 실제 카드에 표시할 때는 현재의 확정 사전이 과거 기계 출력보다 우선한다.

검증 환경에서 빈 캐시의 전수 추론은 262초가 걸렸다. 보정 후 JSONL 본문의 SHA-256은 `31a8a3f0537c2d2e5caaa323f86fd4b7b60ee7b547dab1e73d9a3463c93bdb88`이었고, 원래 gzip 헤더까지 복원한 2,920,974바이트의 SHA-256은 `9e2aec465df74daf1f4bc1878bb9f38b76833bbfd89e71564a0646f24ca76590`으로 출고본과 일치했다. 과거 SQLite로 재생성한 파일은 보정 전 본문도 일치했다. 다른 모델·GPU에서 이 차이표 밖의 문장이 달라지거나 압축 라이브러리가 다른 바이트를 만들면 도구는 결과 파일을 쓰기 전에 차이를 알린다. 이 확인에는 zlib 1.3.2를 사용했다. 전체 복원 회귀까지 실행하려면 `TCG_TEST_WEISS_ZIP`과 `TCG_TEST_WEISS_GENERATED`에 두 입력 파일 경로를 지정하고 위의 단위 테스트를 실행한다.
