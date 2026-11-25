package kr.tcghub;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.zip.CRC32;
import javax.imageio.ImageIO;
import javax.imageio.stream.MemoryCacheImageInputStream;
import javax.imageio.stream.MemoryCacheImageOutputStream;
import org.springframework.http.HttpStatus;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

final class UploadCell {
    private static final int WIDTH=300, HEIGHT=438, MAX=1024*1024;
    private static final byte[] MAGIC={(byte)137,80,78,71,13,10,26,10};
    private UploadCell() {}

    static byte[] normalize(MultipartFile file) throws IOException {
        String name = file.getOriginalFilename(), type = file.getContentType();
        if (name==null || !name.toLowerCase(Locale.ROOT).endsWith(".png") ||
                (type!=null && !type.equalsIgnoreCase("image/png") && !type.equalsIgnoreCase("application/octet-stream"))) {
            throw new ResponseStatusException(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
        }
        if (file.getSize()>MAX) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE);
        byte[] bytes;
        try (var input = file.getInputStream()) { bytes = input.readNBytes(MAX+1); }
        if (bytes.length>MAX) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE);
        if (!Arrays.equals(MAGIC,Arrays.copyOf(bytes,MAGIC.length))) throw invalid();
        byte[] clean = imageChunks(bytes);
        BufferedImage source;
        try (var input = new MemoryCacheImageInputStream(new ByteArrayInputStream(clean))) {
            var reader = ImageIO.getImageReadersByFormatName("PNG").next();
            try {
                reader.setInput(input,true,true);
                source = reader.read(0);
            } catch (IOException | IllegalArgumentException ex) { throw invalid(); }
            finally { reader.dispose(); }
        }
        var cell = new BufferedImage(WIDTH,HEIGHT,BufferedImage.TYPE_INT_RGB);
        var graphics = cell.createGraphics();
        try {
            graphics.setColor(new Color(24,24,24));
            graphics.fillRect(0,0,WIDTH,HEIGHT);
            graphics.drawImage(source,0,0,null);
        } finally { graphics.dispose(); }
        var result = new ByteArrayOutputStream();
        try (var output = new MemoryCacheImageOutputStream(result)) {
            var writer = ImageIO.getImageWritersByFormatName("PNG").next();
            try { writer.setOutput(output); writer.write(cell); }
            finally { writer.dispose(); }
        }
        return result.toByteArray();
    }

    // Only pixel, palette and transparency chunks reach the decoder. Metadata can carry compressed payloads.
    private static byte[] imageChunks(byte[] bytes) {
        ByteBuffer data = ByteBuffer.wrap(bytes);
        data.position(MAGIC.length);
        var pixels = new ByteArrayOutputStream(bytes.length);
        pixels.writeBytes(MAGIC);
        boolean imageData=false;
        while (data.remaining()>=12) {
            int start=data.position();
            int size=data.getInt();
            if (size<0 || size>data.remaining()-8) throw invalid();
            String type=new String(bytes,start+4,4,StandardCharsets.US_ASCII);
            if (start==8 && !type.equals("IHDR")) throw invalid();
            var crc=new CRC32();
            crc.update(bytes,start+4,4+size);
            if (data.getInt(start+8+size)!=(int)crc.getValue()) throw invalid();
            switch (type) {
                case "IHDR" -> {
                    if (start!=8 || size!=13 || data.getInt(start+8)!=WIDTH || data.getInt(start+12)!=HEIGHT) throw invalid();
                }
                case "IDAT" -> imageData=true;
                case "IEND" -> { if (size!=0 || !imageData || start+12!=bytes.length) throw invalid(); }
                case "PLTE","tRNS" -> { }
                case "acTL","fcTL","fdAT" -> throw invalid();
                default -> {
                    if ((bytes[start+4]&0x20)==0) throw invalid();
                    data.position(start+size+12);
                    continue;
                }
            }
            pixels.write(bytes,start,size+12);
            data.position(start+size+12);
            if (type.equals("IEND")) return pixels.toByteArray();
        }
        throw invalid();
    }

    private static ResponseStatusException invalid() { return new ResponseStatusException(HttpStatus.BAD_REQUEST); }
}
