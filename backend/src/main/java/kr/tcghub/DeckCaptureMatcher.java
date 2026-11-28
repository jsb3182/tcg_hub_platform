package kr.tcghub;

import java.awt.image.BufferedImage;
import java.io.IOException;
import java.util.*;
import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;
import jakarta.validation.constraints.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
class DeckCaptureMatcher {
    record Candidate(long cardId,String number,String name,String imageUrl,double confidence) {}
    record Slot(int index,int left,int top,int width,int height,List<Candidate> candidates,boolean needsReview) {}
    record Result(int width,int height,int columns,int rows,List<Slot> slots) {}
    record Sample(long id,String number,String name,String image,long hash) {}
    private final JdbcClient db;
    DeckCaptureMatcher(JdbcClient db) { this.db=db; }

    @PostMapping(value={"/api/decks/import-capture","/api/v1/me/decks/import-capture"}, consumes="multipart/form-data")
    Result match(@RequestParam MultipartFile file,@RequestParam @Pattern(regexp=AdminCatalogApi.GAMES) String game,
                 @RequestParam(defaultValue="10") @Min(1) @Max(12) int columns,
                 @RequestParam @Min(1) @Max(15) int rows,@RequestParam(defaultValue="0") double left,
                 @RequestParam(defaultValue="0") double top,@RequestParam(defaultValue="1") double right,
                 @RequestParam(defaultValue="1") double bottom) throws IOException {
        if (!(0<=left && left<right && right<=1 && 0<=top && top<bottom && bottom<=1) || columns*rows>120) throw invalid();
        if (file.getSize()>1024*1024) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE);
        BufferedImage image;
        try (var stream=new MemoryCacheImageInputStream(file.getInputStream())) {
            var readers=ImageIO.getImageReaders(stream);
            if (!readers.hasNext()) throw invalid();
            var reader=readers.next();
            try {
                if (!Set.of("png","jpeg","jpg").contains(reader.getFormatName().toLowerCase(Locale.ROOT))) throw invalid();
                reader.setInput(stream,true,true);
                int w=reader.getWidth(0),h=reader.getHeight(0);
                if ((long)w*h>5_000_000 || w*(right-left)/columns<12 || h*(bottom-top)/rows<16) throw invalid();
                image=reader.read(0);
            } catch (javax.imageio.IIOException e) {throw invalid();}
            finally {reader.dispose();}
        }
        var pool=db.sql("""
            select distinct on (f.id,c.id) c.id,c.number,coalesce(c.specs->'names'->>'ko',r.name,c.name) as name,
                '/media/'||f.storage_key as image,f.capture_hash::bigint as hash
            from catalog_art_file f join catalog_art_card a on a.file_id=f.id join card c on c.id=a.card_id
                 left join card_korean_reading r on r.card_id=c.id and r.due_at is null
            where c.game_code=? and c.status='PUBLISHED' and f.capture_hash is not null and f.storage_key is not null
              and not starts_with(f.source_url,'https://images.ygoprodeck.com/')
            order by f.id,c.id
            """).param(game).query(Sample.class).list();
        var slots=new ArrayList<Slot>(rows*columns);
        int w=image.getWidth(),h=image.getHeight();
        for (int row=0;row<rows;row++) for (int col=0;col<columns;col++) {
            int x=(int)(w*(left+(right-left)*col/columns)), y=(int)(h*(top+(bottom-top)*row/rows));
            int cw=(int)(w*(left+(right-left)*(col+1)/columns))-x,ch=(int)(h*(top+(bottom-top)*(row+1)/rows))-y;
            long hash=signature(image,x,y,cw,ch);
            var best=new ArrayList<Candidate>(4);
            int transitions=Long.bitCount(hash);
            if (transitions>=3 && transitions<=61) for (var sample:pool) {
                double confidence=(64-Long.bitCount(hash^sample.hash()))/64d;
                if (confidence<0.68 || best.size()==3 && best.get(2).confidence()>=confidence) continue;
                int old=-1;
                for (int n=0;n<best.size();n++) if (best.get(n).cardId()==sample.id()) old=n;
                if (old>=0 && best.get(old).confidence()>=confidence) continue;
                if (old>=0) best.remove(old);
                best.add(new Candidate(sample.id(),sample.number(),sample.name(),sample.image(),confidence));
                best.sort(Comparator.comparingDouble(Candidate::confidence).reversed());
                if (best.size()>3) best.remove(3);
            }
            boolean uncertain=best.isEmpty() || best.get(0).confidence()<.91 ||
                    best.size()>1 && best.get(0).confidence()-best.get(1).confidence()<.08;
            slots.add(new Slot(slots.size(),x,y,cw,ch,best,uncertain));
        }
        return new Result(w,h,columns,rows,slots);
    }
    static long signature(BufferedImage image,int x,int y,int w,int h) {
        long hash=0;
        for (int j=0;j<8;j++) {
            int previous=0;
            for (int i=0;i<9;i++) {
                int rgb=image.getRGB(x+(int)(w*(.12+.095*i)),y+(int)(h*(.19+.065*j)));
                int gray=(299*(rgb>>16&255)+587*(rgb>>8&255)+114*(rgb&255))/1000;
                if (i>0) hash=(hash<<1)|(previous>gray?1:0);
                previous=gray;
            }
        }
        return hash;
    }
    private static ResponseStatusException invalid(){return new ResponseStatusException(HttpStatus.BAD_REQUEST,"캡처 이미지 또는 배열 범위를 확인해 주세요.");}
}
