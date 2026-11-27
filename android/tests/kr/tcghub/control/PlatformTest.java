package kr.tcghub.control;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.util.Arrays;

/** Pure Java transport fixture uses only a kernel loopback datagram socket. */
public final class PlatformTest {
    static void require(boolean condition) { if (!condition) throw new AssertionError(); }

    public static void main(String[] args) throws Exception {
        PlatformOrigin publicHost = new PlatformOrigin("https://cards.example.org");
        require(publicHost.owns("https://cards.example.org:443/binder"));
        require(publicHost.adminPage("https://cards.example.org/admin?tab=operations"));
        String notice = "http://nivelarena.co.kr/bbs/board.php?bo_table=notice&wr_id=198";
        require(PlatformOrigin.externalBrowserLink(notice, true));
        require(PlatformOrigin.externalBrowserLink(notice.replace("notice", "booster"), true));
        require(!PlatformOrigin.externalBrowserLink(notice, false));
        require(!publicHost.owns(notice) && !publicHost.resource(notice) && PublicSite.root(notice).isEmpty());
        for (String invalid : new String[]{notice + "#other", notice + "&next=https://elsewhere.test",
                notice.replace("198", "new"), notice.replace("notice", "user"),
                notice.replace(".co.kr", ".co.kr.invalid"), notice.replace(".co.kr", ".co.kr:8080"),
                notice.replace(".co.kr", ".co.kr@elsewhere.test")}) {
            require(!PlatformOrigin.externalBrowserLink(invalid, true));
        }
        require(publicHost.resource("https://tile.openstreetmap.org/13/8752/3882.png"));
        require(publicHost.resource("https://assets.tcgdex.net/ko/test.webp"));
        require(publicHost.resource("https://artworks-jp-n.ygoresources.com/1/2/4041_2.png"));
        require(publicHost.resource("https://artworks-en-n.ygoresources.com/0/40/41_1.png"));
        require(publicHost.resource("https://artworks-ko-db.ygoresources.com/0/40/41_1.png"));
        String riotCard = "https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/"
                + "0123456789abcdef0123456789abcdef01234567-744x1039.png";
        require(publicHost.resource(riotCard));
        require(publicHost.resource(riotCard + "?accountingTag=RB"));
        require(!publicHost.resource(riotCard + "?v=1"));
        require(!publicHost.resource(riotCard.replace("game_data_live", "other")));
        require(!publicHost.resource("https://artworks-jp-rn.ygoresources.com/1/51/50_1.png"));
        require(!publicHost.resource("https://artworks-ko-db.ygoresources.com/0/40/41_1.png?v=1"));
        require(!publicHost.resource("https://artworks-jp-n.ygoresources.com/other.png"));
        require(publicHost.resource("https://www.onepiece-cardgame.kr/fileDownload?downname=OP01.png"));
        for (String blocked : new String[]{"file:///sdcard/test", "content://com.termux.documents/test",
                "intent://cards.example.org", "https://cards.example.org.evil.example/admin",
                "https://cards.example.org@evil.example/", "https://a@cards.example.org/", "http://cards.example.org/",
                "https://tiles.example.org/private", "https://cards.example.org:8443/",
                "https://www.onepiece-cardgame.com/images/cardlist/card/../../other", "http://127.0.0.1:8080"})
            require(!publicHost.resource(blocked));
        PlatformOrigin local = new PlatformOrigin(PlatformOrigin.LOCAL);
        require(local.owns("http://127.0.0.1:8080/play"));
        require(!local.owns("http://127.0.0.1:5432/"));
        String saved = "https://cards.example.org/";
        String suggested = "https://paired.example.org";
        require(PlatformOrigin.launchRoot(false, "", "", false).isEmpty());
        require(PlatformOrigin.launchRoot(false, "", suggested, false).isEmpty());
        require(PlatformOrigin.launchRoot(false, saved, suggested, false).equals(saved));
        require(PlatformOrigin.launchRoot(false, saved, suggested, true).equals(saved));
        require(PlatformOrigin.launchRoot(false, "", suggested, true).equals(suggested + "/"));
        require(PlatformOrigin.launchRoot(false, "", "", true).equals(PlatformOrigin.LOCAL));
        require(PlatformOrigin.launchRoot(true, saved, suggested, true).equals(PlatformOrigin.LOCAL));
        require(PlatformOrigin.launchRoot(true, saved, suggested, false).isEmpty());
        require(PlatformOrigin.launchRoot(false, "", "http://example.org", true).isEmpty());
        require(PlatformOrigin.pairedRoot("", "").equals(PlatformOrigin.LOCAL));
        require(PlatformOrigin.pairedRoot("", suggested).equals(suggested + "/"));
        require(PlatformOrigin.pairedRoot("http://127.0.0.1:8080", suggested).equals(PlatformOrigin.LOCAL));
        require(PlatformOrigin.pairedRoot(saved, suggested).equals(saved));
        InetAddress ip = InetAddress.getByAddress(new byte[]{(byte)192,(byte)168,4,(byte)129});
        WakePacket.Lan lan = new WakePacket.Lan(ip, 25);
        require(lan.cidr.equals("192.168.4.128/25") && lan.broadcast.getHostAddress().equals("192.168.4.255"));
        for (int prefix : new int[]{0, 8, 15, 31, 32}) {
            try { new WakePacket.Lan(ip, prefix); throw new AssertionError(); } catch (IllegalArgumentException expected) {}
        }
        for (String mac : new String[]{"ff:ff:ff:ff:ff:ff","00:00:00:00:00:00","01:00:00:00:00:01","ab","localhost"}) {
            try { WakePacket.mac(mac); throw new AssertionError(); } catch (IllegalArgumentException expected) {}
        }
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (DatagramSocket receiver = new DatagramSocket(0,loopback); DatagramSocket sender = new DatagramSocket(0,loopback)) {
            receiver.setSoTimeout(2000);
            WakePacket.send(sender,loopback,receiver.getLocalPort(),"02-11-22-33-44-55");
            DatagramPacket got = new DatagramPacket(new byte[103],103); receiver.receive(got);
            require(got.getLength()==102 && loopback.equals(got.getAddress()));
            byte[] bytes = got.getData();
            for (int i = 0; i < 6; i++) require((bytes[i] & 255) == 255);
            for (int i = 6; i < 102; i+=6)
                require(Arrays.equals(Arrays.copyOfRange(bytes,i,i+6),new byte[]{2,17,34,51,68,85}));
        }
        System.out.println("Web origins, image allowlist, private subnet and 102-byte loopback UDP verified.");
    }
}
