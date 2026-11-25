package kr.tcghub;

import java.util.*;
import jakarta.validation.constraints.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
class DeckRules {
    record Section(String section, Integer minCards, Integer maxCards) {}
    record Rule(String gameCode, String format, int version, Integer maxCopiesPerCard, String source, List<Section> sections) {}
    record Line(@Positive long cardId, @NotBlank @Size(max=64) String section, @Min(1) @Max(999) int quantity) {}
    record CardInfo(long id, String name, String identity, String kind, String stage, boolean basicEnergy, boolean triggerCard) {}
    static class Invalid extends RuntimeException { Invalid(String reason) { super(reason); } }
    private final JdbcClient db;
    DeckRules(JdbcClient db) { this.db = db; }

    Rule rule(String game, String format, int version) {
        var sections = db.sql("""
            select section,min_cards,max_cards from deck_section_rule where game_code=? and format=? and rule_version=?
            order by case section when 'MAIN' then 0 when 'EXTRA' then 1 when 'LEADER' then 1
                       when 'LEGEND' then 1 when 'RUNE' then 2 when 'BATTLEFIELD' then 3 else 4 end,section
            """).param(game).param(format).param(version).query(Section.class).list();
        return db.sql("select max_copies_per_card,details->>'source' from deck_rule where game_code=? and format=? and version=?")
                .param(game).param(format).param(version).query((r,n)->new Rule(game,format,version,
                        r.getObject(1,Integer.class),r.getString(2),sections))
                .optional().orElseThrow(()->new Invalid("선택한 게임의 덱 규칙을 찾을 수 없습니다."));
    }

    static String sectionName(String section) {
        return switch(section) {
            case "MAIN" -> "메인"; case "SIDE" -> "사이드"; case "EXTRA" -> "엑스트라";
            case "LEADER" -> "리더"; case "RUNE" -> "룬"; case "LEGEND" -> "레전드"; case "BATTLEFIELD" -> "전장";
            default -> section;
        };
    }

    void validate(Rule rule, List<Line> lines, boolean complete) {
        var quantities = new HashMap<String,Integer>();
        var counts = new HashMap<String,Integer>();
        var unique = new HashSet<String>();
        var allowed = new HashSet<String>();
        rule.sections().forEach(s->allowed.add(s.section()));
        var cards = new HashMap<Long,CardInfo>();
        if (!lines.isEmpty()) {
            var ids = lines.stream().map(Line::cardId).distinct().toList();
            var results = db.sql("""
                select id,name,lower(trim(case when game_code='NIVEL' then coalesce(nullif(number,''),name)
                    else coalesce(nullif(original_name,''),name) end)) as identity,
                    lower(coalesce(specs->>'type',specs->>'card_type',specs->>'k','')) as kind,
                    lower(coalesce(specs->>'stage','')) as stage,
                    (name ~* '^(기본.*에너지|basic .*energy|基本.*エネルギー)$'
                        or lower(coalesce(specs->>'card_type','')) in ('basic energy','기본 에너지','기본에너지')) as basic_energy,
                    (coalesce(effect,'') ~ '([[]트리거[]]|【트리거】)' or specs->>'트리거' in ('O','있음','트리거')) is true as trigger_card
                from card where game_code=:game and status='PUBLISHED' and id in (:ids)
                """).param("game",rule.gameCode()).param("ids",ids).query(CardInfo.class).list();
            results.forEach(card->cards.put(card.id(),card));
            if (cards.size()!=ids.size()) throw new Invalid("이 게임의 공개 도감에 있는 카드만 추가할 수 있습니다.");
        }
        int climax=0, triggers=0, basicPokemon=0;
        boolean checkBasicPokemon=true;
        boolean standard = rule.version()==2 && rule.format().equals("CONSTRUCTED");
        for (var line : lines) {
            var card = cards.get(line.cardId());
            String section=line.section();
            if (!allowed.contains(section)) throw new Invalid("선택한 게임에서 사용할 수 없는 구역입니다.");
            if (!unique.add(section+"/"+line.cardId())) throw new Invalid("같은 구역의 중복 항목은 수량으로 합쳐 주세요.");
            quantities.merge(section,line.quantity(),Integer::sum);
            boolean unlimited = standard && (rule.gameCode().equals("POKEMON") && card.basicEnergy()
                    || rule.gameCode().equals("RIFTBOUND") && section.equals("RUNE"));
            if (!unlimited) {
                int copies=counts.merge(card.identity(),line.quantity(),Integer::sum);
                Integer limit=rule.maxCopiesPerCard();
                if (standard && rule.gameCode().equals("RIFTBOUND") && section.equals("BATTLEFIELD")) limit=1;
                if (limit!=null && copies>limit) throw new Invalid(card.name()+" 카드는 합계 "+limit+"장까지 넣을 수 있습니다.");
            }
            if (!standard) continue;
            String kind=card.kind();
            switch (rule.gameCode()) {
                case "YUGIOH" -> {
                    boolean extra=kind.matches(".*(fusion|synchro|xyz|link|융합|싱크로|엑시즈|링크).*");
                    if (extra && section.equals("MAIN") || !kind.isEmpty() && !extra && section.equals("EXTRA"))
                        throw new Invalid(card.name()+" 카드의 메인·엑스트라 구역을 확인해 주세요.");
                }
                case "NIVEL" -> {
                    if (!kind.isEmpty() && (kind.contains("리더") || kind.contains("leader")) != section.equals("LEADER"))
                        throw new Invalid("리더 카드 한 장은 리더 구역에 배치해 주세요.");
                    if (card.triggerCard()) triggers+=line.quantity();
                }
                case "WEISS" -> { if (kind.equals("cx") || kind.contains("climax") || kind.contains("클라이맥스")) climax+=line.quantity(); }
                case "POKEMON" -> {
                    if (card.stage().contains("기본") || card.stage().equals("basic") || kind.startsWith("기본 포켓몬")) basicPokemon+=line.quantity();
                    if (card.stage().isEmpty() && (kind.isEmpty() || kind.equals("포켓몬") || kind.equals("pokémon"))) checkBasicPokemon=false;
                }
                case "RIFTBOUND" -> {
                    String special = switch(kind) {case "rune" -> "RUNE"; case "legend" -> "LEGEND"; case "battlefield" -> "BATTLEFIELD"; default -> null;};
                    if (special!=null && !special.equals(section) || !kind.isEmpty() && special==null && !Set.of("MAIN","SIDE").contains(section))
                        throw new Invalid(card.name()+" 카드의 구역을 확인해 주세요.");
                }
                default -> { }
            }
        }
        for (var section:rule.sections()) {
            int quantity=quantities.getOrDefault(section.section(),0);
            if (section.maxCards()!=null && quantity>section.maxCards())
                throw new Invalid(sectionName(section.section())+" 구역은 "+section.maxCards()+"장까지 넣을 수 있습니다.");
            if (complete && section.minCards()!=null && quantity<section.minCards())
                throw new Invalid(sectionName(section.section())+" 구역에 최소 "+section.minCards()+"장이 필요합니다.");
        }
        if (climax>8) throw new Invalid("클라이맥스 카드는 최대 8장입니다.");
        if (triggers>8) throw new Invalid("트리거 카드는 최대 8장입니다.");
        if (standard && complete && rule.gameCode().equals("POKEMON") && checkBasicPokemon && basicPokemon==0)
            throw new Invalid("기본 포켓몬이 최소 한 장 필요합니다.");
    }
}
