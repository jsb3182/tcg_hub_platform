package kr.tcghub;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @AutoConfigureMockMvc @Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class PersonalCalendarIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    @Autowired ObjectMapper json;
    @Autowired Tokens tokens;
    @Value("${tcg.public-origin}") String origin;
    static final String URL="/api/v1/me/calendar";
    String member() {
        String email=UUID.randomUUID()+"@example.invalid";
        db.sql("insert into app_user(email,password_hash) values(?,'fixture')").param(email).update();
        return tokens.issue(email,"ROLE_USER");
    }
    MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder req,String token) {
        return req.header("Authorization","Bearer "+token).header("Origin",origin).header("X-TCG-Request","1");
    }
    @Test void personalAlarmsAreOwnerScopedAndImportable() throws Exception {
        String a=member(),b=member(), title="대회, 교환; \\ "+"한글🎴".repeat(15);
        String body=json.writeValueAsString(Map.of("title",title,"startsAt","2027-03-19T19:30:00+09:00",
                "endsAt","2027-03-19T20:00:00+09:00","reminderMinutes",15));
        api.perform(get(URL)).andExpect(status().isUnauthorized());
        String created=api.perform(as(post(URL),a).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.reminders[0]").value("2027-03-19T10:15:00Z"))
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        long id=json.readTree(created).get("id").asLong();
        api.perform(as(get(URL),a)).andExpect(jsonPath("$.items[0].id").value((int)id));
        api.perform(as(get(URL),b)).andExpect(jsonPath("$.items").isEmpty());
        api.perform(as(get(URL+"/"+id+".ics"),b)).andExpect(status().isNotFound());
        api.perform(as(delete(URL+"/"+id),b)).andExpect(status().isNotFound());
        String text=api.perform(as(get(URL+"/"+id+".ics"),a)).andExpect(status().isOk())
                .andExpect(header().string("Cache-Control","no-store")).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertTrue(text.contains("TRIGGER:-PT900S\r\nACTION:DISPLAY"));
        assertTrue(text.contains("DTSTART:20270319T103000Z\r\n")&&text.contains("DTEND:20270319T110000Z\r\n"));
        assertTrue(text.replace("\r\n ","").contains("SUMMARY:대회\\, 교환\\; \\\\ "+"한글🎴".repeat(15)));
        for (String line:text.split("\r\n")) assertTrue(line.getBytes(StandardCharsets.UTF_8).length<=75);
        api.perform(as(delete(URL+"/"+id),a)).andExpect(status().isNoContent());
        assertEquals(0,db.sql("select count(*) from event_reminder where event_id=?").param(id).query(Integer.class).single());
    }
    @Test void optionalAlarmAndPublicStoreEventsRemainSeparate() throws Exception {
        String a=member();
        long store=db.sql("insert into store(name,address,location) values('Calendar QA','Test',ST_GeogFromText('POINT(127 37)')) returning id").query(Long.class).single();
        long publicId=db.sql("insert into calendar_event(store_id,title,category,starts_at,status) values(?,'Public store','TOURNAMENT',now(),'PUBLISHED') returning id")
                .param(store).query(Long.class).single();
        api.perform(as(get(URL),a)).andExpect(jsonPath("$.items").isEmpty());
        api.perform(as(delete(URL+"/"+publicId),a)).andExpect(status().isNotFound());
        String draft=json.writeValueAsString(Map.of("title","Practice","startsAt","2027-03-19T19:30:00Z"));
        String result=api.perform(as(post(URL),a).contentType(MediaType.APPLICATION_JSON).content(draft)).andExpect(status().isCreated())
                .andExpect(jsonPath("$.reminders").isEmpty()).andReturn().getResponse().getContentAsString();
        String ics=api.perform(as(get(URL+"/"+json.readTree(result).get("id").asLong()+".ics"),a)).andReturn().getResponse().getContentAsString();
        assertFalse(ics.contains("VALARM")); assertFalse(ics.contains("DTEND:"));
        api.perform(as(post(URL),a).contentType(MediaType.APPLICATION_JSON).content(draft.replace("Practice","Injected\\r\\nFIELD")))
                .andExpect(status().isBadRequest());
    }
}
