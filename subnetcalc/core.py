"""Pure network calculation helpers.

Everything in here is I/O free: functions take strings or ``ipaddress``
objects and return plain Python data structures.  This keeps the logic
easy to unit test and reusable from the CLI or other code.
"""

import ipaddress
import re

__all__ = [
    "parse_network",
    "parse_address",
    "network_info",
    "split_network",
    "contains",
    "overlaps",
    "summarize",
    "range_to_cidrs",
    "free_space",
    "next_free",
    "prefix_for_hosts",
    "parse_plan_spec",
    "plan_subnets",
]

# Upper bound on how many subnets a single split() call will materialize.
# Without this, a request like ``split_network("10.0.0.0/8", new_prefix=32)``
# builds a 16.7M-element list, and the IPv6 equivalent (e.g. ``::/0`` down to
# ``/128``) tries to build up to 2**128 -- both hang the process and can
# exhaust memory rather than failing fast with a useful error.
MAX_SPLIT_SUBNETS = 1_000_000


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
    return _usable_for_prefix(net.prefixlen, net.version)


def _usable_for_prefix(prefixlen, version):
    """:func:`_usable_count` for a block of ``prefixlen`` in IP ``version``."""
    max_prefixlen = 32 if version == 4 else 128
    total = 1 << (max_prefixlen - prefixlen)
    if prefixlen == max_prefixlen:
        # A single address (/32 or /128): the address itself.
        return 1
    if prefixlen == max_prefixlen - 1:
        # Point-to-point links: IPv4 /31 (RFC 3021) and IPv6 /127 (RFC 6164)
        # have no network or broadcast address, so both addresses are usable.
        return 2
    if version == 4:
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

    subnet_count = 1 << (new_prefix - net.prefixlen)
    if subnet_count > MAX_SPLIT_SUBNETS:
        raise ValueError(
            "split would produce %d subnets, which exceeds the limit of %d; "
            "choose a longer starting prefix, a shorter new prefix, or a "
            "smaller count" % (subnet_count, MAX_SPLIT_SUBNETS)
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


def _occupied_ranges(net, used, strict=False):
    """Sorted, merged ``(first, last)`` integer ranges of ``used`` inside ``net``.

    ``used`` holds addresses and/or networks.  Entries of the other IP version
    or entirely outside ``net`` are skipped; an entry that only partly covers
    ``net`` (a larger block containing it) is clipped to ``net``.
    """
    start = int(net.network_address)
    end = int(net.broadcast_address)
    ranges = []
    for item in used:
        other = _coerce_network(item, strict=strict)
        if other.version != net.version or not other.overlaps(net):
            continue
        ranges.append(
            (
                max(start, int(other.network_address)),
                min(end, int(other.broadcast_address)),
            )
        )
    ranges.sort()
    merged = []
    for first, last in ranges:
        if merged and first <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], last))
        else:
            merged.append((first, last))
    return merged


def _free_blocks(net, used, strict=False):
    """Free space of ``net`` minus ``used`` as a minimal, sorted CIDR list."""
    addr_cls = type(net.network_address)
    free = []
    cursor = int(net.network_address)
    for first, last in _occupied_ranges(net, used, strict=strict):
        if first > cursor:
            free.extend(
                ipaddress.summarize_address_range(addr_cls(cursor), addr_cls(first - 1))
            )
        cursor = last + 1
    if cursor <= int(net.broadcast_address):
        free.extend(
            ipaddress.summarize_address_range(addr_cls(cursor), net.broadcast_address)
        )
    return free


def free_space(cidr, used, min_prefix=None, strict=False):
    """Blocks of ``cidr`` not covered by any entry of ``used``.

    ``used`` is an iterable of addresses and/or networks; entries that do not
    overlap ``cidr`` (including the other IP version) are ignored.  The result
    is the minimal set of CIDRs covering the free space, lowest address first.
    With ``min_prefix`` set, blocks smaller than ``/min_prefix`` (a longer
    prefix) are left out.
    """
    net = parse_network(cidr, strict=strict)
    if min_prefix is not None and not 0 <= min_prefix <= net.max_prefixlen:
        raise ValueError(
            "min prefix %d is outside 0..%d" % (min_prefix, net.max_prefixlen)
        )
    free = _free_blocks(net, used, strict=strict)
    if min_prefix is not None:
        free = [block for block in free if block.prefixlen <= min_prefix]
    return free


