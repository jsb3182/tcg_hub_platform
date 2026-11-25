package kr.tcghub;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import javax.imageio.ImageIO;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"tcg.public-origin=http://127.0.0.1:8080","tcg.cf-team-domain=","tcg.cf-audience="})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class AdminMediaIntegrationTest {
    @TempDir static Path spool;
    @DynamicPropertySource static void config(DynamicPropertyRegistry props) {
        props.add("tcg.spool-root", () -> spool.toString());
    }
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    String route, bearer;
    Cookie cookie;
    long card,variant;
    @BeforeEach void setup() {
        String email=UUID.randomUUID()+"@image-test.invalid";
        var user=db.sql("insert into app_user(email,role,password_hash) values(?,'ROLE_ADMIN','unused') returning id")
                .param(email).query(Long.class).single();
        db.sql("insert into local_admin_factor(user_id,secret_base32) values(?,'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ')").param(user).update();
        String session=UUID.randomUUID().toString().replace("-","")+"12345678901";
        db.sql("insert into local_admin_session(token_hash,user_id,expires_at) values(?,?,now()+interval '1 hour')")
                .params(Accounts.hash(session),user).update();
        cookie=new Cookie(LocalAdmin.COOKIE,session);
        bearer="Bearer "+tokens.issue(email,"ROLE_ADMIN");
        card=db.sql("insert into card(game_code,name,status) values('NIVEL',?,'PUBLISHED') returning id")
                .param("media-upload-"+UUID.randomUUID()).query(Long.class).single();
        variant=db.sql("insert into card_variant(card_id) values(?) returning id").param(card).query(Long.class).single();
        route="/api/v1/admin/variants/"+variant+"/image";
    }

    private byte[] png(int width,int pixel) throws Exception {
        var image=new BufferedImage(width,438,BufferedImage.TYPE_INT_ARGB);
        image.setRGB(0,0,pixel);
        var output=new ByteArrayOutputStream();
        ImageIO.write(image,"PNG",output);
        return output.toByteArray();
    }
    private MockHttpServletRequestBuilder local(MockHttpServletRequestBuilder request) {
        return request.header("Host","127.0.0.1:8080").with(req -> {
            req.setRemoteAddr("127.0.0.1"); req.setLocalAddr("127.0.0.1"); req.setLocalPort(8080); return req;
        });
    }
    private MockHttpServletRequestBuilder upload(String name, byte[] data) {
        return local(multipart(route).file(new MockMultipartFile("file",name,"image/png",data)).servletPath(route))
                .header("Origin","http://127.0.0.1:8080").header("X-TCG-Request","1");
    }
    @Test void protectedUploadWritesWorkerCellDeduplicatesAndRollsBack() throws Exception {
        byte[] file=png(300,0xffff0000);
        http.perform(upload("crop.png",file).header("Authorization",bearer)).andExpect(status().isForbidden());
        http.perform(upload("crop.png",file).header("Authorization","Bearer "+tokens.issue("other@image-test.invalid","ROLE_USER"))
                .cookie(cookie)).andExpect(status().isForbidden());
        for(int i=0;i<2;i++) http.perform(upload("crop.png",file).header("Authorization",bearer).cookie(cookie))
                .andExpect(status().isAccepted()).andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.variantId").value(variant));
        long id=db.sql("select id from media_job where variant_id=?").param(variant).query(Long.class).single();
        String key=db.sql("select spool_key from media_job where id=?").param(id).query(String.class).single();
        Path cell=spool.resolve(key);
        assertTrue(key.matches("[0-9a-f]{32}\\.png"));
        BufferedImage img=ImageIO.read(cell.toFile());
        assertEquals(300,img.getWidth()); assertEquals(438,img.getHeight());
        assertFalse(img.getColorModel().hasAlpha());
        assertEquals(0xff181818,img.getRGB(1,1));
        assertEquals(0xffff0000,img.getRGB(0,0));
        String statusPath="/api/v1/admin/media-jobs/"+id;
        http.perform(local(get(statusPath)).header("Authorization",bearer).cookie(cookie))
                .andExpect(status().isOk()).andExpect(jsonPath("$.id").value(id));
        TestTransaction.flagForRollback();
        TestTransaction.end();
        assertFalse(Files.exists(cell));
    }
    @Test void rejectsWrongFormatDamagedDataDimensionsAndUnpublishedCard() throws Exception {
        byte[] file=png(300,1);
        http.perform(upload("crop.jpg",file).header("Authorization",bearer).cookie(cookie)).andExpect(status().isUnsupportedMediaType());
        http.perform(upload("crop.png",new byte[15]).header("Authorization",bearer).cookie(cookie)).andExpect(status().isBadRequest());
        http.perform(upload("crop.png",png(299,1)).header("Authorization",bearer).cookie(cookie)).andExpect(status().isBadRequest());
        byte[] corrupt=file.clone();
        corrupt[corrupt.length-1]^=1;
        http.perform(upload("crop.png",corrupt).header("Authorization",bearer).cookie(cookie)).andExpect(status().isBadRequest());
        http.perform(upload("crop.png",new byte[1024*1024+1]).header("Authorization",bearer).cookie(cookie)).andExpect(status().isPayloadTooLarge());
        db.sql("update card set status='PENDING' where id=?").param(card).update();
        http.perform(upload("crop.png",file).header("Authorization",bearer).cookie(cookie)).andExpect(status().isConflict());
        assertEquals(0,db.sql("select count(*) from media_job where variant_id=?").param(variant).query(Integer.class).single());
    }
}
