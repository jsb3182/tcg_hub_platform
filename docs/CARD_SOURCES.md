# 카드 도감의 출처와 갱신 범위

각 카드는 제공자의 고유 식별자와 원문 링크를 갖는다. 도감과 덱 연습은 요청한 언어의 카드명·효과·그림을 각각 조회하고, 다른 판본을 표시할 때는 실제 언어를 함께 반환한다. 언어판을 대조할 수 있는 범위는 출처마다 다르다.

팩은 게임, 팩 코드, 원문 제품명으로 구분한다. 한 코드를 공유하는 초판·기념판이나 부스터·트라이얼 덱은 각각 조회할 수 있다. 공백·대소문자·전각 문자와 일부 문장부호의 간격만 다른 제품명은 같은 이름으로 대조한다. 기존 도감의 카드 ID와 이미 연결된 팩의 숫자 ID는 유지한다.

| 게임 | 실제 수집 범위 | 읽는 방법과 출처 |
|---|---|---|
| 유희왕 | YGOPRODeck의 영문 OCG·TCG 카드와 수록 팩·레어도별 인쇄본. 같은 카드의 팩이 다르면 별도 항목이다. | DB 버전을 확인하고 500장 단위로 카드 목록을 순회한다. 팩 발매일과 카드의 최초 OCG·TCG 발매일을 구분한다. [YGOPRODeck API 가이드](https://ygoprodeck.com/api-guide/) |
| 포켓몬 | type-null이 Pokémon Korea에서 수집한 한국어 실물 카드. 제품 코드가 없는 인쇄본은 제공된 전체 제품명을 보존한다. | GitHub API에서 받은 커밋으로 압축 파일을 고정하고 한 번 순회한다. 한국어·영어·일본어 원본이 가진 동일 인쇄본 키를 우선하고 카드 지문을 보조로 사용한다. 원본과 대상 언어에서 이름이 하나로 결정될 때만 연결한다. 개별 출처는 포켓몬코리아 상세 페이지다. [데이터셋과 키 설명](https://github.com/type-null/PTCG-database) |
| 바이스 슈발츠 | CCondeluci가 유지관리한 영문판 목록. 출처가 제공하는 카드 코드, 팩, 레어도, 소울, 트리거, 능력을 보존한다. | 세트 데이터에 영향을 준 커밋의 ZIP 한 개를 읽고 내부 JSON을 세트별 처리한다. 카드는 공식 Bushiroad 카드 검색으로 연결된다. [데이터셋과 구조](https://github.com/CCondeluci/WeissSchwarz-ENG-DB) · [공식 영문 카드 목록](https://en.ws-tcg.com/cardlist/) |
| 니벨아레나 | 젬블로컴퍼니의 공식 한국어 게시판에 등록된 인쇄본. 같은 번호의 레어도 차이는 게시물 ID로 구분한다. | 원본 사이트가 공개한 HTTP 목록과 카드 상세만 사용한다. 게시판 전체 건수와 고유 ID를 대조하고 `robots.txt` 및 최소 0.5초의 요청 간격을 적용한다. 최신 40건의 상세는 하루, 이전 항목은 30일간 캐시한다. [공식 카드 목록](http://nivelarena.co.kr/bbs/board.php?bo_table=cardlists) |
| 리프트바운드 | RiftHunt 영문 인쇄본, 카드 텍스트와 세트 발매일. 카드 번호는 `riftboundId`, 수집 번호(`num`), 구형 자료의 `id` 순으로 표시한다. 바인더·덱과 원문 링크에는 인쇄본 UUID(`printing_id`)를 사용한다. | 공개 bulk API에서 카드·세트 스냅샷을 받고 24시간 동안 수동 갱신에도 같은 파일을 사용한다. Riot Games는 공개 Riftbound 앱 운영에 앱 전용 API 키 또는 서면 라이선스를 요구한다. [RiftHunt 무료 API](https://rifthunt.com/api/) · [Riot Digital Tools Policy](https://developer.riotgames.com/docs/riftbound) |

| 원피스 카드게임 | 한국 공식 카드 목록, 영문 OPTCG API의 부스터·스타터·DON!! 목록, Koala Kollect가 보존하는 일본·영어 공식 카드 목록. 카드 번호와 제품으로 연결하고 대표 일러스트와 판본별 출처를 기록한다. | Koala 자료는 커밋과 SHA-256으로 확인한다. 같은 카드 번호가 여러 제품에 실린 경우 각 제품을 보존한다. 한국 공식 공지는 주제 목록에서 수집하고 공식 X는 운영자가 X API 이용 요건을 충족했을 때 가동한다. [한국 공식 카드](https://www.onepiece-cardgame.kr/cardlist.do) · [한국 공식 소식](https://www.onepiece-cardgame.kr/topics.do) · [일본 공식 카드](https://www.onepiece-cardgame.com/cardlist/) · [영어 공식 카드](https://en.onepiece-cardgame.com/cardlist/) · [OPTCG API](https://optcgapi.com/) · [Koala Kollect 데이터 및 라이선스](https://github.com/hotavocado/koala-kollect-data) |

한국 공식 원피스 목록은 한 번에 새 페이지와 갱신 페이지를 합해 최대 24개 읽는다. 중단된 페이지까지 캐시한 뒤 다음 실행에서 다른 제품부터 순환한다. 첫 실행의 성공 건수는 그때까지 실제 확인된 제품·번호 조합이다. 2026년 11월 26일 검증에서 원피스 61제품 3,655건 중 한국어·영어·일본어 카드명이 모두 확인된 항목은 1,645건이었다. 한국어 과거 페이지 한 곳이 시간 초과되어 이후 동기화가 보완한다.

원피스의 같은 카드 번호는 여러 제품에 재수록될 수 있다. `specs.productCode`는 도감에서 선택한 제품이다. 언어별 그림에는 그 그림을 확인한 출처 페이지(`imageSources`)와 확인된 제품 코드(`imageProducts`)가 함께 기록된다. 예를 들어 `EB-01 / EB01-003`의 한국어 대체 그림은 한국 공식 목록의 `OP-14 / EB01-003_P2`이다. 제품 코드가 없는 그림과 여러 상품을 묶은 `PROMO` 항목의 그림은 출처만 기록한다. 다음 원피스 동기화에서 기존 응답 캐시를 다시 읽어 저장된 카드 ID에 이 정보를 채운다. [한국 공식 OPK-14 카드 목록](https://www.onepiece-cardgame.kr/cardlist.do?series=%5BOPK-14%5D+%EB%B6%80%EC%8A%A4%ED%84%B0+%ED%8C%A9+%EC%B0%BD%ED%95%B4%EC%9D%98+%EC%B9%A0%EA%B1%B8&page=7&size=20)

유희왕은 YGOPRODeck의 `konami_id`와 YAML Yugi의 코나미 DB 번호로 한국어·영어·일본어판 카드명과 효과를 연결한다. 일본어 표기에서 루비의 읽기 주석을 제거한다. 새 스냅샷이 완성되면 언어 인덱스를 교체한다. YGOPRODeck 그림은 제공자가 직접 연결을 제한하고 있으며 이 클라이언트는 해당 CDN의 이미지를 직접 불러오지 않는다. 한국·일본판 이미지를 임의로 추정하지 않는다. [YAML Yugi](https://github.com/DawnbrandBots/yaml-yugi) · [YGOPRODeck 이용 안내](https://ygoprodeck.com/api-guide/)

영문 유희왕 대표 이미지는 일일 카드 동기화 시 공개 인쇄본 최대 12개를 받아 기존 WebP 아틀라스 작업 대기열에 등록한다. 카드 API의 작은 대표 이미지 URL을 검증하고 1년간 재사용하며 운영자가 작업한 변형 이미지는 유지한다. 출처가 특정 팩의 일러스트나 판본 언어를 보증하지 않는 이미지는 대표 그림으로 표시한다.

포켓몬 인쇄본의 기준은 한국판 `ko_id`다. 이름과 인쇄본 키 또는 카드 지문이 일치하고 해당 필드가 하나로 결정될 때 언어별 기술·효과와 이미지를 연결한다. 한국·일본판은 지역 발행사 이미지 URL을 사용한다. 영어 그림은 제품·번호·영문명을 대조한다. TCGdex의 영문 카드 목록과 Pokémon TCG API 유지관리자가 커밋별로 배포한 카드 데이터를 읽으며, 그림의 근거 URL을 `specs.imageSources.en`에 저장한다. [TCGdex REST](https://tcgdex.dev/) · [Pokémon TCG API 데이터](https://github.com/PokemonTCG/pokemon-tcg-data)

영어 인덱스 갱신 시 워커는 키 없이 Pokémon TCG API의 `GET /v2/sets`로 세트 별칭을 확인하고, 이미 존재하는 카드 ID를 순환하며 주당 최대 4개 `GET /v2/cards/{id}` 응답을 카드 번호·세트·이름과 대조한다. 요청 사이에는 최소 2.1초를 둔다. 성공한 응답과 소스 URL을 보존하고, 오류 시에는 기존 검증 자료와 배포 스냅샷을 사용한다. `Retry-After`는 재시작 후에도 지킨다. 신규 키 발급은 종료됐으며 기존 키 지원 종료 예정일은 2027년 3월 1일이다. [카드 상세 사양](https://docs.pokemontcg.io/api-reference/cards/get-card/) · [호출 한도 및 중단 안내](https://docs.pokemontcg.io/getting-started/rate-limits/)

2026년 11월 26일 한국 인쇄본 20,323건에서 영어 그림 9,961건, 일본어 그림 13,766건을 확인했다. 기존 영문 TCGdex 매칭만 적용했을 때보다 영어 그림이 2,846건 늘었다. 같은 날 Pokémon TCG API의 177세트 목록과 `base1-4` 상세가 HTTP 200을 반환했고, 다른 호출에서는 5xx가 발생했다.

리프트바운드의 새 덱은 2026년 10월 9일 종합·대회 규칙과 11월 23일 금지 목록을 적용한다. 메인 40장에 선택한 챔피언 1장이 포함되고, 룬 12장·서로 다른 전장 3장·레전드 1장·사이드보드 최대 10장을 검사한다. 기존 저장 덱의 규칙 버전은 유지한다. [Riot 공식 규칙과 금지 목록](https://playriftbound.com/en-us/rules-hub/)

카드 문구·상표·일러스트의 권리는 각 게임사와 IP 권리자에게 있다. 데이터셋 도구의 오픈소스 라이선스는 원본 카드 이미지에 대한 이용 허가와 구분한다. 이 어댑터는 카드·팩 메타데이터만 수집한다. 공개 운영 시에는 원문 출처 표시와 각 제공자의 이용 조건을 따른다.

`CATALOG_CACHE_ROOT`에는 웹 공개 경로 밖의 쓰기 가능한 디렉터리를 지정한다. 기본 카탈로그 갱신 간격은 24시간이다. 운영자 화면에서 게임별 상태와 마지막 성공 건수를 확인할 수 있다. 같은 게임의 스냅샷은 프로세스 잠금으로 한 번에 하나만 읽는다. 유희왕은 DB 버전이 같은 카드 페이지를 재사용하며, 포켓몬은 한국어 커밋이 같으면 이미 정규화한 한국어 자료를 읽는다. 바이스 슈발츠는 세트 데이터의 커밋이 같으면 저장한 ZIP을 재사용한다. 새 버전의 파일을 완성하면 해당 소스의 이전 리비전 캐시를 정리한다. HTTP 호출이 중간에 끊기면 이미 커밋한 배치를 보존하고, 다음 실행에서 응답 캐시와 중복 방지 키를 사용해 대조한다. 429 또는 503 응답의 대기 지시는 수집 스케줄러에 전달한다.

원피스 덱 검증은 한국 대회 금지 카드와 금지 페어, 2026년 7월 해제된 두 카드, 11월 13일 추가된 금지 카드를 반영한다. [한국 공식 금지·제한 목록](https://www.onepiece-cardgame.kr/topics/view.do?brdno=1171)

## 리프트바운드 공개 배포

앱 전용 키로 운영하려면 Riot 개발자 포털에 앱을 등록하고 공식 `riftbound-content-v1`의 `GET /riftbound/content/v1/contents`에서 카드 자료를 받아야 한다. 공식 명세는 기본 언어를 영어로 안내한다. 2026년 11월 25일 아시아 엔드포인트에 키 없이 요청했을 때 HTTP 401이 반환됐다. 현재 설치의 카드 본문과 판본 ID는 RiftHunt에서 왔으므로, 키 발급 후 실제 공식 응답으로 판본을 대조할 때까지 기존 바인더와 덱의 카드 ID를 보존한다. [공식 API 명세](https://developer.riotgames.com/apis#riftbound-content-v1/GET_getContent) · [Riot의 카드 자료·앱 등록 요건](https://developer.riotgames.com/policies/riftbound)
