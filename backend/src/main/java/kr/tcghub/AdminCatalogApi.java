package kr.tcghub;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.time.LocalDate;
import java.util.*;
import com.fasterxml.jackson.annotation.JsonRawValue;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/admin/catalog")
@Transactional(readOnly=true)
class AdminCatalogApi {
    static final String GAMES = "YUGIOH|POKEMON|WEISS|NIVEL|RIFTBOUND";
    record PackInput(@NotNull @Pattern(regexp=GAMES) String gameCode, @NotBlank @Size(max=320) String name,
                     @Size(max=96) String code, LocalDate releaseDate, @Size(max=200) String releaseLabel,
                     JsonNode metadata, @Positive Long version) {}
    record CardInput(@NotNull @Pattern(regexp=GAMES) String gameCode, @Positive Long packId,
                     @NotBlank @Size(max=320) String name, @Size(max=320) String originalName,
                     @Size(max=128) String number, @Size(max=128) String rarity, @Size(max=8000) String effect,
                     LocalDate releaseDate, JsonNode specs, @Pattern(regexp="PENDING|PUBLISHED") String status,
                     @Positive Long version) {}
    record Visibility(@NotNull @Pattern(regexp="PENDING|PUBLISHED") String status,@NotNull @Positive Long version) {}
    record PackView(long id,String gameCode,String name,String code,LocalDate releaseDate,String releaseLabel,
                    @JsonRawValue String metadata,long version,boolean editable) {}
    record CardView(long id,String gameCode,Long packId,String packName,String name,String originalName,
                    String number,String rarity,String effect,LocalDate releaseDate,@JsonRawValue String specs,
                    String status,long version,boolean editable,Long variantId) {}
    record Page<T>(List<T> items,long total,int page,int size) {}
    record EditState(String gameCode,long version,boolean editable) {}

    private static final String PACK_FIELDS = """
            select p.id,p.game_code,p.name,p.code,p.release_date,p.release_label,p.metadata::text as metadata,
                   p.edit_version as version,p.legacy_key is null as editable
            """;
    private static final String CARD_FIELDS = """
            select c.id,c.game_code,c.pack_id,p.name as pack_name,c.name,c.original_name,c.number,c.rarity,c.effect,
                   c.release_date,c.specs::text as specs,c.status,c.edit_version as version,
                   (c.legacy_key is null and c.source_id is null and c.status<>'REJECTED') as editable,v.id as variant_id
            """;
    private static final String CARD_FROM = """
             from card c left join pack p on p.id=c.pack_id
             left join card_variant v on v.card_id=c.id and v.position=0
            """;
    private final JdbcClient db;

    AdminCatalogApi(JdbcClient db) { this.db=db; }

    @GetMapping("/packs")
    Page<PackView> packs(Principal user,@RequestParam(defaultValue="") @Pattern(regexp="|"+GAMES) String game,
                         @RequestParam(defaultValue="") @Size(max=120) String q,
                         @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                         @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        operator(user);
        String filter = """
                 from pack p where (:game='' or p.game_code=:game)
                   and (:q='' or strpos(lower(concat_ws(' ',p.name,p.code)),lower(:q))>0)
                """;
        var params=Map.of("game",game,"q",search(q));
        var items=db.sql(PACK_FIELDS+filter+" order by p.id desc limit :size offset :offset").params(params)
                .param("size",size).param("offset",(long)page*size).query(PackView.class).list();
        long total=db.sql("select count(*)"+filter).params(params).query(Long.class).single();
        return new Page<>(items,total,page,size);
    }

    @GetMapping("/cards")
    Page<CardView> cards(Principal user,@RequestParam(defaultValue="") @Pattern(regexp="|"+GAMES) String game,
                         @RequestParam(defaultValue="") @Size(max=120) String q,
                         @RequestParam(defaultValue="") @Pattern(regexp="|PENDING|PUBLISHED|REJECTED") String status,
                         @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                         @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        operator(user);
        String filter = """
                 where (:game='' or c.game_code=:game) and (:status='' or c.status=:status)
                   and (:q='' or strpos(lower(concat_ws(' ',c.name,c.original_name,c.number)),lower(:q))>0)
                """;
        var params=Map.of("game",game,"status",status,"q",search(q));
        var items=db.sql(CARD_FIELDS+CARD_FROM+filter+" order by c.id desc limit :size offset :offset").params(params)
                .param("size",size).param("offset",(long)page*size).query(CardView.class).list();
        long total=db.sql("select count(*) from card c"+filter).params(params).query(Long.class).single();
        return new Page<>(items,total,page,size);
    }

    @GetMapping("/packs/{id}")
    PackView pack(Principal user,@PathVariable @Positive long id) { operator(user); return readPack(id); }

