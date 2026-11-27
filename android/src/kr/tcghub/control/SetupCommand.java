package kr.tcghub.control;

final class SetupCommand {
    static final String TAG = "a90-2026.11.28.6";
    private static final String HELPER =
            "https://github.com/jsb3182/tcg_hub_platform/releases/download/"
                    + TAG
                    + "/setup-termux.sh";

    private SetupCommand() {}

    /**
     * One paste into an interactive Termux shell. The temporary script runs only after
     * verification.
     */
    static String forHashes(String helper, String archive) {
        if (helper == null
                || !helper.matches("[a-f0-9]{64}")
                || archive == null
                || !archive.matches("[a-f0-9]{64}"))
            throw new IllegalArgumentException("Invalid release checksum");
        return "(set -eu; umask 077; if ! { command -v curl && command -v mktemp && command -v"
                   + " sha256sum; } >/dev/null; then pkg install -y curl coreutils; fi; f=$(mktemp"
                   + " \"$PREFIX/tmp/tcg-setup.XXXXXXXX\"); trap 'rm -f -- \"$f\"' EXIT; curl"
                   + " --proto '=https' --proto-redir '=https' -fL --retry 3 '"
                + HELPER
                + "' -o \"$f\"; printf '%s  %s\\n' '"
                + helper
                + "' \"$f\" | sha256sum --check; bash \"$f\" --release "
                + TAG
                + " --archive-sha256 "
                + archive
                + ")";
    }
}
