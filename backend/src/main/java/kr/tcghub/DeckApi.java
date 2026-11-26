package kr.tcghub;

import java.security.Principal;
import java.time.OffsetDateTime;
import java.util.*;
import kr.tcghub.DeckRules.Line;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1")
@Transactional(readOnly = true, isolation=Isolation.REPEATABLE_READ)
class DeckApi {
    record Save(@NotBlank @Size(max=100) String name, @NotBlank @Size(max=32) String gameCode,
                @NotBlank @Pattern(regexp="DRAFT|COMPLETE") String state, @PositiveOrZero int revision,
                boolean shared, @NotNull @Size(max=300) List<@NotNull @Valid Line> entries) {}
    record Header(long id, String name, String gameCode, String format, int ruleVersion, String state,
                  int revision, OffsetDateTime updatedAt, UUID shareToken) {}
    record Summary(long id, String name, String gameCode, String format, int ruleVersion, String state,
                   int revision, OffsetDateTime updatedAt, UUID shareToken, long cards) {}
    record Page(List<Summary> items, long total) {}
    record Entry(long cardId, String section, int quantity, String name, String number, String packName,
                 Integer curveValue, CatalogApi.Image image) {}
    record Details(@com.fasterxml.jackson.annotation.JsonUnwrapped Header deck, DeckRules.Rule rule,List<Entry> entries) {}
    record History(int revision, OffsetDateTime savedAt, String name, String state, int cards) {}
    record HistoryPage(List<History> items,long total) {}
    private static final String FIELDS="d.id,d.name,d.game_code,d.format,d.rule_version,d.state,d.revision,d.updated_at,d.share_token";
    private final JdbcClient db;
    private final DeckRules rules;
    private final ObjectMapper json;
    private final DeckCodes codes;
    DeckApi(JdbcClient db, DeckRules rules, ObjectMapper json,DeckCodes codes) {this.db=db;this.rules=rules;this.json=json;this.codes=codes;}

    @GetMapping("/me/decks/{id}/code")
    DeckCodes.Code code(Principal user,@PathVariable @Positive long id) {return codes.encode(owned(user,id,false));}

    @PostMapping("/me/decks/import")
    @Transactional
    @ResponseStatus(HttpStatus.CREATED)
    Details importCode(Principal user,@RequestBody DeckCodes.Code input) {return create(user,codes.decode(input.code()));}

    @ExceptionHandler(DeckRules.Invalid.class)
    ResponseEntity<Map<String,String>> invalid(DeckRules.Invalid e) {
        return ResponseEntity.unprocessableEntity().body(Map.of("detail",e.getMessage()));
    }
    private static ResponseStatusException missing() { return new ResponseStatusException(HttpStatus.NOT_FOUND); }

    @GetMapping("/me/decks/rules/{game}")
    DeckRules.Rule rule(@PathVariable @Size(max=32) String game) { return rules.current(game); }

    @GetMapping("/me/decks")
    Page list(Principal user,@RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page) {
        String from=" from deck d join app_user u on u.id=d.owner_id where u.email=? and u.enabled";
        var items=db.sql("select "+FIELDS+",(select coalesce(sum(e.quantity),0) from deck_entry e where e.deck_id=d.id) as cards"+from+
                " order by d.updated_at desc,d.id desc limit 24 offset ?").param(user.getName()).param(page*24)
                .query(Summary.class).list();
        return new Page(items,db.sql("select count(*)"+from).param(user.getName()).query(Long.class).single());
    }

    private Header owned(Principal user,long id, boolean lock) {
        String sql="select "+FIELDS+" from deck d join app_user u on u.id=d.owner_id where d.id=? and u.email=? and u.enabled";
        return db.sql(sql+(lock?" for update of d":"")).param(id).param(user.getName()).query(Header.class).optional().orElseThrow(DeckApi::missing);
    }
    private Details details(Header header) {
        var entries=db.sql("select e.card_id,e.section,e.quantity,c.name,c.number,p.name as pack_name,"+
                "card_curve_value(c.game_code,c.specs) as curve_value"+LibraryImage.COLUMNS+
                "from deck_entry e join card c on c.id=e.card_id left join pack p on p.id=c.pack_id "+LibraryImage.JOIN+
                "where e.deck_id=? order by e.section,c.name,e.card_id").param(header.id()).query((r,n)->new Entry(
                        r.getLong("card_id"),r.getString("section"),r.getInt("quantity"),r.getString("name"),
                        r.getString("number"),r.getString("pack_name"),r.getObject("curve_value",Integer.class),LibraryImage.read(r))).list();
        return new Details(header,rules.rule(header.gameCode(),header.format(),header.ruleVersion()),entries);
    }
    @GetMapping("/me/decks/{id}")
    Details get(Principal user,@PathVariable @Positive long id) { return details(owned(user,id,false)); }

