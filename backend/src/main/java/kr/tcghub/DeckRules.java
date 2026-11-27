package kr.tcghub;

import java.util.*;
import jakarta.validation.constraints.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
class DeckRules {
    record Section(String section, Integer minCards, Integer maxCards) {}
    record Rule(String gameCode, String format, int version, Integer maxCopiesPerCard, String source, List<Section> sections) {}
    record Line(@Positive long cardId, @NotBlank @Size(max=64) String section,
                @Min(1) @Max(999) int quantity, @Positive Long variantId,
                @Positive @Max(32767) Integer neuronArtwork) {
        Line(long cardId,String section,int quantity,Long variantId) { this(cardId,section,quantity,variantId,null); }
        Line(long cardId,String section,int quantity) { this(cardId,section,quantity,null); }
    }
    record CardInfo(long id, String name, String identity, String kind, String stage, boolean basicEnergy,
                    boolean triggerCard, String domains, String tags, String supertype, boolean unlimitedCopies) {
        Set<String> labels(String value) {
            return value == null || value.isBlank() ? Set.of() : new HashSet<>(List.of(value.split("\u001f")));
        }
    }
    static class Invalid extends RuntimeException { Invalid(String reason) { super(reason); } }
    // Bandai Namco Korea tournament list effective 2026-11-13 (announcement 1171).
    // OP05-041 and OP02-052 were released from the list on 2026-07-01.
    private static final Set<String> ONE_PIECE_BANNED=Set.of("op06-047","op03-040","op02-117",
            "op06-086","eb01-059","op07-045","op03-098","st10-001","op06-116","st06-015","op02-024");
    private static final List<Set<String>> ONE_PIECE_PAIRS=List.of(Set.of("op07-115","eb04-058"),
            Set.of("op11-040","op11-067"),Set.of("op11-040","op08-069"));
    private final JdbcClient db;
    DeckRules(JdbcClient db) { this.db = db; }

