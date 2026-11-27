package kr.tcghub;

import java.security.Principal;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/community")
@Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
class CommunityApi {
    static final String BOARDS = "FREE|SUGGESTION|TRADE";
    static final String TYPES = "SELL|BUY|EXCHANGE";
    static final String STATES = "OPEN|RESERVED|CLOSED";
    record Id(long id) {}
    record Page<T>(List<T> items, int page, int size, long total) {}
    record Summary(long id, String board, String title, String tradeType, String tradeStatus,
                   OffsetDateTime createdAt, long commentCount, boolean mine) {}
    record Tag(long id, String gameCode, String name, String number) {}
    record Detail(long id, String board, String title, String tradeType, String tradeStatus,
                  OffsetDateTime createdAt, long commentCount, boolean mine, String body, List<Tag> cards) {}
    record Comment(long id, Long parentId, String body, OffsetDateTime createdAt, boolean mine) {}
    record NewPost(@NotNull @Pattern(regexp=BOARDS) String board, @NotBlank @Size(max=120) String title,
                   @NotBlank @Size(max=5000) String body, @Pattern(regexp=TYPES) String tradeType,
                   @Size(max=12) List<@NotNull @Positive Long> cardIds) {}
    record NewComment(@NotBlank @Size(max=1200) String body, @Positive Long parentId) {}
    record Trade(@NotNull @Pattern(regexp=STATES) String tradeStatus,
                 @Pattern(regexp=STATES) String expectedTradeStatus) {}
    record Report(@Positive Long postId, @Positive Long commentId, @NotBlank @Size(max=500) String reason) {}

    private static final String POST_FIELDS = """
            p.id, p.board, p.title, p.trade_type, p.trade_status, p.created_at,
            (select count(*) from post_comment c where c.post_id=p.id and not c.hidden) as comment_count,
            p.author_id=coalesce((select id from app_user where email=:viewer and enabled),0) as mine
            """;
    private static final String LIST = """
             from board_post p where not p.hidden and (:board='' or p.board=:board)
               and (:type='' or p.trade_type=:type) and (:state='' or p.trade_status=:state)
               and (:q='' or strpos(lower(p.title),lower(:q))>0)
            """;
    private final JdbcClient db;
    CommunityApi(JdbcClient db) { this.db = db; }

    @GetMapping("/posts")
    Page<Summary> posts(Principal user, @RequestParam(defaultValue="") @Pattern(regexp="|"+BOARDS) String board,
                        @RequestParam(defaultValue="") @Pattern(regexp="|"+TYPES) String tradeType,
                        @RequestParam(defaultValue="") @Pattern(regexp="|"+STATES) String tradeStatus,
                        @RequestParam(defaultValue="") @Size(max=120) String q,
                        @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                        @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        var filter = Map.of("board",board,"type",tradeType,"state",tradeStatus,"q",q.strip());
        var items = db.sql("select "+POST_FIELDS+LIST+" order by p.id desc limit :size offset :offset")
                .params(filter).param("viewer",viewer(user)).param("size",size).param("offset",(long)page*size)
                .query(Summary.class).list();
        long total = db.sql("select count(*)"+LIST).params(filter).query(Long.class).single();
        return new Page<>(items,page,size,total);
    }

    @GetMapping("/posts/{id}")
    Detail post(Principal user, @PathVariable @Positive long id) {
        record PostBody(long id, String board, String title, String tradeType, String tradeStatus,
                        OffsetDateTime createdAt, long commentCount, boolean mine, String body) {}
        var p = db.sql("select "+POST_FIELDS+",p.body from board_post p where p.id=:id and not p.hidden")
                .param("id",id).param("viewer",viewer(user)).query(PostBody.class).optional().orElseThrow(CommunityApi::missing);
        var cards = db.sql("""
                select c.id,c.game_code,coalesce(nullif(c.specs->'names'->>'ko',''),c.name) as name,c.number
                from post_card pc join card c on c.id=pc.card_id and c.status='PUBLISHED'
                where pc.post_id=? order by c.id
                """).param(id).query(Tag.class).list();
        return new Detail(p.id(),p.board(),p.title(),p.tradeType(),p.tradeStatus(),p.createdAt(),
                p.commentCount(),p.mine(),p.body(),cards);
    }

    @GetMapping("/posts/{id}/comments")
    Page<Comment> comments(Principal user, @PathVariable @Positive long id,
                           @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                           @RequestParam(defaultValue="50") @Min(1) @Max(100) int size) {
        visiblePost(id,false);
        var items = db.sql("""
                select c.id,c.parent_id,c.body,c.created_at,
                       c.author_id=coalesce((select id from app_user where email=:viewer and enabled),0) as mine
                from post_comment c where c.post_id=:post and not c.hidden order by c.id limit :size offset :offset
                """).param("viewer",viewer(user)).param("post",id).param("size",size).param("offset",(long)page*size)
                .query(Comment.class).list();
        long total = db.sql("select count(*) from post_comment where post_id=? and not hidden")
                .param(id).query(Long.class).single();
        return new Page<>(items,page,size,total);
    }