    @GetMapping("/shared/decks/{token}")
    Details shared(@PathVariable UUID token) {
        var header=db.sql("select "+FIELDS+"""
             from deck d join app_user u on u.id=d.owner_id where d.share_token=? and u.enabled
               and not exists(select 1 from deck_entry e join card c on c.id=e.card_id
                              where e.deck_id=d.id and c.status<>'PUBLISHED')
            """).param(token).query(Header.class).optional().orElseThrow(DeckApi::missing);
        return details(header);
    }

    @PostMapping("/me/decks")
    @Transactional
    @ResponseStatus(HttpStatus.CREATED)
    Details create(Principal user,@RequestBody @Valid Save data) {
        if(data.revision()!=0) throw new ResponseStatusException(HttpStatus.CONFLICT);
        var rule=rules.current(data.gameCode());
        rules.validate(rule,data.entries(),data.state().equals("COMPLETE"));
        long id=db.sql("""
            insert into deck(owner_id,game_code,name,format,rule_version,state,share_token)
            select id,?,?,'CONSTRUCTED',?,?,? from app_user where email=? and enabled returning id
            """).param(data.gameCode()).param(data.name().strip()).param(rule.version()).param(data.state())
                .param(data.shared()?UUID.randomUUID():null).param(user.getName()).query(Long.class).optional().orElseThrow(DeckApi::missing);
        return writeEntries(user,id,rule,data.entries());
    }

    @PutMapping("/me/decks/{id}")
    @Transactional
    Details update(Principal user,@PathVariable @Positive long id,@RequestBody @Valid Save data) {
        var before=owned(user,id,true);
        if(before.revision()!=data.revision()) throw new ResponseStatusException(HttpStatus.CONFLICT);
        if(!before.gameCode().equals(data.gameCode())) throw new DeckRules.Invalid("저장한 덱은 게임을 변경할 수 없습니다.");
        var rule=rules.rule(before.gameCode(),before.format(),before.ruleVersion());
        rules.validate(rule,data.entries(),data.state().equals("COMPLETE"));
        // A deck created before V10 gets its initial snapshot on its first write.
        if(!db.sql("select exists(select 1 from deck_revision where deck_id=? and revision=?)")
                .param(id).param(before.revision()).query(Boolean.class).single()) snapshot(details(before));
        UUID token=data.shared()?(before.shareToken()!=null?before.shareToken():UUID.randomUUID()):null;
        db.sql("update deck set name=?,state=?,share_token=?,revision=revision+1,updated_at=clock_timestamp() where id=?")
                .param(data.name().strip()).param(data.state()).param(token).param(id).update();
        db.sql("delete from deck_entry where deck_id=?").param(id).update();
        return writeEntries(user,id,rule,data.entries());
    }
    private Details writeEntries(Principal user,long id,DeckRules.Rule rule,List<DeckRules.Line> entries) {
        for(var line:entries) db.sql("""
            insert into deck_entry(deck_id,game_code,format,rule_version,section,card_id,quantity) values(?,?,?,?,?,?,?)
            """).param(id).param(rule.gameCode()).param(rule.format()).param(rule.version())
                .param(line.section()).param(line.cardId()).param(line.quantity()).update();
        var result=details(owned(user,id,false));
        snapshot(result);
        return result;
    }
    private void snapshot(Details details) {
        try {
            var saved=json.createObjectNode();
            saved.put("name",details.deck().name()).put("state",details.deck().state()).put("gameCode",details.deck().gameCode())
                    .put("revision",details.deck().revision()).put("cards",details.entries().stream().mapToInt(Entry::quantity).sum());
            saved.set("entries",json.valueToTree(details.entries()));
            db.sql("insert into deck_revision(deck_id,revision,saved_at,snapshot) values(?,?,?,cast(? as jsonb))")
                    .param(details.deck().id()).param(details.deck().revision()).param(details.deck().updatedAt())
                    .param(json.writeValueAsString(saved)).update();
        } catch(JsonProcessingException e) { throw new IllegalStateException(e); }
    }
    @GetMapping("/me/decks/{id}/history")
    HistoryPage history(Principal user,@PathVariable @Positive long id,@RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page) {
        owned(user,id,false);
        var items=db.sql("""
            select revision,saved_at,snapshot->>'name' as name,snapshot->>'state' as state,
                   (snapshot->>'cards')::integer as cards from deck_revision where deck_id=?
            order by revision desc limit 24 offset ?
            """).param(id).param(page*24).query(History.class).list();
        return new HistoryPage(items,db.sql("select count(*) from deck_revision where deck_id=?").param(id).query(Long.class).single());
    }
    @GetMapping("/me/decks/{id}/history/{revision}")
    JsonNode saved(Principal user,@PathVariable @Positive long id,@PathVariable @Positive int revision) throws JsonProcessingException {
        owned(user,id,false);
        return json.readTree(db.sql("select snapshot::text from deck_revision where deck_id=? and revision=?")
                .param(id).param(revision).query(String.class).optional().orElseThrow(DeckApi::missing));
    }
}
