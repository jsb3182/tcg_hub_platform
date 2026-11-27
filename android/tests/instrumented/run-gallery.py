"""Run the production WebView document exporter on an Android 10+ emulator.

Set ANDROID_HOME and JAVA_HOME, then use this file with --serial emulator-5554.
--adb-port selects a separate local adb server. Requires Android SDK platform 35,
build-tools 35.0.0 and JDK 17. The test APK uses a disposable signing key.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
from xml.etree import ElementTree


def run(*command):
    return subprocess.check_output([str(arg) for arg in command], text=True, encoding="utf-8",
                                   errors="replace", stderr=subprocess.STDOUT, timeout=90)


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--serial", required=True)
    options.add_argument("--adb-port", default="5037", type=int)
    args = options.parse_args()
    if not re.fullmatch(r"emulator-[0-9]+", args.serial):
        options.error("Choose a dedicated emulator serial")
    android = Path(__file__).resolve().parents[2]
    sdk = Path(os.environ["ANDROID_HOME"])
    jdk = Path(os.environ["JAVA_HOME"]) / "bin"
    build = sdk / "build-tools" / "35.0.0"
    platform = sdk / "platforms" / "android-35" / "android.jar"
    exe = ".exe" if os.name == "nt" else ""
    script = ".bat" if os.name == "nt" else ""
    adb = [sdk/"platform-tools"/("adb"+exe), "-P", args.adb_port, "-s", args.serial]
    if run(*adb, "shell", "getprop", "ro.boot.qemu").strip() != "1":
        raise SystemExit("Selected Android transport is not an emulator")
    if int(run(*adb, "shell", "getprop", "ro.build.version.sdk").strip()) < 29:
        raise SystemExit("The MediaStore gallery path needs API 29 or newer")
    package = "kr.tcghub.control.galleryqa"
    if run(*adb, "shell", "pm", "list", "packages", package).strip():
        raise SystemExit("This emulator already contains a gallery test package")
    with tempfile.TemporaryDirectory(prefix="tcg-gallery-") as tmp:
        work = Path(tmp)
        gen, classes, dex = [work / name for name in ("gen", "classes", "dex")]
        for folder in (gen, classes, dex):
            folder.mkdir()
        uri = "http://schemas.android.com/apk/res/android"
        ns = "{" + uri + "}"
        ElementTree.register_namespace("android", uri)
        manifest = ElementTree.parse(android/"AndroidManifest.xml")
        root = manifest.getroot()
        root.set("package", package)
        app = root.find("application")
        for activity in app.findall("activity"):
            activity.set(ns+"name", "kr.tcghub.control" + activity.get(ns+"name"))
        ElementTree.SubElement(app, "activity", {ns+"name":"kr.tcghub.control.GalleryProbe$Page", ns+"exported":"false"})
        ElementTree.SubElement(root, "instrumentation", {ns+"name":"kr.tcghub.control.GalleryProbe", ns+"targetPackage":package})
        manifest.write(work/"AndroidManifest.xml", encoding="utf-8", xml_declaration=True)
        aapt = build/("aapt2"+exe)
        apk = work/"qa.apk"
        run(aapt, "compile", "--dir", android/"res", "-o", work/"res.zip")
        run(aapt, "link", "--java", gen, "--custom-package", "kr.tcghub.control", "-I", platform,
            "--manifest", work/"AndroidManifest.xml", "-o", work/"unsigned.apk", work/"res.zip")
        (gen/"kr/tcghub/control/ReleasePin.java").write_text(
            'package kr.tcghub.control; final class ReleasePin { static final String HELPER="",ARCHIVE=""; }')
        run(jdk/("javac"+exe), "-encoding", "UTF-8", "--release", "8", "-classpath", platform, "-d", classes,
            *(android/"src").rglob("*.java"), *gen.rglob("*.java"), Path(__file__).with_name("GalleryProbe.java"))
        jar = jdk/("jar"+exe)
        run(jar, "cf", work/"classes.jar", "-C", classes, ".")
        run(build/("d8"+script), "--lib", platform, "--min-api", "28", "--output", dex, work/"classes.jar")
        run(jar, "uf", work/"unsigned.apk", "-C", dex, "classes.dex")
        run(build/("zipalign"+exe), "-f", "4", work/"unsigned.apk", work/"aligned.apk")
        key = work/"fixture.p12"
        run(jdk/("keytool"+exe), "-genkeypair", "-keyalg", "RSA", "-keystore", key, "-storepass", "fixture-only",
            "-alias", "qa", "-dname", "CN=Disposable gallery fixture", "-validity", "1")
        run(build/("apksigner"+script), "sign", "--ks", key, "--ks-pass", "pass:fixture-only",
            "--out", apk, work/"aligned.apk")
        run(*adb, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
        run(*adb, "shell", "wm", "dismiss-keyguard")
        assert "Success" in run(*adb, "install", apk)
        try:
            result = run(*adb, "shell", "am", "instrument", "-w", package+"/kr.tcghub.control.GalleryProbe")
            print(result)
            if "INSTRUMENTATION_CODE: -1" not in result or "folder_picker=1,cancel_callback=true" not in result:
                raise SystemExit(1)
        finally:
            run(*adb, "uninstall", package)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.output) from error
