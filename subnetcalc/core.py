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
    the block, while ``num_usable`` applies the classic "minus network and
    broadcast" rule for IPv4 (with the /31 and /32 special cases).
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
    }


def _usable_count(net):
    """Number of assignable host addresses in ``net``."""
    total = net.num_addresses
    if net.version == 4:
        if net.prefixlen == 32:
            return 1
        if net.prefixlen == 31:
            # RFC 3021 point-to-point: both addresses are usable.
            return 2
        return max(total - 2, 0)
    if net.prefixlen == 128:
        return 1
    return total


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
