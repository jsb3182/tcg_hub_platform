package kr.tcghub;

import java.io.IOException;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
class HostControl {
    enum Command { RESTART, SHUTDOWN }
    private final Path socket;
    HostControl(@Value("${tcg.host-control-socket:}") String configured) {
        socket = configured.isBlank() ? null : Path.of(configured);
        if (socket != null && !socket.isAbsolute()) throw new IllegalArgumentException("Expected absolute control socket path");
    }
    boolean available() { return socket != null && Files.exists(socket); }

    void submit(Command command) {
        if (!available()) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        try (Selector selector=Selector.open(); SocketChannel channel=SocketChannel.open(StandardProtocolFamily.UNIX)) {
            channel.configureBlocking(false);
            SelectionKey key=channel.register(selector,SelectionKey.OP_CONNECT);
            if (!channel.connect(UnixDomainSocketAddress.of(socket)))
                while (!channel.finishConnect()) await(selector,deadline);
            key.interestOps(SelectionKey.OP_WRITE);
            ByteBuffer request=StandardCharsets.US_ASCII.encode(command==Command.RESTART ? "restart\n" : "shutdown\n");
            while (request.hasRemaining()) if (channel.write(request)==0) await(selector,deadline);
            key.interestOps(SelectionKey.OP_READ);
            ByteBuffer reply=ByteBuffer.allocate(3);
            while (reply.hasRemaining()) {
                int bytes=channel.read(reply);
                if (bytes<0) break;
                if (bytes==0) await(selector,deadline);
            }
            if (!"OK\n".equals(StandardCharsets.US_ASCII.decode(reply.flip()).toString()))
                throw new IOException("Control service did not accept command");
        } catch (IOException | UnsupportedOperationException e) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
        }
    }
    private static void await(Selector selector,long deadline) throws IOException {
        long millis=TimeUnit.NANOSECONDS.toMillis(deadline-System.nanoTime());
        if (millis<=0) throw new IOException("Host control timeout");
        selector.select(millis);
        selector.selectedKeys().clear();
    }
}
