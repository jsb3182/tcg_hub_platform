package kr.tcghub.control;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.io.IOException;
import java.util.Arrays;
import java.util.Locale;

final class WakePacket {
    static String mac(String raw) {
        String text = raw.trim().replace('-', ':').toUpperCase(Locale.ROOT);
        if (!text.matches("[0-9A-F]{2}(:[0-9A-F]{2}){5}") || text.equals("00:00:00:00:00:00")
                || (Integer.parseInt(text.substring(0,2), 16) & 1) != 0)
            throw new IllegalArgumentException("개인 PC의 유선 랜카드 MAC 주소를 입력하세요.");
        return text;
    }

    static byte[] encode(String raw) {
        String[] octets = mac(raw).split(":");
        byte[] address = new byte[6];
        for (int i = 0; i < address.length; i++) address[i] = (byte) Integer.parseInt(octets[i], 16);
        byte[] bytes = new byte[102];
        Arrays.fill(bytes, 0, 6, (byte) 0xff);
        for (int i = 6; i < bytes.length; i += 6) System.arraycopy(address, 0, bytes, i, 6);
        return bytes;
    }

    static final class Lan {
        final String cidr;
        final InetAddress broadcast;
        Lan(InetAddress address, int prefix) throws UnknownHostException {
            if (!(address instanceof Inet4Address) || prefix < 8 || prefix > 30)
                throw new IllegalArgumentException("사설 IPv4 Wi-Fi가 필요합니다.");
            byte[] b = address.getAddress();
            int a = b[0] & 255, second = b[1] & 255;
            int minimum = a == 10 ? 8 : a == 172 && second >= 16 && second <= 31 ? 12
                    : a == 192 && second == 168 ? 16 : 33;
            if (prefix < minimum) throw new IllegalArgumentException("사설 IPv4 Wi-Fi가 필요합니다.");
            byte[] network = b.clone(), high = b.clone();
            for (int i = 0; i < 4; i++) {
                int bits = Math.max(0, Math.min(8, prefix - 8 * i));
                int mask = (0xff << (8 - bits)) & 0xff;
                network[i] &= mask;
                high[i] |= ~mask;
            }
            cidr = InetAddress.getByAddress(network).getHostAddress() + "/" + prefix;
            broadcast = InetAddress.getByAddress(high);
        }
    }

    static void send(DatagramSocket socket, InetAddress broadcast, int port, String mac) throws IOException {
        byte[] data = encode(mac);
        socket.setBroadcast(true);
        socket.send(new DatagramPacket(data, data.length, broadcast, port));
    }
}
