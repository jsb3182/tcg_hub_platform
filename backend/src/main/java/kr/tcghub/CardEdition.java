package kr.tcghub;

/** Resolve each field independently; an available name does not imply translated rules or artwork. */
final class CardEdition {
    private CardEdition() {}
    static final String IMAGE_JOIN = """
            cross join lateral (select case
                when nullif(c.specs->'images'->>:lang,'') is not null then :lang
                when nullif(c.specs->'images'->>(c.specs->>'language'),'') is not null then c.specs->>'language'
                end as lang) art
            """;
    static final String FIELDS = """
            coalesce(nullif(c.specs->'names'->>:lang,''),c.name) as name,
            case when nullif(c.specs->'names'->>:lang,'') is not null then :lang
                 else coalesce(c.specs->>'language','und') end as language,
            coalesce(nullif(c.specs->'texts'->>:lang,''),c.effect) as effect,
            case when nullif(c.specs->'texts'->>:lang,'') is not null then :lang
                 when nullif(c.effect,'') is not null then coalesce(c.specs->>'language','und') end as "effectLanguage",
            c.specs->'images'->>art.lang as "imageUrl", art.lang as "imageLanguage",
            c.specs->>'productCode' as "productCode", c.specs->'imageProducts'->>art.lang as "imageProduct",
            c.specs->'imageSources'->>art.lang as "imageSource"
            """;
}