    @GetMapping("/cards/{id}")
    CardView card(Principal user,@PathVariable @Positive long id) { operator(user); return readCard(id); }

    private PackView readPack(long id) {
        return db.sql(PACK_FIELDS+" from pack p where p.id=?").param(id).query(PackView.class).optional().orElseThrow(AdminCatalogApi::missing);
    }

    private CardView readCard(long id) {
        return db.sql(CARD_FIELDS+CARD_FROM+" where c.id=?").param(id).query(CardView.class).optional().orElseThrow(AdminCatalogApi::missing);
    }

    @PostMapping("/packs")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    PackView createPack(Principal user,@Valid @RequestBody PackInput input) {
        long admin=operator(user);
        if (input.version()!=null) throw bad("새 팩에는 버전을 지정할 수 없습니다.");
        long id=packParams(db.sql("""
                insert into pack(game_code,name,code,release_date,release_label,metadata)
                values(:game,:name,:code,:day,:label,cast(:data as jsonb)) returning id
                """),input,false).query(Long.class).single();
        audit(admin,"CREATE_PACK",id);
        return readPack(id);
    }

    @PutMapping("/packs/{id}")
    @Transactional
    PackView updatePack(Principal user,@PathVariable @Positive long id,@Valid @RequestBody PackInput input) {
        long admin=operator(user);
        var state=db.sql("""
                select game_code,edit_version as version,legacy_key is null as editable from pack where id=? for update
                """).param(id).query(EditState.class).optional().orElseThrow(AdminCatalogApi::missing);
        requireEditable(state,input.gameCode(),input.version());
        packParams(db.sql("""
                update pack set name=:name,code=:code,release_date=:day,release_label=:label,
                       metadata=cast(:data as jsonb),edit_version=edit_version+1 where id=:id and game_code=:game
                """).param("id",id),input,true).update();
        audit(admin,"EDIT_PACK",id);
        return readPack(id);
    }

    private JdbcClient.StatementSpec packParams(JdbcClient.StatementSpec sql,PackInput input,boolean edit) {
        return sql.param("game",input.gameCode()).param("name",text(input.name())).param("code",text(input.code()))
                .param("day",input.releaseDate()).param("label",text(input.releaseLabel())).param("data",object(input.metadata(),edit));
    }

    @PostMapping("/cards")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    CardView createCard(Principal user,@Valid @RequestBody CardInput input) {
        long admin=operator(user);
        if (input.version()!=null) throw bad("새 카드에는 버전을 지정할 수 없습니다.");
        long id=cardParams(db.sql("""
                insert into card(game_code,pack_id,name,original_name,number,rarity,effect,release_date,specs,status)
                values(:game,:pack,:name,:original,:number,:rarity,:effect,:day,cast(:data as jsonb),:status) returning id
                """),input,false).query(Long.class).single();
        db.sql("insert into card_variant(card_id,position,rarity) values(?,0,?)").param(id).param(text(input.rarity())).update();
        audit(admin,"CREATE_CARD",id);
        return readCard(id);
    }

    @PutMapping("/cards/{id}")
    @Transactional
    CardView updateCard(Principal user,@PathVariable @Positive long id,@Valid @RequestBody CardInput input) {
        long admin=operator(user);
        var state=db.sql("""
                select game_code,edit_version as version,(legacy_key is null and source_id is null and status<>'REJECTED') as editable
                from card where id=? for update
                """).param(id).query(EditState.class).optional().orElseThrow(AdminCatalogApi::missing);
        requireEditable(state,input.gameCode(),input.version());
        cardParams(db.sql("""
                update card set pack_id=:pack,name=:name,original_name=:original,number=:number,rarity=:rarity,
                       effect=:effect,release_date=:day,specs=cast(:data as jsonb),status=:status,edit_version=edit_version+1
                 where id=:id and game_code=:game
                """).param("id",id),input,true).update();
        db.sql("""
                insert into card_variant(card_id,position,rarity) values(?,0,?) on conflict(card_id,position)
                do update set rarity=excluded.rarity where card_variant.rarity is distinct from excluded.rarity
                """).param(id).param(text(input.rarity())).update();
        audit(admin,"EDIT_CARD",id);
        return readCard(id);
    }

    @PutMapping("/cards/{id}/status")
    @Transactional
    CardView publication(Principal user,@PathVariable @Positive long id,@Valid @RequestBody Visibility input) {
        long admin=operator(user);
        record Current(String status,long version) {}
        var before=db.sql("select status,edit_version as version from card where id=? for update")
                .param(id).query(Current.class).optional().orElseThrow(AdminCatalogApi::missing);
        if (before.version()!=input.version() || before.status().equals("REJECTED"))
            throw new ResponseStatusException(HttpStatus.CONFLICT,"카드의 현재 상태와 버전을 확인해 주세요.");
        if (!before.status().equals(input.status())) {
            db.sql("update card set status=?,edit_version=edit_version+1 where id=?").param(input.status()).param(id).update();
            audit(admin,"CARD_"+input.status(),id);
        }
        return readCard(id);
    }

