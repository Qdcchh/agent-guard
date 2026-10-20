"""用 OpenSSL 3 交叉验证两方协同 SM2 参考实现（双向）。

运行：python3 cosm2_xcheck_openssl.py
要求：OpenSSL 3.x（macOS 自带的是 LibreSSL，不支持 SM2；请用 brew 安装的
openssl@3，或在 Linux/Docker 里运行），Python 3.9+ 且 hashlib 支持 sm3。
预期输出：cosign->openssl verify: 20 /20 和 openssl->python verify: True
"""

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp())
import cosm2_reference as c  # noqa: E402 - script-local path is initialized above

ok = 0
for i in range(20):
    p1, p2 = c.Party1(), c.Party2()
    pub = p2.keygen_finish(p1.keygen_msg())
    p1.set_public(pub)
    msg = os.urandom(50 + i)
    r, s = c.cosign(p1, p2, msg)
    open("pub.pem", "w").write(c.public_key_pem(pub))
    open("msg.bin", "wb").write(msg)
    open("sig.der", "wb").write(c.der_signature(r, s))
    res = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            "pub.pem",
            "-rawin",
            "-in",
            "msg.bin",
            "-sigfile",
            "sig.der",
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:1234567812345678",
        ],
        capture_output=True,
        text=True,
    )
    assert "Verified Successfully" in res.stdout, res.stdout + res.stderr
    # tampered must fail
    open("msg.bin", "wb").write(msg + b"!")
    res2 = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            "pub.pem",
            "-rawin",
            "-in",
            "msg.bin",
            "-sigfile",
            "sig.der",
            "-digest",
            "sm3",
            "-pkeyopt",
            "distid:1234567812345678",
        ],
        capture_output=True,
        text=True,
    )
    assert "Verified Successfully" not in res2.stdout
    ok += 1
print("cosign->openssl verify:", ok, "/20")
# reverse: openssl signs, python verifies
subprocess.run(
    [
        "openssl",
        "genpkey",
        "-algorithm",
        "EC",
        "-pkeyopt",
        "ec_paramgen_curve:SM2",
        "-out",
        "k.pem",
    ],
    check=True,
)
subprocess.run(["openssl", "pkey", "-in", "k.pem", "-pubout", "-out", "kpub.pem"], check=True)
txt = subprocess.run(
    ["openssl", "pkey", "-pubin", "-in", "kpub.pem", "-text", "-noout"],
    capture_output=True,
    text=True,
).stdout
hexs = "".join(re.findall(r"[0-9a-f]{2}", txt.split("pub:")[1].split("ASN1")[0]))
x, y = int(hexs[2:66], 16), int(hexs[66:130], 16)
open("m2.bin", "wb").write(b"hello agent guard")
subprocess.run(
    [
        "openssl",
        "pkeyutl",
        "-sign",
        "-inkey",
        "k.pem",
        "-rawin",
        "-in",
        "m2.bin",
        "-out",
        "s2.der",
        "-digest",
        "sm3",
        "-pkeyopt",
        "distid:1234567812345678",
    ],
    check=True,
)
der = open("s2.der", "rb").read()


def rd(off):
    length = der[off + 1]
    return int.from_bytes(der[off + 2 : off + 2 + length], "big"), off + 2 + length


r, o = rd(2)
s, _ = rd(o)
print("openssl->python verify:", c.verify((x, y), b"hello agent guard", (r, s)))
