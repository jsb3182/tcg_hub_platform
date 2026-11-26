package kr.tcghub;

/** Resolve each field independently; an available name does not imply translated rules or artwork. */
final class CardEdition {
    private CardEdition() {}
    static final String FIELDS = """
            coalesce(nullif(c.specs->'names'->>:lang,''),c.name) as name,
            case when nullif(c.specs->'names'->>:lang,'') is not null then :lang
                 else coalesce(c.specs->>'language','und') end as language,
            coalesce(nullif(c.specs->'texts'->>:lang,''),c.effect) as effect,
            case when nullif(c.specs->'texts'->>:lang,'') is not null then :lang
                 when nullif(c.effect,'') is not null then coalesce(c.specs->>'language','und') end as "effectLanguage",
            coalesce(nullif(c.specs->'images'->>:lang,''),c.specs->'images'->>(c.specs->>'language')) as "imageUrl",
            case when nullif(c.specs->'images'->>:lang,'') is not null then :lang
                 when c.specs->'images'->>(c.specs->>'language') is not null then c.specs->>'language' end as "imageLanguage"
            """;
}
