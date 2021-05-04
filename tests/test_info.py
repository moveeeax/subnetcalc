import ipaddress

import pytest

from subnetcalc import core


def test_info_basic_ipv4():
    info = core.network_info("192.168.1.0/24")
    assert info["version"] == 4
    assert info["network_address"] == "192.168.1.0"
    assert info["broadcast_address"] == "192.168.1.255"
    assert info["netmask"] == "255.255.255.0"
    assert info["hostmask"] == "0.0.0.255"
    assert info["prefixlen"] == 24
    assert info["num_addresses"] == 256
    assert info["num_usable"] == 254
    assert info["first_host"] == "192.168.1.1"
    assert info["last_host"] == "192.168.1.254"
    assert info["is_private"] is True
    assert info["is_global"] is False


def test_info_host_bits_masked_when_not_strict():
    info = core.network_info("192.168.1.130/24")
    assert info["network_address"] == "192.168.1.0"


def test_info_strict_rejects_host_bits():
    with pytest.raises(ValueError):
        core.network_info("192.168.1.130/24", strict=True)


def test_info_slash_31_point_to_point():
    info = core.network_info("10.0.0.0/31")
    assert info["num_addresses"] == 2
    assert info["num_usable"] == 2
    assert info["first_host"] == "10.0.0.0"
    assert info["last_host"] == "10.0.0.1"


def test_info_slash_32_single_host():
    info = core.network_info("10.0.0.5/32")
    assert info["num_addresses"] == 1
    assert info["num_usable"] == 1
    assert info["network_address"] == "10.0.0.5"
    assert info["broadcast_address"] == "10.0.0.5"
    assert info["first_host"] == "10.0.0.5"
    assert info["last_host"] == "10.0.0.5"


def test_info_slash_zero():
    info = core.network_info("0.0.0.0/0")
    assert info["num_addresses"] == 2 ** 32
    assert info["num_usable"] == 2 ** 32 - 2
    assert info["prefixlen"] == 0


def test_info_public_address_is_global():
    info = core.network_info("8.8.8.0/24")
    assert info["is_private"] is False
    assert info["is_global"] is True


def test_info_ipv6_basic():
    info = core.network_info("2001:db8::/64")
    assert info["version"] == 6
    assert info["prefixlen"] == 64
    assert info["num_addresses"] == 2 ** 64
    assert info["network_address"] == "2001:db8::"
    assert info["is_private"] is True


def test_info_ipv6_slash_128():
    info = core.network_info("2001:db8::1/128")
    assert info["num_addresses"] == 1
    assert info["num_usable"] == 1
    assert info["first_host"] == "2001:db8::1"


def test_info_invalid_raises():
    with pytest.raises(ValueError):
        core.network_info("not-a-network")


def test_info_loopback_flag():
    info = core.network_info("127.0.0.1/32")
    assert info["is_loopback"] is True


def test_info_link_local_flag():
    info = core.network_info("169.254.0.0/16")
    assert info["is_link_local"] is True


def test_info_multicast_flag():
    info = core.network_info("224.0.0.0/4")
    assert info["is_multicast"] is True


def test_parse_address_roundtrip():
    addr = core.parse_address("10.1.2.3")
    assert isinstance(addr, ipaddress.IPv4Address)
    assert str(addr) == "10.1.2.3"