    Rule current(String game) {
        int version = db.sql("select max(version) from deck_rule where game_code=? and format='CONSTRUCTED' having count(*)>0")
                .param(game).query(Integer.class).optional().orElseThrow(()->new Invalid("덱 규칙이 없는 게임입니다."));
        return rule(game,"CONSTRUCTED",version);
    }

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
            case "DON" -> "두웅!!"; case "CHAMPION" -> "선택한 챔피언";
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
                select id,name,lower(trim(case when game_code in ('NIVEL','ONEPIECE') then coalesce(nullif(number,''),name)
                    when game_code='RIFTBOUND' then coalesce(nullif(specs->>'cleanName',''),original_name,name)
                    else coalesce(nullif(original_name,''),name) end)) as identity,
                    lower(coalesce(nullif(specs->>'type',''),nullif(specs->>'card_type',''),
                        case when game_code='YUGIOH' and specs->>'k'='몬스터'
                             then concat_ws(' ',specs->>'k',specs->>'sub') else specs->>'k' end,'')) as kind,
                    lower(coalesce(specs->>'stage','')) as stage,
                    (name ~* '^(기본.*에너지|basic .*energy|基本.*エネルギー)$'
                        or lower(coalesce(specs->>'card_type','')) in ('basic energy','기본 에너지','기본에너지')) as basic_energy,
                    (coalesce(effect,'') ~ '([[]트리거[]]|【트리거】)' or specs->>'트리거' in ('O','있음','트리거')) is true as trigger_card,
                    (select string_agg(lower(trim(v)),chr(31)) from jsonb_array_elements_text(
                        case when jsonb_typeof(specs->'colors')='array' then specs->'colors'
                             when jsonb_typeof(specs->'domains')='array' then specs->'domains' else '[]'::jsonb end) v) as domains,
                    (select string_agg(lower(trim(v)),chr(31)) from jsonb_array_elements_text(
                        case when jsonb_typeof(specs->'tags')='array' then specs->'tags' else '[]'::jsonb end) v) as tags,
                    lower(coalesce(specs->>'supertype','')) as supertype,
                    lower(concat_ws(' ',effect,specs->'texts'->>'en')) ~ 'you may (have|include) any number of (this card|cards with this card number) in your deck' as unlimited_copies
                from card where game_code=:game and status='PUBLISHED' and id in (:ids)
                """).param("game",rule.gameCode()).param("ids",ids).query(CardInfo.class).list();
            results.forEach(card->cards.put(card.id(),card));
            if (cards.size()!=ids.size()) throw new Invalid("이 게임의 공개 도감에 있는 카드만 추가할 수 있습니다.");
        }
        int climax=0, triggers=0, basicPokemon=0;
        boolean checkBasicPokemon=true;
        boolean standard = rule.version()>=2 && rule.format().equals("CONSTRUCTED");
        boolean riot = standard && rule.gameCode().equals("RIFTBOUND") && rule.version()>=3;
        boolean op = standard && rule.gameCode().equals("ONEPIECE");
        var leader = lines.stream().filter(l -> l.section().equals(riot ? "LEGEND" : "LEADER")).findFirst()
                .map(l -> cards.get(l.cardId())).orElse(null);
        Set<String> bans = riot ? new HashSet<>(db.sql("""
                select lower(replace(v,'’','''')) from deck_rule r,
                lateral jsonb_array_elements_text(r.details->'banned') v where r.game_code=? and r.format=? and r.version=?
                """).param(rule.gameCode()).param(rule.format()).param(rule.version()).query(String.class).list()) : Set.of();
        int signatureCopies=0;
        for (var line : lines) {
            var card = cards.get(line.cardId());
            String section=line.section();
            if (!allowed.contains(section)) throw new Invalid("선택한 게임에서 사용할 수 없는 구역입니다.");
            if (line.neuronArtwork()!=null && (!"YUGIOH".equals(rule.gameCode()) || line.variantId()!=null))
                throw new Invalid("한 카드에는 일러스트 판본을 하나만 선택해 주세요.");
            if (!unique.add(section+"/"+line.cardId()+"/"+line.variantId()+"/"+line.neuronArtwork()))
                throw new Invalid("같은 구역의 같은 일러스트는 수량으로 합쳐 주세요.");
            quantities.merge(section,line.quantity(),Integer::sum);
            boolean unlimited = standard && (rule.gameCode().equals("POKEMON") && card.basicEnergy()
                    || rule.gameCode().equals("RIFTBOUND") && section.equals("RUNE")
                    || op && (section.equals("DON") || card.unlimitedCopies()));
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
                    if (kind.equals("token") || kind.equals("토큰"))
                        throw new Invalid("토큰은 덱에 넣을 수 없습니다.");
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
                    boolean chosen=riot && section.equals("CHAMPION") && kind.equals("unit") && card.supertype().equals("champion");
                    if (special!=null && !special.equals(section) || !kind.isEmpty() && special==null && !chosen && !Set.of("MAIN","SIDE").contains(section))
                        throw new Invalid(card.name()+" 카드의 구역을 확인해 주세요.");
                    if (riot) {
                        if (bans.contains(card.identity().replace('’','\'')) || card.supertype().equals("token"))
                            throw new Invalid(card.name()+" 카드는 이 대회 규칙에서 덱에 넣을 수 없습니다.");
                        boolean signature=card.supertype().equals("signature");
                        if (signature) signatureCopies+=line.quantity();
                        if (leader!=null) {
                            var colors=card.labels(card.domains());
                            if (!colors.isEmpty()) {
                                colors=new HashSet<>(colors);
                                colors.remove("colorless");
                                if (!leader.labels(leader.domains()).containsAll(colors))
                                    throw new Invalid(card.name()+" 카드의 도메인이 레전드와 일치하지 않습니다.");
                            }
                            if ((chosen || signature) && Collections.disjoint(leader.labels(leader.tags()),card.labels(card.tags())))
                                throw new Invalid("선택한 챔피언과 시그니처 카드는 레전드의 챔피언 태그와 일치해야 합니다.");
                        }
                    }
                }
                case "ONEPIECE" -> {
                    if (ONE_PIECE_BANNED.contains(card.identity())) throw new Invalid(card.name()+" 카드는 한국 공식 대회 금지 카드입니다.");
                    String required=switch (kind) {
                        case "leader","리더" -> "LEADER"; case "don","don!!","두웅!!" -> "DON";
                        case "character","event","stage","캐릭터","이벤트","스테이지" -> "MAIN"; default -> "";
                    };
                    if (!required.equals(section)) throw new Invalid(card.name()+" 카드 종류와 구역을 확인해 주세요.");
                    if (leader!=null && section.equals("MAIN") && (!leader.labels(leader.domains()).containsAll(card.labels(card.domains()))
                            || card.labels(card.domains()).isEmpty()))
                        throw new Invalid(card.name()+" 카드의 색이 리더 색에 포함되어야 합니다.");
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
        if (signatureCopies>3) throw new Invalid("시그니처 카드는 전체 덱과 사이드보드 합계 3장까지입니다.");
        if (op && ONE_PIECE_PAIRS.stream().anyMatch(counts.keySet()::containsAll))
            throw new Invalid("한국 공식 대회 금지 페어의 두 카드를 함께 넣을 수 없습니다.");
        if (climax>8) throw new Invalid("클라이맥스 카드는 최대 8장입니다.");
        if (triggers>8) throw new Invalid("트리거 카드는 최대 8장입니다.");
        if (standard && complete && rule.gameCode().equals("POKEMON") && checkBasicPokemon && basicPokemon==0)
            throw new Invalid("기본 포켓몬이 최소 한 장 필요합니다.");
    }
}