def next_free(cidr, used, prefix, strict=False):
    """Lowest free ``/prefix`` block of ``cidr``, or None if none is left.

    Free space is computed as in :func:`free_space`.  Every block of the
    minimal free set is aligned, so a free ``/prefix`` always sits at the
    start of the first free block that is at least that large.
    """
    net = parse_network(cidr, strict=strict)
    _check_prefix(net, prefix)
    return _first_fit(net, _free_blocks(net, used, strict=strict), prefix)


def _check_prefix(net, prefix):
    if prefix < net.prefixlen:
        raise ValueError(
            "prefix /%d is larger than the block %s" % (prefix, net)
        )
    if prefix > net.max_prefixlen:
        raise ValueError("prefix /%d exceeds max %d" % (prefix, net.max_prefixlen))


def _first_fit(net, free, prefix):
    for block in free:
        if block.prefixlen <= prefix:
            return ipaddress.ip_network(
                "%s/%d" % (block.network_address, prefix)
            )
    return None


def prefix_for_hosts(hosts, version):
    """Longest prefix whose block still has at least ``hosts`` usable hosts.

    Usable hosts are counted as in :func:`network_info` (``num_usable``).
    """
    if hosts < 1:
        raise ValueError("hosts must be >= 1")
    max_prefixlen = 32 if version == 4 else 128
    for prefixlen in range(max_prefixlen, -1, -1):
        if _usable_for_prefix(prefixlen, version) >= hosts:
            return prefixlen
    raise ValueError(
        "%d hosts do not fit in any IPv%d block" % (hosts, version)
    )


# Names end up as map keys in HCL, YAML and JSON output; keeping them to a
# safe character set means no output format needs quoting rules for them.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def parse_plan_spec(data):
    """Validate a plan spec (already decoded from JSON) and normalize it.

    Expected shape::

        {"supernet": "10.42.0.0/16",          # optional if given elsewhere
         "subnets": [
           {"name": "web-a", "prefix": 24, "group": "public"},
           {"name": "app-a", "hosts": 500},
           {"name": "db", "cidr": "10.42.200.0/26"}]}

    Each subnet needs a ``name`` and at least one of ``prefix``, ``hosts`` or
    ``cidr`` (a fixed allocation).  Returns ``(supernet_or_None, requests)``
    where each request is a dict with the keys ``name``, ``group``,
    ``prefix``, ``hosts`` and ``cidr`` (missing ones set to None).
    """
    if not isinstance(data, dict):
        raise ValueError("plan spec must be an object")
    unknown = set(data) - {"supernet", "subnets"}
    if unknown:
        raise ValueError("unknown plan spec keys: %s" % ", ".join(sorted(unknown)))
    supernet = data.get("supernet")
    if supernet is not None and not isinstance(supernet, str):
        raise ValueError("plan spec 'supernet' must be a string")
    subnets = data.get("subnets")
    if not isinstance(subnets, list):
        raise ValueError("plan spec 'subnets' must be a list")
    return supernet, [_parse_request(entry) for entry in subnets]


def _parse_request(entry):
    if not isinstance(entry, dict):
        raise ValueError("each plan subnet must be an object")
    unknown = set(entry) - {"name", "group", "prefix", "hosts", "cidr"}
    if unknown:
        raise ValueError(
            "unknown subnet keys: %s" % ", ".join(sorted(unknown))
        )
    name = entry.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            "subnet name %r must start with a letter or digit and contain "
            "only letters, digits, '_', '.' and '-'" % (name,)
        )
    group = entry.get("group")
    if group is not None and (not isinstance(group, str) or not _NAME_RE.match(group)):
        raise ValueError("subnet %s: invalid group %r" % (name, group))
    request = {"name": name, "group": group}
    for key in ("prefix", "hosts"):
        value = entry.get(key)
        # bool is an int subclass; "prefix": true is a typo, not /1.
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError("subnet %s: %s must be an integer" % (name, key))
        request[key] = value
    cidr = entry.get("cidr")
    if cidr is not None and not isinstance(cidr, str):
        raise ValueError("subnet %s: cidr must be a string" % name)
    request["cidr"] = cidr
    if request["prefix"] is not None and request["hosts"] is not None:
        raise ValueError("subnet %s: give prefix or hosts, not both" % name)
    if request["prefix"] is None and request["hosts"] is None and cidr is None:
        raise ValueError("subnet %s: needs prefix, hosts or cidr" % name)
    return request


