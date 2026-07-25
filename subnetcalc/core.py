"""Pure network calculation helpers.

Everything in here is I/O free: functions take strings or ``ipaddress``
objects and return plain Python data structures.  This keeps the logic
easy to unit test and reusable from the CLI or other code.
"""

import ipaddress

__all__ = [
    "parse_network",
    "parse_address",
    "network_info",
    "split_network",
    "contains",
    "overlaps",
    "summarize",
    "range_to_cidrs",
]


def parse_network(value, strict=False):
    """Return an IPv4Network/IPv6Network from ``value``.

    ``strict`` mirrors :func:`ipaddress.ip_network`; with ``strict=False``
    host bits are allowed and masked off.
    """
    return ipaddress.ip_network(str(value), strict=strict)


def parse_address(value):
    """Return an IPv4Address/IPv6Address from ``value``."""
    return ipaddress.ip_address(str(value))


def network_info(cidr, strict=False):
    """Return a dict describing ``cidr``.

    Works for both IPv4 and IPv6.  ``num_addresses`` counts every address in
    the block, while ``num_usable`` counts only the assignable ones and always
    matches the ``first_host``..``last_host`` range -- see :func:`_usable_count`
    for the per-family rules and their point-to-point exceptions.
    """
    net = parse_network(cidr, strict=strict)

    if net.num_addresses <= 2:
        host_list = list(net.hosts())
        first_host = host_list[0] if host_list else None
        last_host = host_list[-1] if host_list else None
    else:
        first_host = next(net.hosts(), None)
        if net.version == 4:
            last_host = net.broadcast_address - 1
        else:
            last_host = net.broadcast_address

    return {
        "cidr": str(net),
        "version": net.version,
        "network_address": str(net.network_address),
        "broadcast_address": str(net.broadcast_address),
        "netmask": str(net.netmask),
        "hostmask": str(net.hostmask),
        "prefixlen": net.prefixlen,
        "num_addresses": net.num_addresses,
        "num_usable": _usable_count(net),
        "first_host": str(first_host) if first_host is not None else None,
        "last_host": str(last_host) if last_host is not None else None,
        "is_private": net.is_private,
        "is_global": net.is_global,
        "is_multicast": net.is_multicast,
        "is_reserved": net.is_reserved,
        "is_loopback": net.is_loopback,
        "is_link_local": net.is_link_local,
    }


def _usable_count(net):
    """Number of assignable host addresses in ``net``.

    Mirrors ``ipaddress``' own ``hosts()`` semantics, so the count always
    agrees with the ``first_host``..``last_host`` range reported next to it.
    """
    total = net.num_addresses
    if net.prefixlen == net.max_prefixlen:
        # A single address (/32 or /128): the address itself.
        return 1
    if net.prefixlen == net.max_prefixlen - 1:
        # Point-to-point links: IPv4 /31 (RFC 3021) and IPv6 /127 (RFC 6164)
        # have no network or broadcast address, so both addresses are usable.
        return 2
    if net.version == 4:
        # The network and broadcast addresses are not assignable to hosts.
        return total - 2
    # IPv6 has no broadcast address, but the all-zeros interface identifier is
    # reserved as the Subnet-Router anycast address (RFC 4291 s2.6.1), which is
    # why ``IPv6Network.hosts()`` -- and ``first_host`` above -- skip it.
    return total - 1


def split_network(cidr, new_prefix=None, count=None, strict=False):
    """Subdivide ``cidr``.

    Provide exactly one of ``new_prefix`` (target prefix length) or ``count``
    (number of equal subnets, which must be a power of two).  Returns a list
    of network objects.
    """
    net = parse_network(cidr, strict=strict)
    if (new_prefix is None) == (count is None):
        raise ValueError("provide exactly one of new_prefix or count")

    if count is not None:
        if count < 1:
            raise ValueError("count must be >= 1")
        if count & (count - 1) != 0:
            raise ValueError("count must be a power of two")
        bits = count.bit_length() - 1
        new_prefix = net.prefixlen + bits

    if new_prefix < net.prefixlen:
        raise ValueError(
            "new prefix %d is shorter than network prefix %d"
            % (new_prefix, net.prefixlen)
        )
    if new_prefix > net.max_prefixlen:
        raise ValueError(
            "new prefix %d exceeds max %d" % (new_prefix, net.max_prefixlen)
        )

    return list(net.subnets(new_prefix=new_prefix))


def contains(cidr, addr, strict=False):
    """Return True if ``addr`` (address or network) lies within ``cidr``."""
    net = parse_network(cidr, strict=strict)
    try:
        other = parse_address(addr)
    except ValueError:
        # ``strict`` has to be honoured here too, otherwise host bits are
        # rejected in ``cidr`` but silently accepted in ``addr``.
        other = parse_network(addr, strict=strict)
        if other.version != net.version:
            return False
        return other.subnet_of(net)
    if other.version != net.version:
        return False
    return other in net


def overlaps(cidr_a, cidr_b, strict=False):
    """Return True if the two networks share any address."""
    a = parse_network(cidr_a, strict=strict)
    b = parse_network(cidr_b, strict=strict)
    if a.version != b.version:
        return False
    return a.overlaps(b)


def summarize(items, strict=False):
    """Collapse ``items`` (addresses and/or networks) into a minimal set.

    Returns a list of network objects.  IPv4 and IPv6 inputs may be mixed;
    ``ipaddress.collapse_addresses`` is applied per family and the results
    are concatenated (IPv4 first).
    """
    v4 = []
    v6 = []
    for item in items:
        net = _coerce_network(item, strict=strict)
        (v4 if net.version == 4 else v6).append(net)
    result = []
    if v4:
        result.extend(ipaddress.collapse_addresses(v4))
    if v6:
        result.extend(ipaddress.collapse_addresses(v6))
    return result


def _coerce_network(item, strict=False):
    """Turn an address or CIDR string into a network object."""
    text = str(item)
    if "/" in text:
        # An explicit prefix means the caller meant a network: parse it as one
        # so ``strict`` applies and a host-bits error is reported as such
        # instead of being masked by a misleading "not an address" failure.
        return parse_network(text, strict=strict)
    addr = parse_address(text)
    suffix = "/32" if addr.version == 4 else "/128"
    return ipaddress.ip_network(str(addr) + suffix)


def range_to_cidrs(start, end):
    """Smallest CIDR set covering the inclusive range ``start``..``end``."""
    first = parse_address(start)
    last = parse_address(end)
    if first.version != last.version:
        raise ValueError("start and end must be the same IP version")
    if int(first) > int(last):
        raise ValueError("start address is greater than end address")
    return list(ipaddress.summarize_address_range(first, last))
