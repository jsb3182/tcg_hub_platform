ALTER TABLE store ADD COLUMN semas_id text UNIQUE, ADD COLUMN region text,
    ADD COLUMN source_date date, ADD COLUMN listed boolean NOT NULL DEFAULT true;
ALTER TABLE store_game ADD COLUMN evidence_url text, ADD COLUMN checked_on date,
    ADD COLUMN directory_managed boolean NOT NULL DEFAULT false;
CREATE TABLE store_directory_edition (provider text PRIMARY KEY, as_of date NOT NULL);

-- A missing establishment disappears from search but keeps its ID, favorites and event history.
CREATE FUNCTION apply_semas_directory(edition date, rows jsonb) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF edition IS NULL OR jsonb_typeof(rows) IS DISTINCT FROM 'array' OR jsonb_array_length(rows)=0 THEN
        RAISE EXCEPTION 'Expected a complete nonempty directory';
    END IF;
    INSERT INTO store_directory_edition VALUES ('SEMAS',edition)
    ON CONFLICT(provider) DO UPDATE SET as_of=EXCLUDED.as_of WHERE store_directory_edition.as_of<=EXCLUDED.as_of;
    IF NOT FOUND THEN RAISE EXCEPTION 'Cannot replace the directory with an older edition'; END IF;

    INSERT INTO store AS s(semas_id,name,address,region,source_date,location,hours)
        SELECT key,name,address,region,edition,ST_SetSRID(ST_MakePoint(lon,lat),4326)::geography,hours
          FROM jsonb_to_recordset(rows) AS r(key text,name text,address text,region text,lon float8,lat float8,hours jsonb)
    ON CONFLICT(semas_id) DO UPDATE SET name=EXCLUDED.name,address=EXCLUDED.address,region=EXCLUDED.region,
        source_date=edition,location=EXCLUDED.location,hours=EXCLUDED.hours,listed=true;
    UPDATE store s SET listed=false WHERE s.semas_id IS NOT NULL AND s.listed AND NOT EXISTS
        (SELECT FROM jsonb_array_elements(rows) AS r WHERE r->>'key'=s.semas_id);

    DELETE FROM store_game g USING store s WHERE g.store_id=s.id AND g.directory_managed AND s.semas_id IS NOT NULL;
    INSERT INTO store_game(store_id,game_code,evidence_url,checked_on,directory_managed)
        SELECT s.id,e.key,e.value,coalesce(r.checked,edition),true FROM jsonb_to_recordset(rows) AS r(key text,games jsonb,checked date)
        JOIN store s ON s.semas_id=r.key CROSS JOIN LATERAL jsonb_each_text(r.games) AS e
    ON CONFLICT(store_id,game_code) DO NOTHING;
END $$;

