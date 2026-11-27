package kr.tcghub;

import java.util.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
class DeckCodes {
    private static final String PREFIX="TCG1.";
    private static final String PRINT_KEY="""
            case when c.legacy_key is not null then 's:' || c.legacy_key else 'm:' ||
            encode(sha256(convert_to(jsonb_build_array(c.game_code,p.code,p.name,c.number,c.name,c.rarity)::text,'UTF8')),'hex') end
            """;
    record Printing(String key,String section,int quantity,Integer illustration,Integer neuronArtwork) {}
    record Recipe(String game,String name,List<Printing> entries,String nameJa,String nameEn) {}
    record Code(String code) {}
    final JdbcClient db;
    final ObjectMapper json;
    DeckCodes(JdbcClient db,ObjectMapper json) {this.db=db; this.json=json;}

    Code encode(DeckApi.Header deck) {
        var rows=db.sql("select "+PRINT_KEY+" as key,e.section,e.quantity,c.status,v.position,e.neuron_artwork from deck_entry e "+
                       "join card c on c.id=e.card_id left join pack p on p.id=c.pack_id left join card_variant v on v.id=e.variant_id "+
                       "where e.deck_id=? order by e.section,e.display_order,e.card_id")
                .param(deck.id()).query((r,n)->{
                    if (!r.getString("status").equals("PUBLISHED")) throw new DeckRules.Invalid("비공개 카드가 포함된 덱은 내보낼 수 없습니다.");
                    return new Printing(r.getString("key"),r.getString("section"),r.getInt("quantity"),
                            r.getObject("position",Integer.class),r.getObject("neuron_artwork",Integer.class));
                }).list();
        try {
            return new Code(PREFIX+Base64.getUrlEncoder().withoutPadding().encodeToString(
                    json.writeValueAsBytes(new Recipe(deck.gameCode(),deck.name(),rows,deck.nameJa(),deck.nameEn()))));
        } catch(JsonProcessingException e) {throw new IllegalStateException(e);}
    }

    DeckApi.Save decode(String code) {
        if(code==null||code.length()>180000||!code.startsWith(PREFIX)) throw invalid();
        Recipe recipe;
        try {recipe=json.readValue(Base64.getUrlDecoder().decode(code.substring(PREFIX.length())),Recipe.class);}
        catch(java.io.IOException|IllegalArgumentException e) {throw invalid();}
        if(recipe==null||recipe.name()==null||recipe.name().isBlank()||recipe.name().length()>100||
                (recipe.nameJa()!=null&&recipe.nameJa().length()>100)||(recipe.nameEn()!=null&&recipe.nameEn().length()>100)||
                recipe.game()==null||!recipe.game().matches("[A-Z]{1,32}")||recipe.entries()==null||recipe.entries().size()>300)
            throw invalid();
        Set<String> sources=new HashSet<>(), manual=new HashSet<>();
        for(var line:recipe.entries()){
            if(line==null||line.section()==null||!line.section().matches("[A-Z_]{1,64}")||line.quantity()<1||
                    line.quantity()>999||line.key()==null||line.key().length()>1024 ||
                    line.neuronArtwork()!=null && (line.neuronArtwork()<1 ||
                    line.neuronArtwork()>32767 || line.illustration()!=null)) throw invalid();
            if(line.key().startsWith("s:") && line.key().length()>2) sources.add(line.key().substring(2));
            else if(line.key().matches("m:[a-f0-9]{64}")) manual.add(line.key());
            else throw invalid();
        }
        var ids=new HashMap<String,Long>();
        if(!sources.isEmpty()){
            db.sql("select 's:'||legacy_key as key,id from card where game_code=:game and status='PUBLISHED' and legacy_key in (:keys)")
                    .param("game",recipe.game()).param("keys",sources).query((r,n)->ids.put(r.getString(1),r.getLong(2))).list();
        }
        if(!manual.isEmpty()){
            db.sql("select k,min(id) as id from (select c.id,"+PRINT_KEY+" as k from card c left join pack p on p.id=c.pack_id "+
                    "where c.game_code=:game and c.status='PUBLISHED' and c.legacy_key is null) matches where k in (:keys) group by k having count(*)=1")
                    .param("game",recipe.game()).param("keys",manual).query((r,n)->ids.put(r.getString(1),r.getLong(2))).list();
        }
        var lines=new ArrayList<DeckRules.Line>();
        for(var entry:recipe.entries()){
            Long id=ids.get(entry.key());
            if(id==null) throw new DeckRules.Invalid("이 도감에서 일치하는 공개 인쇄본을 하나로 확인할 수 없습니다.");
            Long variant=null;
            if(entry.illustration()!=null) variant=db.sql("select id from card_variant where card_id=? and position=?")
                    .param(id).param(entry.illustration()).query(Long.class).optional()
                    .orElseThrow(()->new DeckRules.Invalid("이 도감에서 선택한 일러스트를 찾을 수 없습니다."));
            lines.add(new DeckRules.Line(id,entry.section(),entry.quantity(),variant,entry.neuronArtwork()));
        }
        return new DeckApi.Save(recipe.name(),recipe.game(),"DRAFT",0,false,lines,recipe.nameJa(),recipe.nameEn());
    }
    private static ResponseStatusException invalid(){return new ResponseStatusException(HttpStatus.BAD_REQUEST);}
}
