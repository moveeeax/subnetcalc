from subnetcalc import core


def test_contains_address_true():
    assert core.contains("192.168.1.0/24", "192.168.1.42") is True


def test_contains_address_false():
    assert core.contains("192.168.1.0/24", "192.168.2.42") is False


def test_contains_network_true():
    assert core.contains("10.0.0.0/8", "10.1.2.0/24") is True


def test_contains_network_false():
    assert core.contains("10.0.0.0/16", "10.1.0.0/24") is False


def test_contains_boundary_addresses():
    assert core.contains("192.168.1.0/24", "192.168.1.0") is True
    assert core.contains("192.168.1.0/24", "192.168.1.255") is True


def test_contains_version_mismatch_false():
    assert core.contains("192.168.1.0/24", "2001:db8::1") is False


def test_contains_ipv6():
    assert core.contains("2001:db8::/32", "2001:db8:1::1") is True
    assert core.contains("2001:db8::/32", "2001:dead::1") is False


def test_overlaps_true():
    assert core.overlaps("10.0.0.0/16", "10.0.1.0/24") is True


def test_overlaps_false():
    assert core.overlaps("10.0.0.0/24", "10.0.1.0/24") is False


def test_overlaps_identical():
    assert core.overlaps("10.0.0.0/24", "10.0.0.0/24") is True


def test_overlaps_version_mismatch_false():
    assert core.overlaps("10.0.0.0/24", "2001:db8::/32") is False


def test_overlaps_ipv6():
    assert core.overlaps("2001:db8::/32", "2001:db8:abcd::/48") is True
