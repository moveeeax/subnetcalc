"""Differential tests: check ``subnetcalc.core`` against ``ipaddress``.

The standard library is the reference implementation here.  Rather than
restating the expected answers by hand (which just re-encodes whatever the
code already does), every test below either recomputes the answer straight
from ``ipaddress`` or asserts a structural invariant that must hold for any
correct subnet calculator.

Inputs are generated with a fixed seed, so failures are reproducible.
"""

import ipaddress
import random

import pytest

from subnetcalc import core

SEED = 20240517
SAMPLES_PER_PREFIX = 4

V4_PREFIXES = list(range(0, 33))
V6_PREFIXES = list(range(0, 129))


def _sample_networks(version, prefixlen, count, seed_extra=0):
    """Deterministic sample of networks with the given prefix length."""
    rnd = random.Random((SEED, version, prefixlen, seed_extra).__hash__())
    cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    bits = 32 if version == 4 else 128
    nets = []
    for _ in range(count):
        addr = cls(rnd.randrange(0, 2 ** bits))
        nets.append(ipaddress.ip_network("%s/%d" % (addr, prefixlen), strict=False))
    return nets


# --------------------------------------------------------------------------
# network_info
# --------------------------------------------------------------------------


@pytest.mark.parametrize("version,prefixlen", (
    [(4, p) for p in V4_PREFIXES] + [(6, p) for p in V6_PREFIXES]
))
def test_info_fields_match_ipaddress(version, prefixlen):
    """Every reported field is recomputed independently from ``ipaddress``."""
    for net in _sample_networks(version, prefixlen, SAMPLES_PER_PREFIX):
        info = core.network_info(str(net))
        assert info["cidr"] == str(net)
        assert info["version"] == net.version
        assert info["network_address"] == str(net.network_address)
        assert info["broadcast_address"] == str(net.broadcast_address)
        assert info["netmask"] == str(net.netmask)
        assert info["hostmask"] == str(net.hostmask)
        assert info["prefixlen"] == net.prefixlen
        assert info["num_addresses"] == net.num_addresses
        assert info["num_addresses"] == 2 ** (net.max_prefixlen - prefixlen)
        assert info["is_private"] == net.is_private
        assert info["is_global"] == net.is_global
        assert info["is_multicast"] == net.is_multicast
        assert info["is_reserved"] == net.is_reserved
        assert info["is_loopback"] == net.is_loopback
        assert info["is_link_local"] == net.is_link_local


@pytest.mark.parametrize("version,prefixlen", (
    [(4, p) for p in V4_PREFIXES] + [(6, p) for p in V6_PREFIXES]
))
def test_usable_count_matches_reported_host_range(version, prefixlen):
    """``num_usable`` must equal the size of the ``first_host``..``last_host``
    range printed next to it.  Reporting a count that disagrees with the range
    is the classic subnet-calculator bug, and it is unverifiable by eye for
    large IPv6 blocks."""
    for net in _sample_networks(version, prefixlen, SAMPLES_PER_PREFIX):
        info = core.network_info(str(net))
        first = ipaddress.ip_address(info["first_host"])
        last = ipaddress.ip_address(info["last_host"])
        assert int(first) <= int(last)
        assert int(last) - int(first) + 1 == info["num_usable"]
        # The usable range must stay inside the block.
        assert first in net and last in net


@pytest.mark.parametrize("cidr", [
    # Small enough to enumerate hosts() exhaustively.
    "10.0.0.0/24", "10.0.0.0/25", "10.0.0.0/28", "10.0.0.0/29",
    "10.0.0.0/30", "10.0.0.0/31", "10.0.0.5/32", "203.0.113.0/26",
    "2001:db8::/118", "2001:db8::/120", "2001:db8::/123", "2001:db8::/125",
    "2001:db8::/126", "2001:db8::/127", "2001:db8::1/128",
])
def test_usable_count_matches_stdlib_hosts(cidr):
    """For blocks small enough to enumerate, compare against ``hosts()``."""
    net = ipaddress.ip_network(cidr, strict=False)
    hosts = list(net.hosts())
    info = core.network_info(cidr)
    assert info["num_usable"] == len(hosts)
    assert info["first_host"] == str(hosts[0])
    assert info["last_host"] == str(hosts[-1])


@pytest.mark.parametrize("cidr,expected", [
    # RFC 3021: an IPv4 /31 has no network or broadcast address.
    ("10.0.0.0/31", 2),
    ("10.0.0.5/32", 1),
    ("10.0.0.0/30", 2),
    ("0.0.0.0/0", 2 ** 32 - 2),
    # RFC 6164: an IPv6 /127 point-to-point link, both addresses usable.
    ("2001:db8::/127", 2),
    ("2001:db8::1/128", 1),
    # RFC 4291 s2.6.1: the all-zeros interface ID is the Subnet-Router
    # anycast address, so it is not assignable to a host.
    ("2001:db8::/64", 2 ** 64 - 1),
    ("2001:db8::/126", 3),
    ("::/0", 2 ** 128 - 1),
])
def test_usable_count_special_prefixes(cidr, expected):
    assert core.network_info(cidr)["num_usable"] == expected


