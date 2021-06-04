import pytest

from subnetcalc import core


def test_ipv6_slash_zero():
    info = core.network_info("::/0")
    assert info["prefixlen"] == 0
    assert info["num_addresses"] == 2 ** 128


def test_split_ipv6_to_max_prefix():
    subnets = core.split_network("2001:db8::/126", new_prefix=128)
    assert len(subnets) == 4
    assert str(subnets[0]) == "2001:db8::/128"


def test_split_large_count_power_of_two():
    subnets = core.split_network("10.0.0.0/16", count=256)
    assert len(subnets) == 256
    assert str(subnets[0]) == "10.0.0.0/24"
    assert str(subnets[-1]) == "10.0.255.0/24"


def test_range_single_address():
    result = core.range_to_cidrs("192.168.0.7", "192.168.0.7")
    assert [str(n) for n in result] == ["192.168.0.7/32"]


def test_range_full_octet_ipv4():
    result = core.range_to_cidrs("10.0.0.0", "10.0.0.63")
    assert [str(n) for n in result] == ["10.0.0.0/26"]


def test_contains_invalid_target_raises():
    with pytest.raises(ValueError):
        core.contains("10.0.0.0/24", "not-an-ip")


def test_summarize_empty_input():
    assert core.summarize([]) == []


def test_split_count_zero_raises():
    with pytest.raises(ValueError):
        core.split_network("10.0.0.0/24", count=0)


def test_overlaps_subnet_and_supernet():
    assert core.overlaps("10.0.0.0/24", "10.0.0.0/25") is True