-- Public SEMAS edition 2026-09-30; see docs/STORES.md for provenance and selection.
SELECT apply_semas_directory(DATE '2026-09-30', $directory$[
{"key":"MA010120220803052951","name":"포켓몬카드SSR","address":"경상북도 영천시 야사시장길 43","region":"경상북도","lon":128.948009808493,"lat":35.9735340183237,"hours":{},"games":{"POKEMON":"https://www.data.go.kr/data/15083033/fileData.do"},"checked":null},
{"key":"MA010120220805023997","name":"티씨지드로우","address":"부산광역시 남구 수영로298번길 37","region":"부산광역시","lon":129.099905206452,"lat":35.1353058695073,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA010120220806202107","name":"TCGKorea","address":"대전광역시 서구 문정로170번길 193","region":"대전광역시","lon":127.397557673301,"lat":36.3506414363222,"hours":{},"games":{},"checked":null},
{"key":"MA010120220806617714","name":"티씨지999","address":"충청남도 천안시 동남구 원성24길 19-5","region":"충청남도","lon":127.160699053849,"lat":36.8132657080095,"hours":{},"games":{},"checked":null},
{"key":"MA010120220806671985","name":"카드빌리지","address":"경기도 평택시 통복시장1로 29","region":"경기도","lon":127.087235715398,"lat":36.999977353987,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA010120220807014543","name":"하비게임몰","address":"경기도 부천시 원미구 중동로254번길 104","region":"경기도","lon":126.774641832378,"lat":37.5015408909579,"hours":{},"games":{"WEISS":"https://www.hobbygamemall.com/goods/goods_list.php?cateCd=001003&page=4","NIVEL":"https://www.hobbygamemall.com/goods/goods_list.php?cateCd=001003&page=4"},"checked":"2026-11-25"},
{"key":"MA010120220807486519","name":"카드스퀘어","address":"서울특별시 중구 다산로40길 51","region":"서울특별시","lon":127.018981198841,"lat":37.5634368613425,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA010120220810059323","name":"티씨지팩토리","address":"전남광주통합특별시 무안군 삼향읍 남악3로 80","region":"전남광주통합특별시","lon":126.460677215388,"lat":34.8126493029636,"hours":{},"games":{},"checked":null},
{"key":"MA010120220811228442","name":"티씨지플레이존","address":"경상남도 김해시 능동로155번길 10-5","region":"경상남도","lon":128.807781092367,"lat":35.2033271673292,"hours":{},"games":{},"checked":null},
{"key":"MA010120220812519021","name":"원주카드스페이스","address":"강원특별자치도 원주시 능라동길 42","region":"강원특별자치도","lon":127.92922679968,"lat":37.3338239850806,"hours":{"text":"월 휴무 · 화–일 12:00–22:00","url":"https://pokemonkorea.co.kr/pokemon_cardshop/menu202","checked":"2026-11-25"},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store","POKEMON":"https://pokemonkorea.co.kr/pokemon_cardshop/menu202"},"checked":"2026-11-25"},
{"key":"MA010120220812935582","name":"카드킹덤","address":"서울특별시 마포구 신촌로 254","region":"서울특별시","lon":126.953971426859,"lat":37.5570233272412,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202211A0033892","name":"새절TCGLABO","address":"서울특별시 은평구 가좌로 251","region":"서울특별시","lon":126.91515837022,"lat":37.5914558472438,"hours":{},"games":{},"checked":null},
{"key":"MA0101202211A0061851","name":"티씨지팩토리","address":"울산광역시 중구 번영로 454-1","region":"울산광역시","lon":129.333932688037,"lat":35.5625872975305,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202301A0044573","name":"티씨지스타디움","address":"대전광역시 유성구 유성대로668번길 107","region":"대전광역시","lon":127.335566554096,"lat":36.3518499270331,"hours":{},"games":{},"checked":null},
{"key":"MA0101202302A0091065","name":"스카이스크레이퍼","address":"대전광역시 중구 목척8길 31","region":"대전광역시","lon":127.426451402686,"lat":36.3294002495626,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202310A0012392","name":"스카이스크레이퍼","address":"경기도 부천시 원미구 부일로 705","region":"경기도","lon":126.808238485434,"lat":37.4849856584271,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202311A0087989","name":"밀짚모자해적단TCG","address":"서울특별시 서대문구 연세로9길 37","region":"서울특별시","lon":126.934583101448,"lat":37.5585368622095,"hours":{},"games":{},"checked":null},
{"key":"MA0101202406A0398687","name":"카드숲","address":"서울특별시 관악구 조원중앙로 13","region":"서울특별시","lon":126.904859032406,"lat":37.4811295239472,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store","RIFTBOUND":"https://playriftbound.com/ko-KR/events/117586446689253331"},"checked":"2026-11-25"},
{"key":"MA0101202406A0514008","name":"티씨지플레이어","address":"전남광주통합특별시 서구 화운로 106","region":"전남광주통합특별시","lon":126.879590544781,"lat":35.148992168292,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202411A0016140","name":"어바웃티씨지","address":"서울특별시 관악구 조원로 16","region":"서울특별시","lon":126.903985718634,"lat":37.4832732177658,"hours":{},"games":{},"checked":null},
{"key":"MA0101202502A0001241","name":"듀얼스파크","address":"대구광역시 중구 동성로2길 50-13","region":"대구광역시","lon":128.597469471239,"lat":35.8681632632775,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202504A0047772","name":"라스TCG","address":"경기도 안산시 단원구 중앙대로 907","region":"경기도","lon":126.837715624412,"lat":37.3171066732133,"hours":{},"games":{},"checked":null},
{"key":"MA0101202509A0023125","name":"티씨지아레나","address":"인천광역시 미추홀구 염창로 77","region":"인천광역시","lon":126.682669354413,"lat":37.465622801529,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store","RIFTBOUND":"https://playriftbound.com/ko-KR/events/117545207299594342"},"checked":"2026-11-25"},
{"key":"MA0101202603A0000464","name":"카드프라임","address":"충청남도 천안시 서북구 백석로 130","region":"충청남도","lon":127.125624397818,"lat":36.8223550712873,"hours":{"text":"평일·주말 13:00–21:00","url":"https://pokemonkorea.co.kr/pokemon_cardshop/menu776","checked":"2026-11-25"},"games":{"POKEMON":"https://pokemonkorea.co.kr/pokemon_cardshop/menu776"},"checked":"2026-11-25"},
{"key":"MA0101202603A0012248","name":"카드엘릭서","address":"경상남도 창원시 마산회원구 합성남7길 31","region":"경상남도","lon":128.585275352034,"lat":35.2390251704185,"hours":{},"games":{"YUGIOH":"https://www.yugioh.co.kr/site/event_store.php?code=store"},"checked":"2026-11-25"},
{"key":"MA0101202603A0013682","name":"티씨지아일랜드","address":"제주특별자치도 제주시 중앙로 197-1","region":"제주특별자치도","lon":126.528567916826,"lat":33.5017134301506,"hours":{},"games":{},"checked":null},
{"key":"MA0101202603A0041253","name":"카드챔프","address":"서울특별시 양천구 오목로 194","region":"서울특별시","lon":126.858941175913,"lat":37.5251968283012,"hours":{"text":"평일·주말 12:30–21:10","url":"https://pokemonkorea.co.kr/pokemon_cardshop/menu758","checked":"2026-11-25"},"games":{"POKEMON":"https://pokemonkorea.co.kr/pokemon_cardshop/menu758"},"checked":"2026-11-25"},
{"key":"MA0101202604A0022602","name":"티씨지라이프","address":"경상남도 창원시 성산구 원이대로579번길 10","region":"경상남도","lon":128.679467037462,"lat":35.2292650342107,"hours":{},"games":{},"checked":null},
{"key":"MA0101202607A0116793","name":"티씨지컬렉트스토어","address":"경기도 하남시 미사강변동로 100-1","region":"경기도","lon":127.193593652775,"lat":37.5639644219305,"hours":{},"games":{},"checked":null},
{"key":"MA0101202607A0165871","name":"센티널TCG","address":"경기도 고양시 덕양구 꽃마을로 38","region":"경기도","lon":126.891990924035,"lat":37.6000053460935,"hours":{},"games":{},"checked":null},
{"key":"MA0101202608A0048894","name":"모두의TCG","address":"경기도 성남시 분당구 황새울로360번길 12","region":"경기도","lon":127.125001278628,"lat":37.3865311007835,"hours":{},"games":{},"checked":null},
{"key":"MA0101202608A0095138","name":"오티엘티씨지","address":"경기도 안산시 상록구 광덕1로 365","region":"경기도","lon":126.850064677761,"lat":37.307851325031,"hours":{},"games":{},"checked":null},
{"key":"MA0101202608A0097170","name":"티씨지고","address":"경기도 평택시 청북읍 안청로 336","region":"경기도","lon":126.915788966306,"lat":37.0179831319797,"hours":{},"games":{},"checked":null},
{"key":"MA0101202608A0104832","name":"카드웨이브강릉","address":"강원특별자치도 강릉시 솔올로 40","region":"강원특별자치도","lon":128.878411473624,"lat":37.7654835372435,"hours":{"text":"월 휴무 · 화·목·토·일 12:00–19:00 · 수·금 12:00–21:00","url":"https://pokemonkorea.co.kr/pokemon_cardshop/menu809","checked":"2026-11-25"},"games":{"POKEMON":"https://pokemonkorea.co.kr/pokemon_cardshop/menu809"},"checked":"2026-11-25"}
]$directory$::jsonb);