def test_host_bits_are_masked_or_rejected_consistently():
    """Host bits are silently masked by default and rejected under ``strict``
    by *every* entry point, in *every* argument position."""
    dirty = "10.1.2.3/24"
    assert core.network_info(dirty)["network_address"] == "10.1.2.0"
    assert core.split_network(dirty, count=1)[0].network_address == \
        ipaddress.IPv4Address("10.1.2.0")
    assert core.contains(dirty, "10.1.2.9") is True
    assert core.contains("10.0.0.0/8", dirty) is True
    assert core.overlaps(dirty, "10.1.2.0/25") is True
    assert [str(n) for n in core.summarize([dirty])] == ["10.1.2.0/24"]

    strict_calls = [
        lambda: core.network_info(dirty, strict=True),
        lambda: core.split_network(dirty, new_prefix=26, strict=True),
        lambda: core.contains(dirty, "10.1.2.9", strict=True),
        # Second argument: a network with host bits must be rejected too.
        lambda: core.contains("10.0.0.0/8", dirty, strict=True),
        lambda: core.overlaps(dirty, "10.0.0.0/8", strict=True),
        lambda: core.overlaps("10.0.0.0/8", dirty, strict=True),
        lambda: core.summarize([dirty], strict=True),
    ]
    for call in strict_calls:
        with pytest.raises(ValueError, match="host bits"):
            call()

    # A bare address never has host bits and stays acceptable under strict.
    assert [str(n) for n in core.summarize(["10.1.2.3"], strict=True)] == \
        ["10.1.2.3/32"]


# --------------------------------------------------------------------------
# split_network
# --------------------------------------------------------------------------


@pytest.mark.parametrize("cidr,new_prefix", [
    ("10.0.0.0/22", np) for np in range(22, 29)
] + [
    ("192.168.1.0/24", np) for np in range(24, 33)
] + [
    ("2001:db8::/60", np) for np in range(60, 67)
] + [
    ("2001:db8::/126", np) for np in range(126, 129)
])
def test_split_tiles_parent_exactly(cidr, new_prefix):
    """Subnets must partition the parent: right count, right size, in order,
    no gaps and no overlaps, covering exactly the parent's address space."""
    parent = ipaddress.ip_network(cidr)
    subs = core.split_network(cidr, new_prefix=new_prefix)

    assert len(subs) == 2 ** (new_prefix - parent.prefixlen)
    assert all(s.prefixlen == new_prefix for s in subs)
    assert all(s.subnet_of(parent) for s in subs)
    assert sum(s.num_addresses for s in subs) == parent.num_addresses
    assert subs[0].network_address == parent.network_address
    assert subs[-1].broadcast_address == parent.broadcast_address
    for prev, nxt in zip(subs, subs[1:]):
        assert int(nxt.network_address) == int(prev.broadcast_address) + 1


@pytest.mark.parametrize("cidr,count", [
    ("10.0.0.0/16", 1), ("10.0.0.0/16", 2), ("10.0.0.0/16", 8),
    ("10.0.0.0/16", 256), ("2001:db8::/48", 16),
])
def test_split_by_count_equals_split_by_prefix(cidr, count):
    parent = ipaddress.ip_network(cidr)
    by_count = core.split_network(cidr, count=count)
    by_prefix = core.split_network(
        cidr, new_prefix=parent.prefixlen + (count.bit_length() - 1)
    )
    assert by_count == by_prefix
    assert len(by_count) == count


@pytest.mark.parametrize("version,prefixlen", (
    [(4, p) for p in V4_PREFIXES] + [(6, p) for p in V6_PREFIXES]
))
def test_split_rejects_out_of_range_prefixes(version, prefixlen):
    net = _sample_networks(version, prefixlen, 1)[0]
    max_prefixlen = net.max_prefixlen
    if prefixlen > 0:
        with pytest.raises(ValueError):
            core.split_network(str(net), new_prefix=prefixlen - 1)
    with pytest.raises(ValueError):
        core.split_network(str(net), new_prefix=max_prefixlen + 1)
    # Splitting to its own prefix is a no-op, never an error.
    assert core.split_network(str(net), new_prefix=prefixlen) == [net]


# --------------------------------------------------------------------------
# contains / overlaps
# --------------------------------------------------------------------------


@pytest.mark.parametrize("version,prefixlen", (
    [(4, p) for p in V4_PREFIXES] + [(6, p) for p in V6_PREFIXES]
))
def test_contains_address_matches_membership_operator(version, prefixlen):
    cls = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
    bits = 32 if version == 4 else 128
    rnd = random.Random((SEED, "contains", version, prefixlen).__hash__())
    for net in _sample_networks(version, prefixlen, SAMPLES_PER_PREFIX):
        probes = [
            net.network_address,
            net.broadcast_address,
            cls(rnd.randrange(0, 2 ** bits)),
        ]
        if int(net.network_address) > 0:
            probes.append(cls(int(net.network_address) - 1))
        if int(net.broadcast_address) < 2 ** bits - 1:
            probes.append(cls(int(net.broadcast_address) + 1))
        for probe in probes:
            assert core.contains(str(net), str(probe)) is (probe in net)


