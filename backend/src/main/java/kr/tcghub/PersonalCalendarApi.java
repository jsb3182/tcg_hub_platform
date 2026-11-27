package kr.tcghub;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.springframework.http.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/me/calendar")
@Transactional(readOnly=true)
class PersonalCalendarApi {
    record Draft(@NotBlank @Size(max=160) @Pattern(regexp="[^\\p{Cntrl}]+") String title,
                 @NotNull OffsetDateTime startsAt, OffsetDateTime endsAt,
                 @Min(0) @Max(10080) Integer reminderMinutes) {}
    record Event(long id,String title,Instant startsAt,Instant endsAt,List<Instant> reminders) {}
    record Page(List<Event> items,boolean hasMore) {}
    private static final String OWNED="""
        from calendar_event e join app_user u on u.id=e.owner_id
        where u.email=:email and u.enabled and e.category='PERSONAL'
        """;
    private static final String SELECT="""
        select e.id,e.title,e.starts_at,e.ends_at,array(select to_char(r.remind_at at time zone 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') from event_reminder r
          where r.event_id=e.id and r.user_id=e.owner_id order by r.remind_at) as reminders
        """+OWNED;
    private final JdbcClient db;
    PersonalCalendarApi(JdbcClient db) { this.db=db; }

    private static Event event(ResultSet rs,int row) throws SQLException {
        Timestamp end=rs.getTimestamp("ends_at");
        String[] reminders=(String[])rs.getArray("reminders").getArray();
        return new Event(rs.getLong("id"),rs.getString("title"),rs.getTimestamp("starts_at").toInstant(),
                end==null?null:end.toInstant(),Arrays.stream(reminders).map(Instant::parse).toList());
    }

    @GetMapping
    Page list(Principal account,@RequestParam(defaultValue="0") @Min(0) @Max(100000) int page,
              @RequestParam(defaultValue="30") @Min(1) @Max(100) int size) {
        var rows=db.sql(SELECT+" order by e.starts_at,e.id limit :limit offset :offset")
                .param("email",account.getName()).param("limit",size+1).param("offset",(long)page*size)
                .query(PersonalCalendarApi::event).list();
        return new Page(rows.subList(0,Math.min(size,rows.size())),rows.size()>size);
    }

    @PostMapping @Transactional @ResponseStatus(HttpStatus.CREATED)
    Event create(Principal account,@RequestBody @Valid Draft draft) {
        var start=draft.startsAt().toInstant();
        var end=draft.endsAt()==null?null:draft.endsAt().toInstant();
        if (!icalDate(start) || end!=null && (!icalDate(end) || !end.isAfter(start)))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        var owner=db.sql("select id from app_user where email=? and enabled").param(account.getName())
                .query(Long.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        var id=db.sql("""
            insert into calendar_event(owner_id,category,title,starts_at,ends_at)
            values(?,'PERSONAL',?,?,?) returning id
            """).param(owner).param(draft.title().strip()).param(Timestamp.from(start))
                .param(4,draft.endsAt(),java.sql.Types.TIMESTAMP_WITH_TIMEZONE)
                .query(Long.class).single();
        if (draft.reminderMinutes()!=null) {
            var when=start.minus(Duration.ofMinutes(draft.reminderMinutes()));
            if (!icalDate(when)) throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
            db.sql("insert into event_reminder(user_id,event_id,remind_at) values(?,?,?)")
                    .param(owner).param(id).param(Timestamp.from(when)).update();
        }
        return find(account,id);
    }

    private Event find(Principal account,long id) {
        return db.sql(SELECT+" and e.id=:id").param("email",account.getName()).param("id",id)
                .query(PersonalCalendarApi::event).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @DeleteMapping("/{id}") @Transactional @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(Principal account,@PathVariable @Positive long id) {
        int changed=db.sql("""
            delete from calendar_event e using app_user u
            where e.id=? and e.owner_id=u.id and e.category='PERSONAL' and u.email=? and u.enabled
            """).param(id).param(account.getName()).update();
        if (changed==0) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    private static final DateTimeFormatter ICS_TIME=DateTimeFormatter.ofPattern("uuuuMMdd'T'HHmmss'Z'",Locale.ROOT).withZone(ZoneOffset.UTC);
    private static boolean icalDate(Instant t) {
        int year=t.atZone(ZoneOffset.UTC).getYear();
        return year>=1 && year<=9999;
    }
    private static String escaped(String value) {
        return value.replace("\\","\\\\").replace("\r\n","\n").replace('\r','\n')
                .replace("\n","\\n").replace(";","\\;").replace(",","\\,");
    }
    private static void line(StringBuilder out,String content) {
        int width=0;
        for (int i=0;i<content.length();) {
            int cp=content.codePointAt(i);
            int bytes=cp<128?1:cp<2048?2:cp<65536?3:4;
            if (width+bytes>75) { out.append("\r\n "); width=1; }
            out.appendCodePoint(cp); width+=bytes; i+=Character.charCount(cp);
        }
        out.append("\r\n");
    }

    @GetMapping(value="/{id}.ics",produces="text/calendar;charset=UTF-8")
    ResponseEntity<byte[]> export(Principal account,@PathVariable @Positive long id) {
        var event=find(account,id);
        StringBuilder text=new StringBuilder();
        String summary=escaped(event.title());
        String uid=UUID.nameUUIDFromBytes((account.getName()+"|"+id+"|"+event.startsAt()).getBytes(StandardCharsets.UTF_8))+"@tcghub";
        for (String header:List.of("BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//TCG Hub//Calendar//EN",
                "BEGIN:VEVENT","UID:"+uid,"DTSTAMP:"+ICS_TIME.format(Instant.now()),
                "DTSTART:"+ICS_TIME.format(event.startsAt()),"SUMMARY:"+summary)) line(text,header);
        if (event.endsAt()!=null) line(text,"DTEND:"+ICS_TIME.format(event.endsAt()));
        for (Instant at:event.reminders()) {
            line(text,"BEGIN:VALARM");
            long seconds=Duration.between(event.startsAt(),at).getSeconds();
            line(text,"TRIGGER:"+(seconds<0?"-":"")+"PT"+Math.abs(seconds)+"S");
            line(text,"ACTION:DISPLAY"); line(text,"DESCRIPTION:"+summary); line(text,"END:VALARM");
        }
        line(text,"END:VEVENT"); line(text,"END:VCALENDAR");
        return ResponseEntity.ok().cacheControl(CacheControl.noStore())
                .header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\"tcg-event-"+id+".ics\"")
                .contentType(MediaType.parseMediaType("text/calendar;charset=UTF-8"))
                .body(text.toString().getBytes(StandardCharsets.UTF_8));
    }
}
