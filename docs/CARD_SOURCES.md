# 카드 도감의 출처와 갱신 범위

각 카드는 제공자의 고유 식별자와 원문 링크를 갖는다. 도감과 덱 연습은 요청한 언어의 카드명·효과·그림을 각각 조회하고, 다른 판본을 표시할 때는 실제 언어를 함께 반환한다. 언어판을 대조할 수 있는 범위는 출처마다 다르다.

팩은 게임, 팩 코드, 원문 제품명으로 구분한다. 한 코드를 공유하는 초판·기념판이나 부스터·트라이얼 덱은 각각 조회할 수 있다. 공백·대소문자·전각 문자와 일부 문장부호의 간격만 다른 제품명은 같은 이름으로 대조한다. 기존 도감의 카드 ID와 이미 연결된 팩의 숫자 ID는 유지한다.

| 게임 | 실제 수집 범위 | 읽는 방법과 출처 |
|---|---|---|
| 유희왕 | YGOPRODeck의 영문 OCG·TCG 카드와 수록 팩·레어도별 인쇄본. 같은 카드의 팩이 다르면 별도 항목이다. | DB 버전을 확인하고 500장 단위로 카드 목록을 순회한다. 팩 발매일과 카드의 최초 OCG·TCG 발매일을 구분한다. [YGOPRODeck API 가이드](https://ygoprodeck.com/api-guide/) |
| 포켓몬 | type-null이 Pokémon Korea에서 수집한 한국어 실물 카드. 제품 코드가 없는 인쇄본은 제공된 전체 제품명을 보존한다. | GitHub API에서 받은 커밋으로 압축 파일을 고정하고 한 번 순회한다. 한국어·영어·일본어 원본이 가진 동일 인쇄본 키를 우선하고 카드 지문을 보조로 사용한다. 원본과 대상 언어에서 이름이 하나로 결정될 때만 연결한다. 개별 출처는 포켓몬코리아 상세 페이지다. [데이터셋과 키 설명](https://github.com/type-null/PTCG-database) |
| 바이스 슈발츠 | CCondeluci가 유지관리한 영문판 목록. 출처가 제공하는 카드 코드, 팩, 레어도, 소울, 트리거, 능력을 보존한다. | 세트 데이터에 영향을 준 커밋의 ZIP 한 개를 읽고 내부 JSON을 세트별 처리한다. 카드는 공식 Bushiroad 카드 검색으로 연결된다. [데이터셋과 구조](https://github.com/CCondeluci/WeissSchwarz-ENG-DB) · [공식 영문 카드 목록](https://en.ws-tcg.com/cardlist/) |
| 니벨아레나 | 젬블로컴퍼니의 공식 한국어 게시판에 등록된 인쇄본. 같은 번호의 레어도 차이는 게시물 ID로 구분한다. | 원본 사이트가 공개한 HTTP 목록과 카드 상세만 사용한다. 게시판 전체 건수와 고유 ID를 대조하고 `robots.txt` 및 최소 0.5초의 요청 간격을 적용한다. 최신 40건의 상세는 하루, 이전 항목은 30일간 캐시한다. [공식 카드 목록](http://nivelarena.co.kr/bbs/board.php?bo_table=cardlists) |
| 리프트바운드 | RiftHunt 영문 인쇄본·효과·세트 발매일과 Riot 공식 갤러리에서 확인한 한국어판 이름·효과·그림. 카드 번호는 `riftboundId`, 수집 번호(`num`), 구형 자료의 `id` 순으로 표시한다. 바인더·덱은 인쇄본 UUID(`printing_id`)를 사용한다. | RiftHunt 목록은 24시간, Riot 영문·한국어 갤러리는 7일 동안 캐시한다. Riot은 공개 Riftbound 앱 운영에 앱 전용 API 키 또는 서면 라이선스를 요구한다. [RiftHunt 무료 API](https://rifthunt.com/api/) · [Riot Digital Tools Policy](https://developer.riotgames.com/docs/riftbound) |

| 원피스 카드게임 | 한국 공식 카드 목록, 영문 OPTCG API의 부스터·스타터·DON!! 목록, Koala Kollect가 보존하는 일본·영어 공식 카드 목록. 카드 번호와 제품으로 연결하고 대표 일러스트와 판본별 출처를 기록한다. | Koala 자료는 커밋과 SHA-256으로 확인한다. 같은 카드 번호가 여러 제품에 실린 경우 각 제품을 보존한다. 한국 공식 공지는 주제 목록에서 수집하고 공식 X는 운영자가 X API 이용 요건을 충족했을 때 가동한다. [한국 공식 카드](https://www.onepiece-cardgame.kr/cardlist.do) · [한국 공식 소식](https://www.onepiece-cardgame.kr/topics.do) · [일본 공식 카드](https://www.onepiece-cardgame.com/cardlist/) · [영어 공식 카드](https://en.onepiece-cardgame.com/cardlist/) · [OPTCG API](https://optcgapi.com/) · [Koala Kollect 데이터 및 라이선스](https://github.com/hotavocado/koala-kollect-data) |

한국 공식 원피스 목록은 한 번에 새 페이지와 갱신 페이지를 합해 최대 24개 읽는다. 중단된 페이지까지 캐시한 뒤 다음 실행에서 다른 제품부터 순환한다. 첫 실행의 성공 건수는 그때까지 실제 확인된 제품·번호 조합이다. 2026년 11월 26일 검증에서 원피스 61제품 3,655건 중 한국어·영어·일본어 카드명이 모두 확인된 항목은 1,645건이었다. 한국어 과거 페이지 한 곳이 시간 초과되어 이후 동기화가 보완한다.

한 상품에서 시간 초과가 발생하면 다음 상품을 확인한다. 연속 세 번 실패하면 해당 회차의 추가 조회를 멈추고, 서버가 429·503을 반환하면 대기 지시를 따른다. 일부 페이지만 읽은 회차에는 이미 확인한 한국 인쇄본의 이름·효과·그림과 출처를 보존한다. 한국 카드명에 연결된 제품이 선택한 제품과 다르면 다른 인쇄의 표기로 표시한다.

도감·솔로 연습·바인더·덱은 카드의 표시 언어와 실제 소장판을 구분한다. 바인더의 일본어 카드명을 검색하거나, 편집 중 언어를 바꿔도 저장한 소장판·상태·수량은 유지된다. 카드명과 효과의 출처가 다르면 각 항목의 링크가 가리키는 원문을 확인할 수 있다.

원피스의 같은 카드 번호는 여러 제품에 재수록될 수 있다. `specs.productCode`는 도감에서 선택한 제품이다. 언어별 그림에는 그 그림을 확인한 출처 페이지(`imageSources`)와 확인된 제품 코드(`imageProducts`)가 함께 기록된다. 예를 들어 `EB-01 / EB01-003`의 한국어 대체 그림은 한국 공식 목록의 `OP-14 / EB01-003_P2`이다. 제품 코드가 없는 그림과 여러 상품을 묶은 `PROMO` 항목의 그림은 출처만 기록한다. 다음 원피스 동기화에서 기존 응답 캐시를 다시 읽어 저장된 카드 ID에 이 정보를 채운다. [한국 공식 OPK-14 카드 목록](https://www.onepiece-cardgame.kr/cardlist.do?series=%5BOPK-14%5D+%EB%B6%80%EC%8A%A4%ED%84%B0+%ED%8C%A9+%EC%B0%BD%ED%95%B4%EC%9D%98+%EC%B9%A0%EA%B1%B8&page=7&size=20)

유희왕은 YGOPRODeck의 `konami_id`와 YAML Yugi의 코나미 DB 번호로 한국어·영어·일본어판 카드명과 효과를 연결한다. 일본어 표기에서 루비의 읽기 주석을 제거한다. 새 스냅샷이 완성되면 언어 인덱스를 교체한다. YGOPRODeck 그림은 제공자가 직접 연결을 제한하고 있으며 이 클라이언트는 해당 CDN의 이미지를 직접 불러오지 않는다. 한국·일본판 이미지를 임의로 추정하지 않는다. [YAML Yugi](https://github.com/DawnbrandBots/yaml-yugi) · [YGOPRODeck 이용 안내](https://ygoprodeck.com/api-guide/)

기존 유희왕 도감을 가져온 경우, 다음 수집에서 수록 번호와 원문 카드명이 YAML Yugi의 같은 언어 인쇄본과 모두 일치해야 번역을 연결한다. 여러 카드가 일치하거나 출처가 비공식 번역으로 표시한 항목은 해당 필드를 제외한다. 별도 영어판 번호와 이름을 YGOPRODeck에서 확인한 상금·기념 카드는 영어 문구를 제공한다. 994행의 원본을 2026년 11월 26일 대조한 결과 428행이 연결됐다. 이름은 한국어 199행·영어 308행·일본어 390행, 효과는 한국어 170행·영어 285행·일본어 383행에서 확인됐다. 원문은 카드 ID별 별도 테이블에 출처와 함께 기록하며, 최신 전체 수집에서 근거가 바뀌거나 사라지면 정정하거나 삭제한다. 기존 도감 텍스트·운영자 입력·일러스트는 각자의 자료를 유지한다. [대조한 YAML Yugi 스냅샷](https://github.com/DawnbrandBots/yaml-yugi/tree/2355f8324797b38596dbf31eb21711f411299882/data/cards) · [영어판 상금 카드 예시](https://ygoprodeck.com/card/ulevo-10231)

영문 유희왕 대표 이미지는 일일 카드 동기화 시 공개 인쇄본 최대 12개를 받아 기존 WebP 아틀라스 작업 대기열에 등록한다. 카드 API의 작은 대표 이미지 URL을 검증하고 1년간 재사용하며 운영자가 작업한 변형 이미지는 유지한다. 출처가 특정 팩의 일러스트나 판본 언어를 보증하지 않는 이미지는 대표 그림으로 표시한다.

유희왕의 **카드 참고 이미지**는 코나미 카드 ID(CID)와 YGOResources 매니페스트에서 대조한 언어별 일러스트다. 한국 데이터베이스 13,861개 CID, 영어 NEURON 14,068개, 일본어 NEURON 14,429개가 연결된다. 러시 듀얼은 제외한다. 인쇄본 그림이 없는 언어에서는 확인된 해당 지역의 가장 낮은 일러스트 번호를 사용하고, 그 언어도 없으면 표시한 지역을 함께 돌려준다. 이 그림은 같은 카드의 일러스트이며 특정 팩의 테두리·판번호·효과가 실린 카드 스캔을 보증하지 않는다. 출처는 사용한 개별 PNG URL이다. 서버에는 경로만 저장하고 해당 그림을 열 때 CDN에서 읽는다. [제공자 이용 안내](https://github.com/yugioh-artworks/artworks-index#readme) · [사용한 경로 매니페스트](https://github.com/yugioh-artworks/artworks-index/blob/433fe3d2223d3453b7732b5bad016196fb7b092f/manifest.json)

포켓몬 인쇄본의 기준은 한국판 `ko_id`다. 이름과 인쇄본 키 또는 카드 지문이 일치하고 해당 필드가 하나로 결정될 때 언어별 기술·효과와 이미지를 연결한다. 한국·일본판은 지역 발행사 이미지 URL을 사용한다. 영어 그림은 제품·번호·영문명을 대조한다. TCGdex의 영문 카드 목록과 Pokémon TCG API 유지관리자가 커밋별로 배포한 카드 데이터를 읽으며, 그림의 근거 URL을 `specs.imageSources.en`에 저장한다. [TCGdex REST](https://tcgdex.dev/) · [Pokémon TCG API 데이터](https://github.com/PokemonTCG/pokemon-tcg-data)

영어 인덱스 갱신 시 워커는 키 없이 Pokémon TCG API의 `GET /v2/sets`로 세트 별칭을 확인하고, 이미 존재하는 카드 ID를 순환하며 주당 최대 4개 `GET /v2/cards/{id}` 응답을 카드 번호·세트·이름과 대조한다. 요청 사이에는 최소 2.1초를 둔다. 성공한 응답과 소스 URL을 보존하고, 오류 시에는 기존 검증 자료와 배포 스냅샷을 사용한다. `Retry-After`는 재시작 후에도 지킨다. 신규 키 발급은 종료됐으며 기존 키 지원 종료 예정일은 2027년 3월 1일이다. [카드 상세 사양](https://docs.pokemontcg.io/api-reference/cards/get-card/) · [호출 한도 및 중단 안내](https://docs.pokemontcg.io/getting-started/rate-limits/)

포켓몬은 요청한 언어판의 이름이 없을 때 전국도감 번호와 한국 카드명 전체가 같은 다른 인쇄본도 대조한다. 소유자·폼·`ex` 표기를 포함한 이름이 정확히 같고 확인된 외국어 표기가 하나일 때만 **다른 인쇄의 참고 카드명**을 제공한다. 예를 들어 한국판 피카츄 ex(`BS2025015044`)는 다른 인쇄의 영문 **Pikachu ex**, 후파(`BS2019018047`)는 다른 인쇄의 일본어 **フーパ**를 참고할 수 있다. 각 카드의 기술·효과·그림은 해당 카드의 조회 결과를 유지한다. 현 스냅샷 20,323장 중 영문 이름 14,428장에 참고명 684장, 일본어 이름 17,431장에 참고명 515장이 추가된다. 기존 서버는 V28에서 저장된 원문을 사용하고, 이후 워커는 스냅샷마다 다시 대조한다. [대조한 데이터 리비전](https://github.com/type-null/PTCG-database/tree/18e0de2feb7a35ebe4296ede0ba6cc768961489b) · [영문 참고 인쇄](https://pkmncards.com/card/pikachu-ex-30th-celebration-30c-053/) · [일본 공식 참고 인쇄](https://www.pokemon-card.com/card-search/details.php/card/31167)

기존 유희왕 도감의 `on`은 원문 카드명이며 `or`는 독음이다. 별도 확인된 인쇄본 데이터가 없으면 `-JP` 번호와 일본어 문자, 또는 `-EN` 번호와 영문 표기가 일치하는 기존 카드의 `on`을 **기존 도감 원문**으로 표시한다. 994장을 기존 외부 대조 결과와 함께 검사해 일본어 153장·영어 12장의 원문 표시를 추가했다. 미확인 한국어 표기는 **기존 도감 표기**로 구분한다. [코나미 공식 카드 DB](https://www.db.yugioh-card.com/yugiohdb/?request_locale=ko) · [포켓몬 공식 카드 검색](https://www.pokemon-card.com/card-search/)

나무위키는 2026년 11월 27일 공개한 `robots.txt`에서 이 서비스의 문서 경로 자동 수집을 허용하지 않았다. 독자가 직접 찾은 위키 표기는 참고 자료이며, 공식 인쇄본에서 확인한 명칭·효과와 구분한다. [나무위키 수집 정책](https://namu.wiki/robots.txt)

관리자의 **도감 → 카드**에서 같은 판번호를 확인한 뒤 언어별 이름이나 효과와 근거 페이지를 저장할 수 있다. 공식 발행사 페이지에서 확인한 인쇄본 표기는 해당 필드를 교정한다. 위키 등에서 대조한 번역은 선택 언어의 원본 문구가 비어 있을 때 표시한다. 이름만 확인했다면 효과는 비워 둔다. 원본 수집과 운영자 검수 기록은 각각 보존되므로 다음 수집에서 공식 문구가 들어오면 즉시 반영된다. 두 필드를 모두 비워 저장하면 해당 언어의 검수 표기를 철회한다.

2026년 11월 26일 한국 인쇄본 20,323건에서 영어 그림 9,961건, 일본어 그림 13,766건을 확인했다. 기존 영문 TCGdex 매칭만 적용했을 때보다 영어 그림이 2,846건 늘었다. 같은 날 Pokémon TCG API의 177세트 목록과 `base1-4` 상세가 HTTP 200을 반환했고, 다른 호출에서는 5xx가 발생했다.

리프트바운드의 새 덱은 2026년 10월 9일 종합·대회 규칙과 11월 23일 금지 목록을 적용한다. 메인 40장에 선택한 챔피언 1장이 포함되고, 룬 12장·서로 다른 전장 3장·레전드 1장·사이드보드 최대 10장을 검사한다. 기존 저장 덱의 규칙 버전은 유지한다. [Riot 공식 규칙과 금지 목록](https://playriftbound.com/en-us/rules-hub/)

2026년 11월 27일 RiftHunt 인쇄본 1,732장을 Riot의 영문·한국어 갤러리와 대조했다. 세트, 수집 번호, 공개 카드 코드, Riot 식별자와 영문 인쇄본 이미지 키가 일치한 카드 중 364장(OGN 340장, OGS 24장)에서 한국어 카드명, 344장에서 한국어 효과를 확인했다. `OGN-001/298`은 **타오르는 화염용**, `OGS-001/024`는 **애니, 화염**이다. 다음 리프트바운드 정기 수집이 기존 카드 ID에 판본 근거를 채운다. 갤러리를 읽지 못하면 같은 인쇄본에서 앞서 확인한 자료를 유지한다. [Riot 한국어 카드 갤러리](https://playriftbound.com/ko-kr/card-gallery/) · [영문 카드 갤러리](https://playriftbound.com/en-us/card-gallery/)

그림은 Riot이 해당 이름으로 설명한 공식 CDN URL을 사용한다. 한국어판 363장은 영문판과 에셋이 달랐다. **빅토르**(`OGN-246a/298`)는 한국어 갤러리에도 영문판 그림이 실려 있어 한국어 이름과 영문판 그림을 표시한다. [타오르는 화염용 한국어판](https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/8e1175bebba326d3d38e52499870d23828934092-1488x2079.png?accountingTag=RB)

바이스 영문 인쇄본 19,321건에는 일본어명 필드가 없다. 별도 일본판 자료에는 일본어 카드명과 일부 일본어 효과가 있지만, 두 지역에서 같은 번호가 다른 카드를 뜻하는 사례가 있다. 예를 들어 `BD/W63`의 102~104번은 영문판에서 순서가 바뀌었다. 지역 간 카드의 대응이 확인되기 전에는 영문 원문을 제공한다. [영문 카드 예시](https://en.ws-tcg.com/cardlist/?cardno=5HY%2FW101-E001) · [일본판 자료](https://github.com/CCondeluci/WeissSchwarz-JP-DB) · [대조표 유지관리자가 확인한 번호 변경](https://github.com/Cris-Oblea/ws-card-db/blob/main/documentation/en-name-matching.md)

카드 문구·상표·일러스트의 권리는 각 게임사와 IP 권리자에게 있다. 데이터셋 도구의 오픈소스 라이선스는 원본 카드 이미지에 대한 이용 허가와 구분한다. 이 어댑터는 카드·팩 메타데이터만 수집한다. 공개 운영 시에는 원문 출처 표시와 각 제공자의 이용 조건을 따른다.

`CATALOG_CACHE_ROOT`에는 웹 공개 경로 밖의 쓰기 가능한 디렉터리를 지정한다. 기본 카탈로그 갱신 간격은 24시간이다. 운영자 화면에서 게임별 상태와 마지막 성공 건수를 확인할 수 있다. 같은 게임의 스냅샷은 프로세스 잠금으로 한 번에 하나만 읽는다. 유희왕은 DB 버전이 같은 카드 페이지를 재사용하며, 포켓몬은 한국어 커밋이 같으면 이미 정규화한 한국어 자료를 읽는다. 바이스 슈발츠는 세트 데이터의 커밋이 같으면 저장한 ZIP을 재사용한다. 새 버전의 파일을 완성하면 해당 소스의 이전 리비전 캐시를 정리한다. HTTP 호출이 중간에 끊기면 이미 커밋한 배치를 보존하고, 다음 실행에서 응답 캐시와 중복 방지 키를 사용해 대조한다. 429 또는 503 응답의 대기 지시는 수집 스케줄러에 전달한다.

원피스 덱 검증은 한국 대회 금지 카드와 금지 페어, 2026년 7월 해제된 두 카드, 11월 13일 추가된 금지 카드를 반영한다. [한국 공식 금지·제한 목록](https://www.onepiece-cardgame.kr/topics/view.do?brdno=1171)

## 유희왕 한국 수록 근거

카드 상세에서 같은 코나미 카드 ID의 한국판 수록 번호와 한국 공식 카드 페이지를 열 수 있다. 인쇄 번호의 링크는 현재 자료를 확인할 때 사용한 YAML Yugi 파일을 연다. 다른 나라의 인쇄본·일러스트를 보고 있을 때에도 도감에 표시된 원래 카드 번호는 유지한다. 한국 수록 번호를 확인할 수 없는 카드는 이 항목을 비워 둔다. [YAML Yugi 카드 자료와 이용 조건](https://github.com/DawnbrandBots/yaml-yugi)

날짜는 YGOJSON의 **한국** 지역 상품에 같은 코나미 ID와 전체 수록 번호가 함께 실린 경우에만 제공한다. 확인한 상품 가운데 가장 이른 발매일이며, 해당 카드의 공식 최초 발매일이나 대회 사용 가능일은 별도로 확인해야 한다. 2026년 11월 27일 검증에서 한국 수록 번호가 확인된 고유 카드 13,866장 중 13,072장에 날짜가 있었고, 794장은 번호만 확인됐다. 예를 들어 푸른 눈의 백룡의 `LOB-K001` 수록 상품은 2003년 12월 9일에 발매됐다. [한국 공식 카드 페이지의 수록 목록](https://www.db.yugioh-card.com/yugiohdb/card_search.action?cid=4007&ope=2&request_locale=ko) · [대조한 YGOJSON 상품](https://github.com/iconmaster5326/YGOJSON/blob/ab5016e14cc6c3296a85d52de2c8b61b9db55cfa/sets/240fad99-f00a-41ed-99e9-26656d0d677c.json)

국내 대회의 금지·제한은 대원미디어가 공지한다. 국내 공지와 NEURON 한국어 목록은 같은 2026년 10월 1일 기준으로도 금지 카드 집계가 서로 다르다. YGOJSON이 재배포한 자료는 4월 7일판이며 YAML Yugi의 지역별 제한 데이터는 한국 전체 목록을 제공하지 않는다. 현행 국내 대회는 한국 공식 공지와 개별 대회 규정을 직접 확인할 수 있다. 앱에서 선택할 수 있는 OCG 검사 지역은 일본이다. [한국 공식 리미트 레귤레이션](https://www.yugioh.co.kr/site/limit_regulation.php) · [한국어 NEURON 목록](https://www.db.yugioh-card.com/yugiohdb/forbidden_limited.action?request_locale=ko) · [YAML Yugi 지역별 제공 범위](https://github.com/DawnbrandBots/yaml-yugi-limit-regulation)

상품 날짜 색인은 YGOJSON 작성자와 Yugipedia 기여자가 정리한 사실 자료에서 한국 상품 구성·날짜만 추출해 줄였다. 원본 카드 본문과 이미지는 포함하지 않는다. 이 파생 색인을 CC BY-SA 4.0으로 제공한다. 재현 시 YGOJSON의 2026-04-07 `aggregate.zip`과 `crawler-middleware/tools/build_ygo_kr_products.py`를 사용한다. 스크립트는 릴리스에 게시된 전체 SHA-256을 확인하고 동일한 압축 색인을 생성한다. [YGOJSON 배포 방법 및 출처](https://github.com/iconmaster5326/YGOJSON) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

## 리프트바운드 공개 배포

앱 전용 키로 운영하려면 Riot 개발자 포털에 앱을 등록하고 공식 `riftbound-content-v1`의 `GET /riftbound/content/v1/contents`에서 카드 자료를 받아야 한다. 공식 명세는 기본 언어를 영어로 안내한다. 2026년 11월 25일 아시아 엔드포인트에 키 없이 요청했을 때 HTTP 401이 반환됐다. 현재 설치의 카드 본문과 판본 ID는 RiftHunt에서 왔으므로, 키 발급 후 실제 공식 응답으로 판본을 대조할 때까지 기존 바인더와 덱의 카드 ID를 보존한다. [공식 API 명세](https://developer.riotgames.com/apis#riftbound-content-v1/GET_getContent) · [Riot의 카드 자료·앱 등록 요건](https://developer.riotgames.com/policies/riftbound)
