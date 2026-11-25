package kr.tcghub.control;

/** Exercises the same URL normalizer used by the launcher, copy and share sheet. */
public final class PublicSiteTest {
    private static void check(String input, String expected) {
        String actual = PublicSite.root(input);
        if (!expected.equals(actual)) throw new AssertionError(input + " produced " + actual);
    }

    public static void main(String[] args) {
        String home = "https://cards.example.com/";
        check(" HTTPS://Cards.Example.Com:443/admin?token=discard#fragment ", home);
        check("https://cards.example.com.", home);
        check("https://cards.example.com//elsewhere.example/u", home);
        check("https://도감.한국/카드", "https://xn--439a29l.xn--3e0b707e/");
        check(PublicSite.root(home), home);
        for (String invalid : new String[]{
                null, "", "http://cards.example.com", "javascript:alert(1)", "intent://cards.example.com",
                "https://admin:password@cards.example.com", "https://good.example@evil.example/",
                "https://cards.example.com:444/", "https://cards.example.com:/", "https:////example.com",
                "https://local", "https://127.0.0.1", "https://2130706433", "https://[::1]",
                "https://server.localhost", "https://home.arpa", "https://pc.local", "https://service.internal",
                "https://cards.example.com\\@evil.example", "https://cards%2Eexample.com",
                "https://bad..example.com", "https://bad-.example.com", "https://cards.example.com/\npath"
        }) check(invalid, "");
        System.out.println("Public HTTPS roots, normalization, persistence shape and rejected URI forms passed.");
    }
}
