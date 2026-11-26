# 한국 TCG 매장 지도

`/stores`에서 상호·주소와 게임을 검색하고 내 위치 또는 지도 중심에서 2~100 km 안의 매장을 찾는다. 매장을 누르면 길찾기, 점포별 영업시간과 종목 출처가 열린다. 로그인한 이용자는 별표로 매장을 저장한다. GPS는 ‘내 위치 주변’을 누른 뒤 브라우저가 위치 접근을 허용할 때 사용한다. 서버는 검색용 좌표를 회원 프로필에 저장하지 않는다.

## 첫 설치 데이터

카카오맵을 사용하려면 Kakao Developers의 JavaScript 키에 사이트의 정확한 출처를 등록한다. A90 내부 주소는 `http://127.0.0.1:8080`이다. API에 `KAKAO_MAP_JS_KEY`를 설정하거나 A90의 Ubuntu 설정 디렉터리 `/etc/tcg-hub/web-config/`에 `tcg.kakao-map-key` 파일을 둔다. 이 키는 브라우저에 제공된다. SDK를 사용할 수 없는 환경에서는 OpenStreetMap 지도를 표시한다. [카카오 지도 JavaScript 가이드](https://apis.map.kakao.com/web/guide/)

소상공인시장진흥공단의 2026년 9월 30일 전국 상가업소 분기 파일에서 상가업소번호·상호·시도·도로명주소·WGS84 위치만 추출했다. 공공데이터포털의 해당 파일은 무료이며 ‘이용허락범위 제한 없음’이다. 지오코딩 호출 또는 외부 장소 검색 키가 필요하지 않다. 원본 ZIP의 SHA-256은 `c83b30e7a1d1144864a91d0e1818abf360f565972878d6e3c88d75ceafe2286a`다. [공공데이터포털 파일과 이용조건](https://www.data.go.kr/data/15083033/fileData.do)

첫 설치에 **34곳의 실명·주소·좌표**가 포함된다. 17곳은 공인점·대회 장소·점포 안내 또는 판매처 상품 목록을 공공 상가업소와 대조했다. 1곳은 장난감 소매업 상호가 ‘포켓몬카드SSR’이라 포켓몬으로 분류했다. 나머지 16곳은 장난감 소매업으로 등록되어 있고 상호에 ‘TCG’ 또는 ‘티씨지’가 명시되어 있다. 이들 16곳의 개별 종목은 미확인으로 표시한다. 공공자료와 유통사의 이전 주소가 충돌한 진주 티씨지팩토리는 제외했다.

| 시도 | 매장 수 | 시도 | 매장 수 |
| --- | ---: | --- | ---: |
| 강원특별자치도 | 2 | 경기도 | 9 |
| 경상남도 | 3 | 경상북도 | 1 |
| 대구광역시 | 1 | 대전광역시 | 3 |
| 부산광역시 | 1 | 서울특별시 | 7 |
| 울산광역시 | 1 | 인천광역시 | 1 |
| 전남광주통합특별시 | 2 | 제주특별자치도 | 1 |
| 충청남도 | 2 | | |

시도명은 해당 분기 원자료를 따른다. 전국 파일을 검색한 결과 13개 시도에서 조건을 충족했다. 공인점 전체 수와 현재 영업 여부는 공급사·점포에서 확인해야 한다.

## 종목과 영업시간의 근거

2026년 11월 25일 점포별 발행사·판매처 자료를 확인했다. 종목이 확인된 매장은 18곳이며 복수 종목이 겹친다. 카드 재고 수량이나 개별 상품의 판매 가능 여부는 집계하지 않는다.

| 게임 | 확인 매장 | 근거 |
| --- | ---: | --- |
| 유희왕 | 13 | [대원미디어 유희왕 공인점](https://www.yugioh.co.kr/site/event_store.php?code=store) |
| 포켓몬 TCG | 5 | [포켓몬코리아 점포 안내](https://pokemonkorea.co.kr/pokemon_cardshop/menu202) 및 포켓몬카드가 명시된 공공 상호 1곳 |
| 바이스 슈발츠, 니벨아레나 | 각각 1 | 부천 하비게임몰의 점포 사업장 주소와 종목별 판매 이력. [하비게임몰 상품 목록](https://www.hobbygamemall.com/goods/goods_list.php?cateCd=001003&page=4) |
| 리프트바운드 | 2 | [인천 티씨지아레나 공식 대회 장소](https://playriftbound.com/ko-KR/events/117545207299594342), [서울 카드숲 공식 대회 장소](https://playriftbound.com/ko-KR/events/117586446689253331) |

원주·목동·천안·강릉 4곳은 포켓몬코리아 점포별 안내 포스터의 요일별 운영시간을 기록했다. 다른 30곳은 ‘영업시간 미확인’으로 표시한다. 점포 이름·시간·종목 같은 사실과 확인 날짜·출처 링크만 사용한다. [원주](https://pokemonkorea.co.kr/pokemon_cardshop/menu202), [목동](https://pokemonkorea.co.kr/pokemon_cardshop/menu758), [천안](https://pokemonkorea.co.kr/pokemon_cardshop/menu776), [강릉](https://pokemonkorea.co.kr/pokemon_cardshop/menu809)

## 분기 갱신

1. 위 공공데이터포털에서 최신 전국 분기 ZIP을 받는다. 제출된 원본 파일을 그대로 사용한다.
2. `crawler-middleware`에서 `python -m tcg_worker.stores 전국자료.zip --json stores-review.json`을 실행해 이름·좌표·종목·출처를 검토한다. 전국 CSV를 스트리밍하므로 전체 압축 해제가 필요 없다. 지도에 올라오는 소수의 결과만 출력 파일에 담긴다.
3. 같은 파일에 대해 `python -m tcg_worker.stores 전국자료.zip --apply`를 실행한다. 워커의 기존 `DATABASE_URL` 또는 libpq의 `PG*` 환경을 사용한다. A90 최초 설치에는 이 명령이 필요 없다. Flyway V11이 검증된 첫 데이터를 넣는다.
4. 점포별 종목·영업시간은 공식 안내를 다시 확인하고 `tcg_worker/stores.py`의 출처·일자·상가업소번호를 함께 갱신한다. 상호나 도로명주소가 검수 정보와 달라진 점포는 다음 확인까지 새 목록에서 빠진다.

가져오기는 분기명과 지역 파일의 완전성을 검증한다. DB는 트랜잭션 하나로 결과를 적용하며 더 오래된 분기의 반영을 거부한다. 동일 상가업소번호의 내부 ID를 유지하고 목록에서 사라진 매장은 비공개 처리해 기존 즐겨찾기와 행사 외래키를 보존한다. 소상공인시장진흥공단 원본과의 연결이 없는 기존 운영자 매장은 그대로 검색된다.

## 지도와 API

OpenLayers가 OpenStreetMap 표준 배경 지도를 표시한다. 화면에 보이는 범위만 HTTPS 타일을 요청하고 출처를 항상 표시한다. 서비스 워커에서 OSM 타일을 사전 다운로드하지 않는다. 타일 서버 장애 시에도 매장 목록과 카카오맵 길찾기를 쓸 수 있다. [OSM 타일 사용 정책](https://operations.osmfoundation.org/policies/tiles/)

- 공개 `GET /api/v1/stores`는 `q`, `game`, `page`, `size`를 받는다. 좌표 검색에는 `lat`과 `lon`을 함께 보낸다. `radiusKm` 기본값은 10, 상한은 500이다. PostGIS의 `ST_DWithin(geography,…)`과 `store_location_gist`를 사용하고 가까운 순서로 반환한다.
- 로그인 사용자 `GET /api/v1/me/favorites/stores`는 자신의 공개 매장 ID를 반환한다. ‘즐겨찾기만’은 `GET /api/v1/me/favorites/stores/search`로 자신의 저장 목록 안에서 같은 검색·반경 조건을 적용한다. `PUT` 또는 `DELETE /api/v1/me/favorites/stores/{id}`는 여러 번 실행해도 결과가 같다. 브라우저 쓰기 요청에는 인증 토큰, 같은 Origin과 `X-TCG-Request: 1`이 필요하다.
