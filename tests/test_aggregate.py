import pytest

from subnetcalc import core


def test_summarize_adjacent_networks():
    result = core.summarize(["192.168.0.0/25", "192.168.0.128/25"])
    assert [str(n) for n in result] == ["192.168.0.0/24"]


def test_summarize_mixed_addresses_and_networks():
    result = core.summarize(["10.0.0.0/24", "10.0.1.0/24", "10.0.2.5"])
    strs = [str(n) for n in result]
    assert "10.0.0.0/23" in strs
    assert "10.0.2.5/32" in strs


def test_summarize_non_contiguous():
    result = core.summarize(["10.0.0.0/24", "10.0.2.0/24"])
    assert [str(n) for n in result] == ["10.0.0.0/24", "10.0.2.0/24"]


def test_summarize_single_address():
    result = core.summarize(["192.168.1.1"])
    assert [str(n) for n in result] == ["192.168.1.1/32"]


def test_summarize_mixed_families():
    result = core.summarize(["10.0.0.0/24", "2001:db8::/33", "2001:db8:8000::/33"])
    strs = [str(n) for n in result]
    assert "10.0.0.0/24" in strs
    assert "2001:db8::/32" in strs


def test_summarize_ipv6():
    result = core.summarize(["2001:db8::/33", "2001:db8:8000::/33"])
    assert [str(n) for n in result] == ["2001:db8::/32"]


def test_range_to_cidrs_basic():
    result = core.range_to_cidrs("192.168.0.0", "192.168.0.255")
    assert [str(n) for n in result] == ["192.168.0.0/24"]


def test_range_to_cidrs_unaligned():
    result = core.range_to_cidrs("192.168.0.1", "192.168.0.10")
    strs = [str(n) for n in result]
    # Covers exactly .1 - .10
    covered = sum(n.num_addresses for n in result)
    assert covered == 10
    assert "192.168.0.8/31" in strs


def test_range_to_cidrs_ipv6():
    result = core.range_to_cidrs("2001:db8::", "2001:db8::ff")
    assert [str(n) for n in result] == ["2001:db8::/120"]


def test_range_to_cidrs_start_after_end_raises():
    with pytest.raises(ValueError):
        core.range_to_cidrs("192.168.0.10", "192.168.0.1")


def test_range_to_cidrs_version_mismatch_raises():
    with pytest.raises(ValueError):
        core.range_to_cidrs("192.168.0.1", "2001:db8::1")
