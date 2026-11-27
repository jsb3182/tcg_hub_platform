package kr.tcghub;

import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.file.*;
import java.security.Principal;
import java.util.Base64;
import java.util.Locale;
import javax.imageio.ImageIO;
import jakarta.validation.constraints.Positive;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/me/decks/{id}/decoration/{slot:cover|main|extra}")
class DeckDecorationApi {
    record Picture(String image) {}
    private final JdbcClient db;
    private final Path directory;
    DeckDecorationApi(JdbcClient db,@Value("${tcg.media-root}") String media) {
        this.db=db;
        this.directory=Path.of(media).toAbsolutePath().normalize().resolve("deck-art");
    }

    private void owner(Principal user,long id,boolean lock) {
        if(db.sql("select d.id from deck d join app_user u on u.id=d.owner_id where d.id=? and u.email=? and u.enabled"
                +(lock?" for update of d":"")).param(id).param(user.getName()).query(Long.class).optional().isEmpty())
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }
    @GetMapping
    @Transactional(readOnly=true)
    ResponseEntity<Picture> get(Principal user,@PathVariable @Positive long id,@PathVariable String slot) throws IOException {
        owner(user,id,false);
        boolean present=db.sql("select exists(select 1 from deck_decoration where deck_id=? and slot=?)")
                .param(id).param(slot).query(Boolean.class).single();
        String image=present ? "data:image/jpeg;base64,"+Base64.getEncoder().encodeToString(Files.readAllBytes(file(id,slot))) : null;
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(new Picture(image));
    }
    private Path file(long id,String slot) { return directory.resolve(id+"-"+slot+".jpg"); }
    private static ResponseStatusException invalid() {return new ResponseStatusException(HttpStatus.UNSUPPORTED_MEDIA_TYPE);}

    @PostMapping(consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
    @Transactional
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void put(Principal user,@PathVariable @Positive long id,@PathVariable String slot,@RequestParam MultipartFile image) throws IOException {
        owner(user,id,true);
        if(image.getSize()>512*1024) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE);
        String name=image.getOriginalFilename();
        if(name==null || !name.toLowerCase(Locale.ROOT).matches(".+\\.jpe?g")) throw invalid();
        byte[] data=image.getBytes();
        if(data.length<4 || data[0]!=(byte)255 || data[1]!=(byte)216 || data[2]!=(byte)255) throw invalid();
        BufferedImage decoded;
        try(var input=ImageIO.createImageInputStream(new ByteArrayInputStream(data))) {
            var readers=ImageIO.getImageReadersByFormatName("JPEG");
            var reader=readers.next();
            try {
                reader.setInput(input,true,true);
                if(reader.getWidth(0)>1024 || reader.getHeight(0)>1024) throw invalid();
                decoded=reader.read(0);
            } catch(javax.imageio.IIOException ex) { throw invalid(); }
            finally { reader.dispose(); }
        }
        Files.createDirectories(directory);
        Path target=file(id,slot), temp=Files.createTempFile(directory,"upload-",".tmp");
        try {
            BufferedImage rgb=new BufferedImage(decoded.getWidth(),decoded.getHeight(),BufferedImage.TYPE_INT_RGB);
            var graphics=rgb.createGraphics();
            try { graphics.drawImage(decoded,0,0,null); } finally { graphics.dispose(); }
            if(!ImageIO.write(rgb,"jpeg",temp.toFile())) throw invalid();
            db.sql("insert into deck_decoration(deck_id,slot,storage_key) values(?,?,?) on conflict(deck_id,slot) do nothing")
                    .param(id).param(slot).param(target.getFileName().toString()).update();
            Files.move(temp,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(temp); }
    }
}