    @PostMapping("/posts")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    Id create(Principal user, @RequestBody @Valid NewPost input) {
        long author = account(user);
        boolean trade = "TRADE".equals(input.board());
        if (trade != (input.tradeType()!=null)) throw invalid();
        var tags = input.cardIds()==null ? List.<Long>of() : input.cardIds();
        if (!tags.isEmpty()) {
            if (new HashSet<>(tags).size()!=tags.size()) throw invalid();
            int found = db.sql("select id from card where id in (:ids) and status='PUBLISHED' order by id for share")
                    .param("ids",tags).query(Long.class).list().size();
            if (found!=tags.size()) throw invalid();
        }
        long id = db.sql("""
                insert into board_post(author_id,board,title,body,trade_type,trade_status)
                values(?,?,?,?,?,?) returning id
                """).param(author).param(input.board()).param(plain(input.title())).param(plain(input.body()))
                .param(input.tradeType()).param(trade ? "OPEN" : null).query(Long.class).single();
        if (!tags.isEmpty()) {
            db.sql("insert into post_card(post_id,card_id) select :post,id from card where id in (:ids)")
                    .param("post",id).param("ids",tags).update();
        }
        return new Id(id);
    }

    @PostMapping("/posts/{id}/comments")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    Id comment(Principal user, @PathVariable @Positive long id, @Valid @RequestBody NewComment input) {
        long author = account(user);
        visiblePost(id,true);
        if (input.parentId()!=null) {
            boolean top = db.sql("select parent_id is null from post_comment where post_id=? and id=? and not hidden for share")
                    .param(id).param(input.parentId()).query(Boolean.class).optional().orElseThrow(CommunityApi::missing);
            if (!top) throw invalid();
        }
        long created = db.sql("insert into post_comment(post_id,author_id,body,parent_id) values(?,?,?,?) returning id")
                .param(id).param(author).param(plain(input.body())).param(input.parentId()).query(Long.class).single();
        return new Id(created);
    }

    @PatchMapping("/posts/{id}/trade-status")
    @Transactional
    Id status(Principal user, @PathVariable @Positive long id, @Valid @RequestBody Trade input) {
        long author = account(user);
        record State(long authorId, String board, String tradeStatus) {}
        var current = db.sql("select author_id,board,trade_status from board_post where id=? and not hidden for update")
                .param(id).query(State.class).optional().orElseThrow(CommunityApi::missing);
        if (current.authorId()!=author) throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        if (!"TRADE".equals(current.board())) throw invalid();
        if (input.expectedTradeStatus()!=null && !input.expectedTradeStatus().equals(current.tradeStatus())
                && !input.tradeStatus().equals(current.tradeStatus())) throw new ResponseStatusException(HttpStatus.CONFLICT);
        db.sql("update board_post set trade_status=? where id=?").param(input.tradeStatus()).param(id).update();
        return new Id(id);
    }

    @PostMapping("/reports")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    Id report(Principal user, @Valid @RequestBody Report input) {
        long author = account(user);
        if ((input.postId()==null)==(input.commentId()==null)) throw invalid();
        if (input.postId()!=null) {
            visiblePost(input.postId(),true);
        } else {
            db.sql("""
                    select c.id from post_comment c join board_post p on p.id=c.post_id
                    where c.id=? and not c.hidden and not p.hidden for share of p,c
                    """).param(input.commentId()).query(Long.class).optional().orElseThrow(CommunityApi::missing);
        }
        long id = db.sql("""
                insert into abuse_report(reporter_id,post_id,comment_id,reason) values(?,?,?,?)
                on conflict do nothing returning id
                """).param(author).param(input.postId()).param(input.commentId()).param(plain(input.reason()))
                .query(Long.class).optional().orElseThrow(() -> new ResponseStatusException(HttpStatus.CONFLICT));
        return new Id(id);
    }

    private static String viewer(Principal user) { return user==null ? "" : user.getName(); }
    private long account(Principal user) {
        return db.sql("select id from app_user where email=? and enabled for share").param(viewer(user))
                .query(Long.class).optional().orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN));
    }
    private void visiblePost(long id, boolean lock) {
        db.sql("select id from board_post where id=? and not hidden"+(lock ? " for share" : ""))
                .param(id).query(Long.class).optional().orElseThrow(CommunityApi::missing);
    }
    // The API supplies plain text. All public renderers use escaped text nodes.
    private static String plain(String value) {
        String stripped = value.strip().replace("\r\n","\n").replace('\r','\n');
        if (stripped.isBlank() || stripped.chars().anyMatch(c -> Character.isISOControl(c) && c!='\n' && c!='\t')) {
            throw invalid();
        }
        return stripped;
    }
    private static ResponseStatusException missing() { return new ResponseStatusException(HttpStatus.NOT_FOUND); }
    private static ResponseStatusException invalid() { return new ResponseStatusException(HttpStatus.BAD_REQUEST); }
}