    private JdbcClient.StatementSpec cardParams(JdbcClient.StatementSpec sql,CardInput input,boolean edit) {
        String data=object(input.specs(),edit);
        validateSpecs(input.gameCode(),input.specs());
        if (input.packId()!=null && db.sql("select id from pack where id=? and game_code=? for key share")
                .param(input.packId()).param(input.gameCode()).query(Long.class).optional().isEmpty())
            throw bad("같은 게임의 팩을 선택해 주세요.");
        if (edit && input.status()==null) throw bad("카드의 게시 상태를 지정해 주세요.");
        return sql.param("game",input.gameCode()).param("pack",input.packId()).param("name",text(input.name()))
                .param("original",text(input.originalName())).param("number",text(input.number()))
                .param("rarity",text(input.rarity())).param("effect",text(input.effect())).param("day",input.releaseDate())
                .param("data",data).param("status",input.status()==null ? "PENDING" : input.status());
    }

    private static void requireEditable(EditState state,String game,Long version) {
        if (!state.editable()) throw new ResponseStatusException(HttpStatus.CONFLICT,"수집·이관한 메타데이터는 읽기 전용입니다.");
        if (!state.gameCode().equals(game)) throw bad("등록한 게임은 변경할 수 없습니다.");
        if (version==null) throw bad("편집을 시작할 때의 버전이 필요합니다.");
        if (state.version()!=version) throw new ResponseStatusException(HttpStatus.CONFLICT,"다른 편집 내용을 먼저 확인해 주세요.");
    }

    private static String object(JsonNode value,boolean required) {
        if (value==null && !required) return "{}";
        if (value==null || !value.isObject()) throw bad("상세 정보는 JSON 객체여야 합니다.");
        String json=value.toString();
        if (json.getBytes(StandardCharsets.UTF_8).length>16384) throw bad("상세 정보의 최대 크기는 16 KiB입니다.");
        validateJsonText(value);
        return json;
    }

    private static void validateJsonText(JsonNode value) {
        if (value.isTextual()) { text(value.textValue()); return; }
        value.fieldNames().forEachRemaining(AdminCatalogApi::text);
        value.forEach(AdminCatalogApi::validateJsonText);
    }

    private static void validateSpecs(String game,JsonNode specs) {
        if (specs==null) return;
        if (specs.hasNonNull("language") && !specs.get("language").isTextual()) throw bad("language에는 언어 코드를 입력해 주세요.");
        if (specs.hasNonNull("names")) {
            JsonNode names=specs.get("names");
            if (!names.isObject()) throw bad("names에는 언어별 카드명을 입력해 주세요.");
            names.forEach(name -> {
                if (!name.isTextual() || name.asText().isBlank() || name.asText().length()>320)
                    throw bad("언어별 카드명은 1~320자의 문자열이어야 합니다.");
            });
        }
        List<String> arrayFields=switch(game) {
            case "YUGIOH" -> List.of("linkmarkers","formats");
            case "POKEMON" -> List.of("types","attacks","abilities");
            case "WEISS" -> List.of("attributes");
            case "RIFTBOUND" -> List.of("domains","finishes");
            default -> List.of();
        };
        for (String key:arrayFields)
            if (specs.hasNonNull(key) && !specs.get(key).isArray()) throw bad(key+"에는 목록을 입력해 주세요.");
        if ("NIVEL".equals(game) && specs.hasNonNull("attribute") && !specs.get("attribute").isTextual())
            throw bad("attribute에는 속성 이름을 입력해 주세요.");
    }

    private static String text(String s) {
        if (s==null) return null;
        if (s.codePoints().anyMatch(c -> c==0 || (c>=0xD800 && c<=0xDFFF))) throw bad("저장할 수 없는 문자가 포함되어 있습니다.");
        String clean=s.strip();
        return clean.isEmpty() ? null : clean;
    }
    private static String search(String s) { return Objects.requireNonNullElse(text(s),""); }
    private long operator(Principal principal) {
        return db.sql("select id from app_user where email=? and enabled and role='ROLE_ADMIN'").param(principal.getName())
                .query(Long.class).optional().orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN));
    }
    private void audit(long admin,String action,long id) {
        db.sql("insert into operator_action(user_id,action,target_id) values(?,?,?)").param(admin).param(action).param(id).update();
    }
    private static ResponseStatusException missing() { return new ResponseStatusException(HttpStatus.NOT_FOUND); }
    private static ResponseStatusException bad(String detail) { return new ResponseStatusException(HttpStatus.BAD_REQUEST,detail); }
}
