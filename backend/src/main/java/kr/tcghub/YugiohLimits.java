package kr.tcghub;

import java.time.LocalDate;
import java.util.*;
import java.util.regex.Pattern;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
class YugiohLimits {
    record Violation(long cardId, String name, int limit, int copies) {}
    record Report(String region, LocalDate effectiveOn, String sourceUrl, String status,
                  List<Long> unknownCardIds, List<Violation> violations) {}
    private record Snapshot(LocalDate effectiveOn, String sourceUrl, LocalDate verifiedOn, boolean verified) {}
    private record Card(long id, String name, String identity, Integer limit, boolean released) {}
    private static final Pattern ALWAYS_NAMED = Pattern.compile(
            "\\(This card(?:'s name is| is) always treated as \"([^\"\\r\\n]+)\"\\.\\)");
    private final JdbcClient db;

    YugiohLimits(JdbcClient db) { this.db = db; }

    static String selection(String game, String requested, String previous) {
        if (requested == null) return previous;
        if (requested.isEmpty()) return null;
        if (!"YUGIOH".equals(game) || !Set.of("OCG","TCG").contains(requested))
            throw new DeckRules.Invalid("유희왕의 OCG(일본) 또는 TCG Advanced 규칙을 선택해 주세요.");
        return requested;
    }

    private static String identity(String englishName, String effect) {
        var matcher = ALWAYS_NAMED.matcher(effect == null ? "" : effect);
        return (matcher.find() ? matcher.group(1) : englishName).toLowerCase(Locale.ROOT).strip();
    }

    Report check(String region, List<DeckRules.Line> entries) {
        if (region == null) return null;
        var snapshot = db.sql("""
                select effective_on, source_url, verified_on, evidence_status='VERIFIED'
                      and current_date between verified_on and verified_on+7 as verified
                from yugioh_limit_list where region=?
                """).param(region).query(Snapshot.class).optional();
        String url = "https://www.db.yugioh-card.com/yugiohdb/forbidden_limited.action?request_locale="
                   + ("OCG".equals(region) ? "ja" : "en");
        var source = snapshot.orElse(new Snapshot(null, url, null, false));
        var quantities = new LinkedHashMap<Long,Integer>();
        entries.forEach(line -> quantities.merge(line.cardId(), line.quantity(), Integer::sum));
        var unknown = new LinkedHashSet<>(quantities.keySet());
        var aggregates = new LinkedHashMap<String,Violation>();
        if (!quantities.isEmpty()) {
            // Only provider-owned cards or reconciled legacy identities are evidence of regional release.
            // Reprints of one CID share a canonical English name, including when the user views another language.
            var cards = db.sql("""
                  select c.id,c.name,k.cid,anchor.name as canonical,anchor.effect,l.max_copies,
                       coalesce(anchor.regional_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                           and anchor.regional_date<=to_char(cast(:cutoff as date),'YYYY-MM-DD')
                           and jsonb_exists(anchor.formats, :region),false) as released
                  from card c
                  """ + CardEdition.LEGACY_JOIN + """
                  left join feed_source origin on origin.id=c.source_id
                  cross join lateral (select case when starts_with(c.legacy_key,'catalog:YUGIOH:')
                        and origin.provider='CATALOG' and origin.source_key='YUGIOH'
                        then c.specs->>'konami_id' when starts_with(c.legacy_key,'legacy:') then linked.konami_id::text end as cid) k
                  left join lateral (
                     select ref.name,ref.effect,ref.specs->'formats' as formats,
                            ref.specs->>(case when :region='OCG' then 'ocg_date' else 'tcg_date' end) as regional_date
                       from card ref join feed_source fs on fs.id=ref.source_id
                      where ref.game_code='YUGIOH' and starts_with(ref.legacy_key,'catalog:YUGIOH:')
                        and fs.provider='CATALOG' and fs.source_key='YUGIOH'
                        and ref.specs->>'konami_id'=k.cid order by ref.id limit 1
                  ) anchor on true
                  left join yugioh_card_limit l on l.region=:region and l.konami_id::text=k.cid
                  where c.game_code='YUGIOH' and c.status='PUBLISHED' and c.id in (:ids)
                  order by c.id
                  """).param("region",region).param("cutoff",source.verifiedOn()).param("ids",quantities.keySet()).query((row,n)->{
                      var canonical = row.getString("canonical");
                      var cap = row.getObject("max_copies",Integer.class);
                      var key = canonical == null ? null : identity(canonical,row.getString("effect"));
                      if (key == null && cap != null) key = "cid:"+row.getString("cid");
                      return new Card(row.getLong("id"),row.getString("name"),
                              key,cap,row.getBoolean("released"));
                  }).list();
            for (var card : cards) {
                if (card.identity() == null) continue;
                if (card.released() || Objects.equals(card.limit(),0)) unknown.remove(card.id());
                else if (card.limit() == null) continue;
                int limit = card.limit() == null ? 3 : card.limit();
                var value = new Violation(card.id(),card.name(),limit,quantities.get(card.id()));
                aggregates.merge(card.identity(),value,(first,next)->new Violation(first.cardId(),first.name(),
                        Math.min(first.limit(),next.limit()),first.copies()+next.copies()));
            }
        }
        var violations = aggregates.values().stream().filter(v->v.copies()>v.limit()).toList();
        String status = !source.verified() ? "UNAVAILABLE" : unknown.isEmpty() ? "CHECKED" : "PARTIAL";
        return new Report(region, source.effectiveOn(), source.sourceUrl(), status, List.copyOf(unknown), violations);
    }

    void requireComplete(Report result) {
        if (result == null) return;
        if (!result.status().equals("CHECKED"))
            throw new DeckRules.Invalid("선택한 지역의 금제표 또는 카드 판정을 확인할 수 없습니다. 초안으로 저장해 주세요.");
        if (!result.violations().isEmpty()) {
            var first = result.violations().get(0);
            throw new DeckRules.Invalid(first.name()+" 카드의 지역별 허용 수량은 "+first.limit()+"장입니다.");
        }
    }
}
