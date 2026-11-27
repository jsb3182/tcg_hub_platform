ALTER TABLE product_release
    ADD COLUMN manual boolean NOT NULL DEFAULT false,
    ADD COLUMN version bigint NOT NULL DEFAULT 1,
    ADD COLUMN selected_pack_id bigint,
    ADD COLUMN product_type text NOT NULL DEFAULT 'UNKNOWN'
      CHECK (product_type IN ('BOOSTER','STARTER','PROMO','ACCESSORY','SPECIAL','UNKNOWN')),
    ADD FOREIGN KEY (game_code,selected_pack_id) REFERENCES pack(game_code,id);

CREATE FUNCTION release_kind(label text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN label ~* 'スターター|ストラクチャー|構築済み|トライアルデッキ|스타터|스트럭처|트라이얼 덱|starter|structure deck|trial deck|battle deck' THEN 'STARTER'
                WHEN label ~* '부스터|확장팩|ブースター|拡張パック|booster' THEN 'BOOSTER'
                WHEN label ~* '프로모|プロモ|promo' THEN 'PROMO'
                WHEN label ~* '슬리브|플레이매트|スリーブ|sleeves|playmat|accessor' THEN 'ACCESSORY'
                WHEN label ~* '스페셜|スペシャル|special|collector.s box|premium collection' THEN 'SPECIAL'
                ELSE 'UNKNOWN' END
$$;
UPDATE product_release SET product_type=release_kind(name);
CREATE FUNCTION classify_product_release() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT NEW.manual THEN NEW.product_type:=release_kind(NEW.name); END IF;
    IF TG_OP='UPDATE' THEN NEW.version:=OLD.version+1; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER classify_product_release BEFORE INSERT OR UPDATE ON product_release
FOR EACH ROW EXECUTE FUNCTION classify_product_release();

CREATE VIEW tcg_release_schedule AS SELECT id,game_code AS game_type,coalesce(names->>'ko',CASE WHEN region='KR' THEN name END) AS product_name_ko,
    name AS product_name_orig,region,release_date,product_type,source_url,coalesce(catalog_code,code) AS linked_set_code
    FROM product_release;
