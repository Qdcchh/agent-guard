"""Prototype share calculation: semi-honest, scalar multiplication not constant time.

Final signatures are always verified with Tongsuo. Python cannot guarantee secret erasure.
"""

import secrets

from agent_guard.cosign.curve import DEFAULT_ID, GX, GY, INF, A, B, G, N, add, mul, neg, on_curve
from agent_guard.cosign.encoding import public_point_to_spki, signature_rs_to_der
from agent_guard.crypto.sm import load_sm2_public_key, sm3_digest, verify_sm2_message


def scalar(value):
    if type(value) is not int or not 1 <= value < N:
        raise ValueError("invalid scalar")
    return value


def validated_point(point):
    if not on_curve(point):
        raise ValueError("invalid point")
    return point


def require_message(message):
    if type(message) is not bytes:
        raise TypeError("message must be bytes")


def i2b(v: int) -> bytes:
    return v.to_bytes(32, "big")


def za(pub, uid: bytes = DEFAULT_ID) -> bytes:
    validated_point(pub)
    entl = (len(uid) * 8).to_bytes(2, "big")
    return sm3_digest(entl + uid + i2b(A) + i2b(B) + i2b(GX) + i2b(GY) + i2b(pub[0]) + i2b(pub[1]))


def compute_e(public_point, message: bytes) -> int:
    require_message(message)
    return int.from_bytes(sm3_digest(za(public_point) + message), "big")


def rand_scalar() -> int:
    return secrets.randbelow(N - 1) + 1


class ExecParty:
    """执行域（发起方 / 输出最终签名）。"""

    def __init__(self, share=None, public=None):
        self.d1 = rand_scalar() if share is None else scalar(share)
        self.pub = None if public is None else validated_point(public)
        self._k1 = None

    def keygen_msg(self):
        return mul(pow(scalar(self.d1), -1, N), G)

    def set_public(self, pub):
        if not on_curve(pub):
            raise ValueError("bad public key")
        self.pub = pub

    def sign_round1(self):
        if self._k1 is not None:
            raise RuntimeError("session already open")
        self._k1 = rand_scalar()
        return mul(self._k1, G)

    def sign_round3(self, msg: bytes, r: int, s2: int, s3: int):
        k1, self._k1 = self._k1, None  # 一次性：无论成败都销毁
        if k1 is None:
            raise RuntimeError("no open session")
        if not all(type(v) is int and 1 <= v < N for v in (r, s2, s3)):
            raise ValueError("bad partial values")
        require_message(msg)
        scalar(self.d1)
        s = (self.d1 * k1 * s2 + self.d1 * s3 - r) % N
        if s == 0 or s == N - r:
            raise ValueError("degenerate s, retry")
        verify_sm2_message(
            load_sm2_public_key(public_point_to_spki(self.pub)),
            msg,
            signature_rs_to_der(i2b(r) + i2b(s)),
        )
        return r, s


class AuthzParty:
    """授权域（响应方，无跨轮状态）。"""

    def __init__(self, share=None, public=None):
        self.d2 = rand_scalar() if share is None else scalar(share)
        self.pub = None if public is None else validated_point(public)

    def keygen_finish(self, t1):
        if not on_curve(t1):
            raise ValueError("bad T1")
        pub = add(mul(pow(scalar(self.d2), -1, N), t1), neg(G))
        if pub is INF:
            raise ValueError("degenerate key, regenerate")
        self.pub = pub
        return pub

    def sign_round2(self, msg: bytes, q1):
        if not on_curve(q1):
            raise ValueError("bad Q1")
        scalar(self.d2)
        e = compute_e(self.pub, msg)
        while True:
            k2, k3 = rand_scalar(), rand_scalar()
            pt = add(mul(k3, q1), mul(k2, G))
            if pt is INF:
                continue
            r = (e + pt[0]) % N
            if r == 0:
                continue
            s2 = self.d2 * k3 % N
            s3 = self.d2 * (r + k2) % N
            return r, s2, s3

    def set_public(self, pub):
        self.pub = validated_point(pub)
