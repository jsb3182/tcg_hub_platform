package kr.tcghub;

import java.security.Principal;
import java.util.List;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;

@RestController
class DeckNeedsApi {
    record Item(long cardId,String name,String number,long required,long owned,String language,String nameBasis,String nameReferenceUrl) {}
    record Page(List<Item> items,Long next) {}
    private final JdbcClient db;
    DeckNeedsApi(JdbcClient db){this.db=db;}

    @GetMapping("/api/v1/me/decks/needed")
    Page needed(Principal user,@RequestParam(defaultValue="0") @PositiveOrZero long after,
                @RequestParam(defaultValue="0") @PositiveOrZero long deckId,
                @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang){
        var items=db.sql("""
                with owner as (select id from app_user where email=:email and enabled),
                wanted as (select e.card_id,sum(e.quantity) as required from owner join deck d on d.owner_id=owner.id
                    join deck_entry e on e.deck_id=d.id where (:deck=0 or d.id=:deck) and e.card_id>:after group by e.card_id),
                stock as (select b.card_id,sum(b.quantity) as owned from owner join binder_card b on b.owner_id=owner.id
                    join wanted w on w.card_id=b.card_id group by b.card_id)
                select c.id as card_id,
                """+CardEdition.NAME_FIELDS+"""
                 ,c.number,w.required,coalesce(s.owned,0) as owned
                from wanted w join card c on c.id=w.card_id and c.status='PUBLISHED' left join stock s on s.card_id=c.id
                """+CardEdition.JOIN+"""
                where w.required>coalesce(s.owned,0) order by c.id limit 41
                """).param("deck",deckId).param("after",after).param("email",user.getName()).param("lang",lang)
                .query(Item.class).list();
        return items.size()<=40?new Page(items,null):new Page(items.subList(0,40),items.get(39).cardId());
    }
}
