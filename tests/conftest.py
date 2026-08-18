"""Repository-wide guard against accidental non-loopback test egress."""

from __future__ import annotations

import ipaddress
import socket

import pytest


def _loopback_address(address: object) -> bool:
    if not isinstance(address, tuple) or not address:
        # Local-domain and platform-specific non-IP transports are not remote
        # network egress and remain governed by their own adapters.
        return True
    host = address[0]
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            return False
    if not isinstance(host, str):
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # Reject names before they can trigger external DNS resolution.
        return False


@pytest.fixture(autouse=True)
def deny_non_loopback_tcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail, rather than skip, any IPv4/IPv6 non-loopback test connection."""

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_sendto = socket.socket.sendto

    def guarded_connect(instance: socket.socket, address: object) -> None:
        if instance.family in {socket.AF_INET, socket.AF_INET6} and not _loopback_address(address):
            raise AssertionError("non_loopback_socket_forbidden")
        original_connect(instance, address)

    def guarded_connect_ex(instance: socket.socket, address: object) -> int:
        if instance.family in {socket.AF_INET, socket.AF_INET6} and not _loopback_address(address):
            raise AssertionError("non_loopback_socket_forbidden")
        return original_connect_ex(instance, address)

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object):
        if host is not None and not _loopback_address((host, 0)):
            raise AssertionError("non_loopback_socket_forbidden")
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_sendto(instance: socket.socket, data: bytes, *args: object) -> int:
        address = args[-1] if args else None
        if instance.family in {socket.AF_INET, socket.AF_INET6} and not _loopback_address(address):
            raise AssertionError("non_loopback_socket_forbidden")
        return original_sendto(instance, data, *args)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
