package kr.tcghub;

import java.security.Principal;
import java.util.List;
import java.util.HashMap;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/me/binder")
@Transactional(readOnly = true)
class BinderApi {
    record Quantity(@NotNull @Min(0) @Max(9999) Integer quantity,
                    @NotNull @Min(0) @Max(9999) Integer expectedQuantity) {}
    static final String EDITION="und|ko|en|ja", CONDITION="UNSPECIFIED|NM|LP|MP|HP|DMG";
    record OwnedCard(long cardId,String name,String gameCode,String number,String packName,int quantity,
                     CatalogApi.Image image,String rarity,String edition,String condition,boolean tradable) {}
    record Stats(String gameCode,long uniqueCards,long copies) {}
    record Page(List<OwnedCard> items, long total, long copies) {}
    record Count(int quantity) {}
    private final JdbcClient db;
    BinderApi(JdbcClient db) { this.db = db; }

    @GetMapping
    Page page(Principal user, @RequestParam(defaultValue="") @Size(max=32) String game,
              @RequestParam(defaultValue="") @Size(max=120) String q,@RequestParam(defaultValue="") @Size(max=64) String rarity,
              @RequestParam(defaultValue="1") @Min(1) @Max(9999) int minQuantity,
              @RequestParam(defaultValue="9999") @Min(1) @Max(9999) int maxQuantity,
              @RequestParam(defaultValue="") @Pattern(regexp="|"+EDITION) String edition,
              @RequestParam(defaultValue="") @Pattern(regexp="|"+CONDITION) String condition,
              @RequestParam(required=false) Boolean tradable,
              @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
              @RequestParam(defaultValue="24") @Min(1) @Max(100) int size) {
        if (minQuantity>maxQuantity) throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        String from = """
            from binder_card b join app_user u on u.id=b.owner_id join card c on c.id=b.card_id
            left join pack p on p.id=c.pack_id
            """;
        String filter="""
                where u.email=:email and u.enabled and (:game='' or c.game_code=:game)
                and (:rarity='' or c.rarity=:rarity) and (:edition='' or b.edition=:edition)
                and (:condition='' or b.condition=:condition) and b.quantity between :min and :max
                and (:q='' or strpos(lower(c.name || ' ' || coalesce(c.number,'')),lower(:q))>0
                    or exists(select from jsonb_each_text(case when jsonb_typeof(c.specs->'names')='object'
                        then c.specs->'names' else '{}'::jsonb end) n where strpos(lower(n.value),lower(:q))>0))
                """;
        var args=new HashMap<String,Object>();
        args.put("email",user.getName()); args.put("game",game); args.put("rarity",rarity); args.put("q",q.strip());
        args.put("edition",edition); args.put("condition",condition); args.put("min",minQuantity); args.put("max",maxQuantity);
        if (tradable!=null) { args.put("tradable",tradable); filter+=" and b.tradable=:tradable "; }
        var totals = db.sql("select count(*),coalesce(sum(b.quantity),0) "+from+filter)
                .params(args).query((r,n)->new long[]{r.getLong(1),r.getLong(2)}).single();
        var items = db.sql("select c.id,c.name,c.game_code,c.number,c.rarity,p.name as pack_name,b.quantity,b.edition,b.condition,b.tradable"+
                LibraryImage.COLUMNS+from+LibraryImage.JOIN+filter+
                " order by b.updated_at desc,b.card_id,b.edition,b.condition,b.tradable limit :size offset :offset")
                .params(args).param("size",size).param("offset",(long)page*size).query((r,n)->new OwnedCard(r.getLong("id"),r.getString("name"),
                        r.getString("game_code"),r.getString("number"),r.getString("pack_name"),r.getInt("quantity"),LibraryImage.read(r),
                        r.getString("rarity"),r.getString("edition"),r.getString("condition"),r.getBoolean("tradable"))).list();
        return new Page(items,totals[0],totals[1]);
    }

    @GetMapping("/{cardId}")
    Count quantity(Principal user, @PathVariable @Positive long cardId,
                   @RequestParam(defaultValue="und") @Pattern(regexp=EDITION) String edition,
                   @RequestParam(defaultValue="UNSPECIFIED") @Pattern(regexp=CONDITION) String condition,
                   @RequestParam(defaultValue="false") boolean tradable) {
        return new Count(db.sql("""
            select b.quantity from binder_card b join app_user u on u.id=b.owner_id
            where u.email=? and u.enabled and b.card_id=? and b.edition=? and b.condition=? and b.tradable=?
            """).param(user.getName()).param(cardId).param(edition).param(condition).param(tradable).query(Integer.class).optional().orElse(0));
    }

    @PutMapping("/{cardId}")
    @Transactional
    Count change(Principal user, @PathVariable @Positive long cardId, @RequestBody @Valid Quantity change,
                 @RequestParam(defaultValue="und") @Pattern(regexp=EDITION) String edition,
                 @RequestParam(defaultValue="UNSPECIFIED") @Pattern(regexp=CONDITION) String condition,
                 @RequestParam(defaultValue="false") boolean tradable) {
        // This row also serializes two simultaneous first inserts for the same owner's card.
        long owner = db.sql("select id from app_user where email=? and enabled for update").param(user.getName())
                .query(Long.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        String lot=" where owner_id=? and card_id=? and edition=? and condition=? and tradable=?";
        int current = db.sql("select quantity from binder_card"+lot).params(owner,cardId,edition,condition,tradable)
                .query(Integer.class).optional().orElse(0);
        if (current != change.expectedQuantity()) throw new ResponseStatusException(HttpStatus.CONFLICT);
        if (change.quantity() == 0) {
            db.sql("delete from binder_card"+lot).params(owner,cardId,edition,condition,tradable).update();
        } else {
            int changed = db.sql("""
                insert into binder_card(owner_id,card_id,quantity,edition,condition,tradable)
                select ?,id,?,?,?,? from card where id=? and status='PUBLISHED'
                on conflict(owner_id,card_id,edition,condition,tradable) do update set quantity=excluded.quantity,updated_at=now()
                """).params(owner,change.quantity(),edition,condition,tradable,cardId).update();
            if (changed==0) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new Count(change.quantity());
    }

    @GetMapping("/stats")
    List<Stats> stats(Principal user) {
        return db.sql("""
            select g.code game_code,coalesce(t.unique_cards,0) unique_cards,coalesce(t.copies,0) copies
            from game g left join (select c.game_code,count(distinct c.id) unique_cards,sum(b.quantity) copies
                from binder_card b join app_user u on u.id=b.owner_id join card c on c.id=b.card_id
                where u.email=? and u.enabled group by c.game_code) t on g.code=t.game_code order by g.code
            """).param(user.getName()).query(Stats.class).list();
    }
}
