import pytest

from subnetcalc import core


def test_split_by_prefix():
    subnets = core.split_network("192.168.0.0/24", new_prefix=26)
    assert [str(s) for s in subnets] == [
        "192.168.0.0/26",
        "192.168.0.64/26",
        "192.168.0.128/26",
        "192.168.0.192/26",
    ]


def test_split_by_count():
    subnets = core.split_network("10.0.0.0/24", count=4)
    assert len(subnets) == 4
    assert str(subnets[0]) == "10.0.0.0/26"
    assert str(subnets[-1]) == "10.0.0.192/26"


def test_split_count_one_returns_self():
    subnets = core.split_network("10.0.0.0/24", count=1)
    assert [str(s) for s in subnets] == ["10.0.0.0/24"]


def test_split_count_must_be_power_of_two():
    with pytest.raises(ValueError):
        core.split_network("10.0.0.0/24", count=3)


def test_split_requires_exactly_one_selector():
    with pytest.raises(ValueError):
        core.split_network("10.0.0.0/24")
    with pytest.raises(ValueError):
        core.split_network("10.0.0.0/24", new_prefix=26, count=4)


def test_split_prefix_shorter_than_network_raises():
    with pytest.raises(ValueError):
        core.split_network("10.0.0.0/24", new_prefix=20)


def test_split_prefix_exceeds_max_raises():
    with pytest.raises(ValueError):
        core.split_network("10.0.0.0/24", new_prefix=33)


def test_split_ipv6_by_prefix():
    subnets = core.split_network("2001:db8::/48", new_prefix=50)
    assert len(subnets) == 4
    assert str(subnets[0]) == "2001:db8::/50"


def test_split_slash_31():
    subnets = core.split_network("10.0.0.0/30", new_prefix=31)
    assert [str(s) for s in subnets] == ["10.0.0.0/31", "10.0.0.2/31"]


def test_split_below_limit_succeeds():
    # 2**19 subnets, comfortably under the 1,000,000 cap.
    subnets = core.split_network("10.0.0.0/1", new_prefix=20)
    assert len(subnets) == 2 ** 19


def test_split_over_limit_raises():
    # 2**24 subnets from a single /8 -> /32 split would otherwise hang the
    # process trying to materialize 16.7M network objects.
    with pytest.raises(ValueError, match="exceeds the limit"):
        core.split_network("10.0.0.0/8", new_prefix=32)


def test_split_count_over_limit_raises():
    with pytest.raises(ValueError, match="exceeds the limit"):
        core.split_network("10.0.0.0/8", count=2 ** 24)


def test_split_ipv6_massive_over_limit_raises():
    # Without a guard this would try to allocate up to 2**128 subnets.
    with pytest.raises(ValueError, match="exceeds the limit"):
        core.split_network("::/0", new_prefix=128)
