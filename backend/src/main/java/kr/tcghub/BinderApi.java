package kr.tcghub;

import java.security.Principal;
import java.util.List;
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
    record OwnedCard(long cardId, String name, String gameCode, String number, String packName, int quantity, CatalogApi.Image image) {}
    record Page(List<OwnedCard> items, long total, long copies) {}
    record Count(int quantity) {}
    private final JdbcClient db;
    BinderApi(JdbcClient db) { this.db = db; }

    @GetMapping
    Page page(Principal user, @RequestParam(defaultValue="") @Size(max=32) String game,
              @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page) {
        String from = """
            from binder_card b join app_user u on u.id=b.owner_id join card c on c.id=b.card_id
            left join pack p on p.id=c.pack_id
            """;
        String filter=" where u.email=:email and u.enabled and (:game='' or c.game_code=:game) ";
        var totals = db.sql("select count(*),coalesce(sum(b.quantity),0) "+from+filter)
                .param("email",user.getName()).param("game",game).query((r,n)->new long[]{r.getLong(1),r.getLong(2)}).single();
        var items = db.sql("select c.id,c.name,c.game_code,c.number,p.name as pack_name,b.quantity"+LibraryImage.COLUMNS+from+LibraryImage.JOIN+filter+
                "order by b.updated_at desc,b.card_id limit 24 offset :offset").param("email",user.getName())
                .param("game",game).param("offset",page*24).query((r,n)->new OwnedCard(r.getLong("id"),r.getString("name"),
                        r.getString("game_code"),r.getString("number"),r.getString("pack_name"),r.getInt("quantity"),LibraryImage.read(r))).list();
        return new Page(items,totals[0],totals[1]);
    }

    @GetMapping("/{cardId}")
    Count quantity(Principal user, @PathVariable @Positive long cardId) {
        return new Count(db.sql("""
            select b.quantity from binder_card b join app_user u on u.id=b.owner_id
            where u.email=? and u.enabled and b.card_id=?
            """).param(user.getName()).param(cardId).query(Integer.class).optional().orElse(0));
    }

    @PutMapping("/{cardId}")
    @Transactional
    Count change(Principal user, @PathVariable @Positive long cardId, @RequestBody @Valid Quantity change) {
        // This row also serializes two simultaneous first inserts for the same owner's card.
        long owner = db.sql("select id from app_user where email=? and enabled for update").param(user.getName())
                .query(Long.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        int current = db.sql("select quantity from binder_card where owner_id=? and card_id=?")
                .param(owner).param(cardId).query(Integer.class).optional().orElse(0);
        if (current != change.expectedQuantity()) throw new ResponseStatusException(HttpStatus.CONFLICT);
        if (change.quantity() == 0) {
            db.sql("delete from binder_card where owner_id=? and card_id=?").param(owner).param(cardId).update();
        } else {
            int changed = db.sql("""
                insert into binder_card(owner_id,card_id,quantity)
                select ?,id,? from card where id=? and status='PUBLISHED'
                on conflict(owner_id,card_id) do update set quantity=excluded.quantity,updated_at=now()
                """).param(owner).param(change.quantity()).param(cardId).update();
            if (changed==0) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return new Count(change.quantity());
    }
}