@pytest.mark.parametrize("version,prefixlen", (
    [(4, p) for p in V4_PREFIXES] + [(6, p) for p in V6_PREFIXES]
))
def test_contains_network_matches_subnet_of(version, prefixlen):
    for net in _sample_networks(version, prefixlen, SAMPLES_PER_PREFIX):
        for other in _sample_networks(version, prefixlen, 3, seed_extra=7):
            assert core.contains(str(net), str(other)) is other.subnet_of(net)
        # A block always contains itself and its own halves.
        assert core.contains(str(net), str(net)) is True
        if prefixlen < net.max_prefixlen:
            for half in net.subnets(prefixlen_diff=1):
                assert core.contains(str(net), str(half)) is True
                assert core.contains(str(half), str(net)) is (half == net)


@pytest.mark.parametrize("version,prefixlen", (
    [(4, p) for p in V4_PREFIXES] + [(6, p) for p in V6_PREFIXES]
))
def test_overlaps_matches_ipaddress_and_is_symmetric(version, prefixlen):
    a_nets = _sample_networks(version, prefixlen, SAMPLES_PER_PREFIX)
    b_nets = _sample_networks(version, prefixlen, SAMPLES_PER_PREFIX, seed_extra=3)
    for a in a_nets:
        for b in b_nets:
            expected = a.overlaps(b)
            assert core.overlaps(str(a), str(b)) is expected
            assert core.overlaps(str(b), str(a)) is expected


@pytest.mark.parametrize("v4,v6", [
    ("10.0.0.0/8", "2001:db8::/32"),
    ("0.0.0.0/0", "::/0"),
])
def test_cross_family_never_matches(v4, v6):
    """A v4 block and a v6 block can never contain or overlap each other,
    even when both are the whole address space."""
    assert core.contains(v4, v6) is False
    assert core.contains(v6, v4) is False
    assert core.overlaps(v4, v6) is False
    assert core.overlaps(v6, v4) is False


# --------------------------------------------------------------------------
# summarize / range_to_cidrs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("trial", range(40))
def test_summarize_preserves_exact_address_set(trial):
    """The collapsed result must cover exactly the input addresses -- no more
    (over-aggregation would hand out addresses the caller never listed) and no
    less -- and must itself be minimal and non-overlapping."""
    rnd = random.Random((SEED, "summarize", trial).__hash__())
    items, expected = [], set()
    for _ in range(rnd.randrange(1, 6)):
        prefixlen = rnd.choice([26, 27, 28, 29, 30, 31, 32])
        addr = ipaddress.IPv4Address(0x0A000000 + rnd.randrange(0, 1024))
        net = ipaddress.ip_network("%s/%d" % (addr, prefixlen), strict=False)
        items.append(str(net))
        expected.update(int(a) for a in net)

    result = core.summarize(items)
    got = set()
    for net in result:
        got.update(int(a) for a in net)
    assert got == expected

    for i, a in enumerate(result):
        for b in result[i + 1:]:
            assert not a.overlaps(b)
    assert list(result) == sorted(result)
    assert list(result) == list(ipaddress.collapse_addresses(result))


def test_summarize_keeps_families_separate_and_ordered():
    items = ["2001:db8::/33", "10.0.0.0/25", "2001:db8:8000::/33", "10.0.0.128/25"]
    result = [str(n) for n in core.summarize(items)]
    assert result == ["10.0.0.0/24", "2001:db8::/32"]


@pytest.mark.parametrize("trial", range(40))
def test_range_to_cidrs_covers_range_exactly(trial):
    """The CIDR set must start at ``start``, end at ``end``, be contiguous,
    and cover exactly ``end - start + 1`` addresses."""
    rnd = random.Random((SEED, "range", trial).__hash__())
    start_int = rnd.randrange(0, 2 ** 32 - 1)
    end_int = min(start_int + rnd.randrange(0, 5000), 2 ** 32 - 1)
    start = ipaddress.IPv4Address(start_int)
    end = ipaddress.IPv4Address(end_int)

    nets = core.range_to_cidrs(str(start), str(end))
    assert nets == list(ipaddress.summarize_address_range(start, end))
    assert nets[0].network_address == start
    assert nets[-1].broadcast_address == end
    assert sum(n.num_addresses for n in nets) == end_int - start_int + 1
    for prev, nxt in zip(nets, nets[1:]):
        assert int(nxt.network_address) == int(prev.broadcast_address) + 1


@pytest.mark.parametrize("start,end", [
    ("::", "::ff"),
    ("2001:db8::1", "2001:db8::1"),
    ("2001:db8::1", "2001:db8::a"),
    ("::", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"),
])
def test_range_to_cidrs_ipv6_covers_range_exactly(start, end):
    first, last = ipaddress.ip_address(start), ipaddress.ip_address(end)
    nets = core.range_to_cidrs(start, end)
    assert nets[0].network_address == first
    assert nets[-1].broadcast_address == last
    assert sum(n.num_addresses for n in nets) == int(last) - int(first) + 1
