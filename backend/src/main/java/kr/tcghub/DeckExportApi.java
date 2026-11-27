package kr.tcghub;

import java.security.Principal;
import java.util.List;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Pattern;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;

@RestController
class DeckExportApi {
    record Item(String section,long cardId,String name,String number,int quantity,Integer illustration,Integer neuronArtwork,
                String language,String nameBasis,String nameReferenceUrl) {}
    record Deck(long id,String gameCode,String name,String nameJa,String nameEn,String state,List<Item> entries) {}
    record Batch(List<Deck> items,Long next) {}
    private final JdbcClient db;
    DeckExportApi(JdbcClient db){this.db=db;}
    @GetMapping("/api/v1/me/decks/export")
    Batch page(Principal user,@RequestParam(defaultValue="0") @PositiveOrZero long after,
               @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang){
        var decks=new LinkedHashMap<Long,Deck>();
        db.sql("""
            with page as (select d.* from deck d join app_user u on u.id=d.owner_id
                where u.email=:email and u.enabled and d.id>:after order by d.id limit 24)
            select d.id,d.game_code,d.name as deck_name,d.name_ja,d.name_en,d.state,e.section,e.card_id,
            """ + CardEdition.NAME_FIELDS + """
                   ,
                   c.number,e.quantity,v.position,e.neuron_artwork
              from page d left join deck_entry e on e.deck_id=d.id left join card c on c.id=e.card_id
              left join card_variant v on v.id=e.variant_id
            """+CardEdition.JOIN+" order by d.id,e.section,e.display_order,e.card_id,e.variant_id")
                .param("email",user.getName()).param("after",after).param("lang",lang).query(rows->{
                while(rows.next()){
                    long id=rows.getLong("id");
                    var deck=decks.get(id);
                    if(deck==null){
                        deck=new Deck(id,rows.getString("game_code"),rows.getString("deck_name"),rows.getString("name_ja"),
                                rows.getString("name_en"),rows.getString("state"),new ArrayList<>());
                        decks.put(id,deck);
                    }
                    Long card=rows.getObject("card_id",Long.class);
                    if(card!=null) deck.entries().add(new Item(rows.getString("section"),card,rows.getString("name"),
                            rows.getString("number"),rows.getInt("quantity"),rows.getObject("position",Integer.class),
                            rows.getObject("neuron_artwork",Integer.class),rows.getString("language"),
                            rows.getString("nameBasis"),rows.getString("nameReferenceUrl")));
                }
                return decks.size();
            });
        var items=List.copyOf(decks.values());
        return new Batch(items,items.size()==24?items.get(items.size()-1).id():null);
    }
}