def plan_subnets(supernet, requests, used=(), previous=None, strict=False):
    """Allocate named, non-overlapping subnets of ``supernet``.

    ``requests`` is a list of dicts as returned by :func:`parse_plan_spec`.
    ``used`` lists CIDRs already taken outside the plan; nothing is allocated
    on top of them.  ``previous`` maps subnet names to the CIDRs an earlier
    run gave them: those names keep their block, so adding a subnet to the
    spec never renumbers the existing ones.

    Fixed (``cidr``) and previous allocations are placed first.  The rest are
    allocated largest block first, ties in spec order, each at the lowest
    free address that fits.  Raises ValueError on a collision or when the
    supernet runs out of space.

    Returns a dict with the allocated ``subnets`` (in spec order), the
    ``free`` blocks left, and fragmentation figures; see the README.
    """
    net = parse_network(supernet, strict=strict)
    previous = dict(previous or {})
    used = list(used)
    # Fail on malformed used entries even when none of them overlap.
    for item in used:
        _coerce_network(item, strict=strict)

    seen = set()
    for request in requests:
        if request["name"] in seen:
            raise ValueError("duplicate subnet name %s" % request["name"])
        seen.add(request["name"])

    sized = []
    for request in requests:
        prefix = _requested_prefix(net, request)
        sized.append((request, prefix))

    taken = []  # (network, label) for collision messages
    results = {}

    def place(name, block, source):
        if block.version != net.version or not block.subnet_of(net):
            raise ValueError("subnet %s: %s is outside %s" % (name, block, net))
        for other, label in taken:
            if block.overlaps(other):
                raise ValueError(
                    "subnet %s: %s overlaps %s (%s)" % (name, block, other, label)
                )
        for item in used:
            other = _coerce_network(item, strict=strict)
            if other.version == block.version and other.overlaps(block):
                raise ValueError(
                    "subnet %s: %s overlaps used %s" % (name, block, other)
                )
        taken.append((block, "subnet %s" % name))
        results[name] = (block, source)

    pending = []
    for request, prefix in sized:
        name = request["name"]
        fixed = request["cidr"]
        source = "fixed"
        if fixed is None and name in previous:
            fixed = previous[name]
            source = "previous"
        if fixed is None:
            pending.append((request, prefix))
            continue
        # A stored or hand-written allocation with host bits is a typo, so
        # these are always parsed strictly.
        block = parse_network(fixed, strict=True)
        if prefix is not None and block.prefixlen != prefix:
            raise ValueError(
                "subnet %s: %s %s is a /%d but the spec asks for /%d"
                % (name, source, block, block.prefixlen, prefix)
            )
        place(name, block, source)

    # Largest first (shortest prefix); sorted() is stable, so equal sizes
    # keep spec order.
    pending.sort(key=lambda item: item[1])
    for request, prefix in pending:
        occupied = used + [block for block, _ in taken]
        block = _first_fit(net, _free_blocks(net, occupied, strict=strict), prefix)
        if block is None:
            raise ValueError(
                "subnet %s: no free /%d left in %s" % (request["name"], prefix, net)
            )
        place(request["name"], block, "allocated")

    free = _free_blocks(net, used + [block for block, _ in taken], strict=strict)
    free_addresses = sum(block.num_addresses for block in free)
    largest = min(free, key=lambda block: block.prefixlen) if free else None

    subnets = []
    for request in requests:
        block, source = results[request["name"]]
        subnets.append(
            {
                "name": request["name"],
                "group": request["group"],
                "cidr": str(block),
                "prefixlen": block.prefixlen,
                "hosts": request["hosts"],
                "num_usable": _usable_count(block),
                "source": source,
            }
        )
    return {
        "supernet": str(net),
        "subnets": subnets,
        "released": sorted(set(previous) - seen),
        "free": [str(block) for block in free],
        "free_addresses": free_addresses,
        "largest_free": str(largest) if largest is not None else None,
        "fragmentation": _fragmentation(largest, free_addresses),
    }


def _fragmentation(largest, free_addresses):
    """How far the largest free block falls short of the best possible one.

    Free space of N addresses could at best hold one block of the largest
    power of two <= N.  The result is ``1 - largest / that``: 0.0 when the
    largest free block is as big as the free space allows, 0.75 when it is a
    quarter of that size.
    """
    if not free_addresses:
        return 0.0
    ideal = 1 << (free_addresses.bit_length() - 1)
    return round(1 - largest.num_addresses / ideal, 4)


def _requested_prefix(net, request):
    """Prefix length a request asks for, or None for a size-less fixed CIDR."""
    name = request["name"]
    if request["hosts"] is not None:
        prefix = prefix_for_hosts(request["hosts"], net.version)
    elif request["prefix"] is not None:
        prefix = request["prefix"]
    else:
        return None
    if prefix < net.prefixlen or prefix > net.max_prefixlen:
        raise ValueError(
            "subnet %s: /%d does not fit in %s" % (name, prefix, net)
        )
    return prefix
