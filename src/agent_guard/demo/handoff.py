"""Linux fixed-pair IPC with reciprocal kernel credentials and bounded frames."""

from __future__ import annotations

import os
import socket
import stat
import struct

from agent_guard.contracts.encoding import canonical_json_bytes, load_strict_json
from agent_guard.demo.config import (
    ChildToken,
    DemoConfigError,
    HandoffAck,
    HandoffConfig,
)

MAX_FRAME = 65536


def _runtime(config):
    if (
        type(config) is not HandoffConfig
        or not hasattr(socket, "SO_PEERCRED")
        or os.getuid() != config.self_uid
    ):
        raise DemoConfigError("Linux exact role UID required")
    parent = config.socket_path.parent
    info = parent.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != config.receiver_uid
        or info.st_gid != config.pair_gid
        or stat.S_IMODE(info.st_mode) != 0o710
        or parent.is_symlink()
    ):
        raise DemoConfigError("exact pair directory required")
    if config.pair_gid not in (*os.getgroups(), os.getgid()):
        raise DemoConfigError("exact pair group required")
    for p in parent.parents:
        if p.is_symlink():
            raise DemoConfigError("socket parent alias forbidden")


def _peer(sock, config):
    _, uid, _ = struct.unpack(
        "3i",
        sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")),
    )
    if uid != config.peer_uid:
        raise DemoConfigError("handoff peer UID rejected")


def _read(sock, count):
    parts = bytearray()
    while len(parts) < count:
        chunk = sock.recv(count - len(parts))
        if not chunk:
            raise DemoConfigError("incomplete handoff frame")
        parts.extend(chunk)
    return bytes(parts)


def _receive(sock):
    length = struct.unpack("!I", _read(sock, 4))[0]
    if not 0 < length <= MAX_FRAME:
        raise DemoConfigError("handoff capacity")
    return load_strict_json(_read(sock, length))


def _send(sock, value):
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_FRAME:
        raise DemoConfigError("handoff capacity")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def _identity(config, *, sender, target):
    return {
        "version": "demo-handoff-2",
        "run_id": config.run_id,
        "task_id": config.task_id,
        "sender": sender,
        "target": target,
    }


def send_child(config: HandoffConfig, *, target: str, token: ChildToken) -> HandoffAck:
    _runtime(config)
    if (
        config.self_uid == config.receiver_uid
        or target != config.peer_client_id
        or type(token) is not ChildToken
        or type(token.access_token) is not str
        or not token.access_token
        or not token.access_token.isascii()
        or len(token.access_token) > MAX_FRAME
        or (token.run_id, token.task_id, token.parent_client_id, token.target_client_id)
        != (config.run_id, config.task_id, config.self_client_id, target)
    ):
        raise DemoConfigError("handoff direction/target rejected")
    info = config.socket_path.lstat()
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != config.receiver_uid
        or info.st_gid != config.pair_gid
        or stat.S_IMODE(info.st_mode) != 0o660
    ):
        raise DemoConfigError("exact pair socket required")
    envelope = _identity(config, sender=config.self_client_id, target=target)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        sock.connect(str(config.socket_path))
        _peer(sock, config)
        _send(sock, {**envelope, "token": token.access_token})
        if _receive(sock) != {**envelope, "accepted": True}:
            raise DemoConfigError("invalid handoff acknowledgement")
    return HandoffAck(config.run_id, config.task_id, config.self_client_id, target)


def receive_child(config: HandoffConfig, *, expected_parent: str) -> ChildToken:
    _runtime(config)
    if config.self_uid != config.receiver_uid or expected_parent != config.peer_client_id:
        raise DemoConfigError("receiver direction rejected")
    # Never replace an existing or foreign socket. Only the receiver owns unlink.
    if config.socket_path.exists() or config.socket_path.is_symlink():
        raise DemoConfigError("handoff socket already exists")
    created = False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.settimeout(10)
            listener.bind(str(config.socket_path))
            created = True
            os.chown(config.socket_path, -1, config.pair_gid)
            os.chmod(config.socket_path, 0o660)
            listener.listen(1)
            sock, _ = listener.accept()
            with sock:
                sock.settimeout(10)
                _peer(sock, config)
                value = _receive(sock)
                envelope = _identity(config, sender=expected_parent, target=config.self_client_id)
                if (
                    type(value) is not dict
                    or set(value) != set(envelope) | {"token"}
                    or any(value[k] != v for k, v in envelope.items())
                    or type(value["token"]) is not str
                    or not value["token"]
                    or not value["token"].isascii()
                ):
                    raise DemoConfigError("handoff envelope rejected")
                _send(sock, {**envelope, "accepted": True})
                return ChildToken(
                    value["token"],
                    config.self_client_id,
                    expected_parent,
                    config.run_id,
                    config.task_id,
                )
    finally:
        if created:
            info = config.socket_path.lstat()
            if (
                stat.S_ISSOCK(info.st_mode)
                and info.st_uid == config.self_uid
                and info.st_gid == config.pair_gid
            ):
                config.socket_path.unlink()
