"""Command line interface for subnetcalc.

Thin argparse wrapper around :mod:`subnetcalc.core`.  Each subcommand maps
to a handler that turns core results into text or JSON and returns a POSIX
exit code.
"""

import argparse
import json
import sys

from . import __version__, core


def _print_result(payload, lines, as_json):
    """Emit either a JSON ``payload`` or the pre-rendered text ``lines``."""
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for line in lines:
            print(line)


def cmd_info(args):
    info = core.network_info(args.cidr, strict=args.strict)
    # IPv6 has no broadcast address; label the final address accordingly.
    last_label = "Broadcast:   " if info["version"] == 4 else "Last addr:   "
    lines = [
        "CIDR:         %s" % info["cidr"],
        "Version:      IPv%d" % info["version"],
        "Network:      %s" % info["network_address"],
        "%s %s" % (last_label, info["broadcast_address"]),
        "Netmask:      %s" % info["netmask"],
        "Wildcard:     %s" % info["hostmask"],
        "Prefix:       /%d" % info["prefixlen"],
        "Hosts:        %s - %s" % (info["first_host"], info["last_host"]),
        "Addresses:    %d" % info["num_addresses"],
        "Usable hosts: %d" % info["num_usable"],
        "Private:      %s" % info["is_private"],
        "Global:       %s" % info["is_global"],
        "Multicast:    %s" % info["is_multicast"],
        "Reserved:     %s" % info["is_reserved"],
        "Loopback:     %s" % info["is_loopback"],
        "Link-local:   %s" % info["is_link_local"],
    ]
    _print_result(info, lines, args.json)
    return 0


def cmd_split(args):
    subnets = core.split_network(
        args.cidr,
        new_prefix=args.prefix,
        count=args.count,
        strict=args.strict,
    )
    strs = [str(s) for s in subnets]
    payload = {"cidr": args.cidr, "count": len(strs), "subnets": strs}
    _print_result(payload, strs, args.json)
    return 0


def cmd_contains(args):
    result = core.contains(args.cidr, args.addr, strict=args.strict)
    payload = {"cidr": args.cidr, "addr": args.addr, "contains": result}
    _print_result(payload, ["true" if result else "false"], args.json)
    return 0 if result else 1


def cmd_overlaps(args):
    result = core.overlaps(args.cidr_a, args.cidr_b, strict=args.strict)
    payload = {"a": args.cidr_a, "b": args.cidr_b, "overlaps": result}
    _print_result(payload, ["true" if result else "false"], args.json)
    return 0 if result else 1


def cmd_summarize(args):
    nets = core.summarize(args.items, strict=args.strict)
    strs = [str(n) for n in nets]
    payload = {"input": list(args.items), "summary": strs}
    _print_result(payload, strs, args.json)
    return 0


def cmd_range(args):
    nets = core.range_to_cidrs(args.start, args.end)
    strs = [str(n) for n in nets]
    payload = {"start": args.start, "end": args.end, "cidrs": strs}
    _print_result(payload, strs, args.json)
    return 0


def _read_text(path):
    """Contents of ``path``, or of stdin for ``-``; OSError becomes ValueError."""
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc.strerror or exc))


def _read_used(args):
    """``--used`` values plus the entries of every ``--used-file``.

    A used file holds one address or CIDR per line (commas and extra
    whitespace also separate entries); ``#`` starts a comment.
    """
    used = list(args.used or [])
    for path in args.used_file or []:
        for line in _read_text(path).splitlines():
            line = line.split("#", 1)[0]
            used.extend(tok for tok in line.replace(",", " ").split() if tok)
    return used


def _parse_prefix(value):
    """argparse type for ``24`` or ``/24``."""
    text = value[1:] if value.startswith("/") else value
    try:
        return int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid prefix length: %r" % value)


def cmd_free(args):
    used = _read_used(args)
    net = core.parse_network(args.cidr, strict=args.strict)
    relevant = [u for u in used if core.overlaps(net, u, strict=args.strict)]
    ignored = [u for u in used if u not in relevant]

    if args.next is not None:
        block = core.next_free(net, used, args.next, strict=args.strict)
        if args.json:
            payload = {
                "cidr": str(net),
                "prefix": args.next,
                "next": str(block) if block is not None else None,
            }
            print(json.dumps(payload, indent=2))
        elif block is not None:
            print(block)
        else:
            print("no free /%d left in %s" % (args.next, net), file=sys.stderr)
        return 0 if block is not None else 1

    all_free = core.free_space(net, used, strict=args.strict)
    shown = core.free_space(net, used, min_prefix=args.min_prefix, strict=args.strict)
    total = sum(b.num_addresses for b in shown)
    hidden = sum(b.num_addresses for b in all_free) - total
    strs = [str(b) for b in shown]
    payload = {
        "cidr": str(net),
        "used": relevant,
        "ignored": ignored,
        "min_prefix": args.min_prefix,
        "free": strs,
        "count": len(strs),
        "free_addresses": total,
        "hidden_addresses": hidden,
    }
    summary = "Total: %d addresses in %d block%s" % (
        total, len(strs), "" if len(strs) == 1 else "s"
    )
    if hidden:
        summary += " (%d more in blocks smaller than /%d)" % (hidden, args.min_prefix)
    _print_result(payload, strs + [summary], args.json)
    return 0


def _parse_subnet_flag(value):
    """argparse type for ``--subnet NAME=/24`` (prefix) or ``NAME=500`` (hosts)."""
    name, sep, size = value.partition("=")
    if not sep or not name or not size:
        raise argparse.ArgumentTypeError(
            "expected NAME=/PREFIX or NAME=HOSTS, got %r" % value
        )
    try:
        if size.startswith("/"):
            return {"name": name, "prefix": int(size[1:])}
        return {"name": name, "hosts": int(size)}
    except ValueError:
        raise argparse.ArgumentTypeError("invalid size in %r" % value)


def _load_previous(path):
    """Name -> CIDR map from the JSON output of an earlier ``plan`` run."""
    try:
        data = json.loads(_read_text(path))
        return {entry["name"]: entry["cidr"] for entry in data["subnets"]}
    except (TypeError, KeyError) as exc:
        raise ValueError(
            "%s is not the JSON output of 'subnetcalc plan' (%s)" % (path, exc)
        )


def cmd_plan(args):
    supernet = args.supernet
    requests = []
    if args.spec:
        try:
            data = json.loads(_read_text(args.spec))
        except json.JSONDecodeError as exc:
            raise ValueError("%s: invalid JSON: %s" % (args.spec, exc))
        spec_supernet, requests = core.parse_plan_spec(data)
        if supernet is None:
            supernet = spec_supernet
        elif spec_supernet is not None and core.parse_network(
            spec_supernet, strict=args.strict
        ) != core.parse_network(supernet, strict=args.strict):
            raise ValueError(
                "supernet %s does not match %s in %s" % (supernet, spec_supernet, args.spec)
            )
    if supernet is None:
        raise ValueError("no supernet: pass SUPERNET or set 'supernet' in the spec")
    _, extra = core.parse_plan_spec({"subnets": args.subnet or []})
    requests += extra
    if not requests:
        raise ValueError("nothing to plan: pass --spec or --subnet")

    previous = _load_previous(args.previous) if args.previous else None
    plan = core.plan_subnets(
        supernet, requests, used=_read_used(args), previous=previous, strict=args.strict
    )
    fmt = "json" if args.json else args.format
    text = _PLAN_FORMATTERS[fmt](plan)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            raise ValueError("cannot write %s: %s" % (args.out, exc.strerror or exc))
    else:
        sys.stdout.write(text)
    return 0


def _plan_groups(plan):
    """Ordered ``{group: [subnet, ...]}`` for subnets that have a group."""
    groups = {}
    for subnet in plan["subnets"]:
        if subnet["group"] is not None:
            groups.setdefault(subnet["group"], []).append(subnet)
    return groups


def _plan_free_summary(plan):
    if not plan["free"]:
        return "Free: none"
    return "Free: %d addresses in %d block%s, largest %s, fragmentation %.1f%%" % (
        plan["free_addresses"],
        len(plan["free"]),
        "" if len(plan["free"]) == 1 else "s",
        plan["largest_free"],
        plan["fragmentation"] * 100,
    )


def _format_plan_table(plan):
    header = ("NAME", "GROUP", "CIDR", "USABLE")
    rows = [
        (s["name"], s["group"] or "-", s["cidr"], str(s["num_usable"]))
        for s in plan["subnets"]
    ]
    widths = [max(len(row[i]) for row in [header] + rows) for i in range(3)]
    lines = []
    for row in [header] + rows:
        cells = [row[i].ljust(widths[i]) for i in range(3)] + [row[3]]
        lines.append("  ".join(cells))
    lines += ["", "Supernet: %s" % plan["supernet"], _plan_free_summary(plan)]
    lines += ["  %s" % block for block in plan["free"]]
    if plan["released"]:
        lines.append("Released: %s" % ", ".join(plan["released"]))
    return "\n".join(lines) + "\n"


def _format_plan_json(plan):
    return json.dumps(plan, indent=2) + "\n"


def _hcl_map(name, entries, indent):
    """An HCL map attribute with ``=`` aligned the way ``terraform fmt`` does."""
    pad = " " * indent
    width = max(len(key) for key, _ in entries) + 2
    lines = ["%s%s = {" % (pad, name)]
    for key, value in entries:
        lines.append("%s  %s = %s" % (pad, ('"%s"' % key).ljust(width), value))
    lines.append("%s}" % pad)
    return lines


def _format_plan_hcl(plan):
    lines = [
        "# Generated by subnetcalc plan from %s; do not edit by hand." % plan["supernet"],
        "# %s" % _plan_free_summary(plan),
        "locals {",
    ]
    lines += _hcl_map(
        "subnet_cidrs",
        [(s["name"], '"%s"' % s["cidr"]) for s in plan["subnets"]],
        2,
    )
    groups = _plan_groups(plan)
    if groups:
        lines.append("")
        lines.append("  subnet_groups = {")
        for i, (group, members) in enumerate(groups.items()):
            if i:
                lines.append("")
            lines += _hcl_map(
                '"%s"' % group,
                [(s["name"], '"%s"' % s["cidr"]) for s in members],
                4,
            )
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _format_plan_yaml(plan):
    # Every scalar is double-quoted so names like "on" or "1" stay strings
    # and IPv6 colons need no further thought.
    lines = ['supernet: "%s"' % plan["supernet"], "subnets:"]
    lines += ['  "%s": "%s"' % (s["name"], s["cidr"]) for s in plan["subnets"]]
    groups = _plan_groups(plan)
    if groups:
        lines.append("groups:")
        for group, members in groups.items():
            lines.append('  "%s":' % group)
            lines += ['    "%s": "%s"' % (s["name"], s["cidr"]) for s in members]
    lines.append("free:" if plan["free"] else "free: []")
    lines += ['  - "%s"' % block for block in plan["free"]]
    lines.append("free_addresses: %d" % plan["free_addresses"])
    lines.append("fragmentation: %s" % plan["fragmentation"])
    return "\n".join(lines) + "\n"


_PLAN_FORMATTERS = {
    "table": _format_plan_table,
    "json": _format_plan_json,
    "hcl": _format_plan_hcl,
    "yaml": _format_plan_yaml,
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="subnetcalc",
        description="CIDR / subnet toolkit for network admins.",
        epilog=(
            "examples:\n"
            "  subnetcalc info 192.168.1.0/24\n"
            "  subnetcalc split 10.0.0.0/24 --count 4\n"
            "  subnetcalc contains 10.0.0.0/8 10.1.2.3\n"
            "  subnetcalc summarize 10.0.0.0/25 10.0.0.128/25\n"
            "  subnetcalc range 192.168.0.1 192.168.0.10 --json\n"
            "  subnetcalc free 10.0.0.0/16 --used 10.0.1.0/24 --next /24\n"
            "  subnetcalc plan 10.42.0.0/16 --spec network.json --format hcl\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="global_json",
        help="emit machine-readable JSON",
    )

    # Shared options usable either before or after the subcommand name.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_info = sub.add_parser(
        "info", parents=[common], help="show details about a CIDR block"
    )
    p_info.add_argument("cidr", help="network in CIDR notation, e.g. 10.0.0.0/24")
    p_info.add_argument(
        "--strict", action="store_true", help="reject host bits in the network"
    )
    p_info.set_defaults(func=cmd_info)

    p_split = sub.add_parser("split", parents=[common], help="subdivide a CIDR block")
    p_split.add_argument("cidr", help="network to subdivide")
    group = p_split.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--prefix", type=int, metavar="N", help="target prefix length"
    )
    group.add_argument(
        "--count", type=int, metavar="K", help="number of equal subnets (power of two)"
    )
    p_split.add_argument("--strict", action="store_true", help="reject host bits")
    p_split.set_defaults(func=cmd_split)

    p_contains = sub.add_parser(
        "contains",
        parents=[common],
        help="test whether an address/network is inside a CIDR",
    )
    p_contains.add_argument("cidr", help="containing network")
    p_contains.add_argument("addr", help="address or network to test")
    p_contains.add_argument("--strict", action="store_true", help="reject host bits")
    p_contains.set_defaults(func=cmd_contains)

    p_overlaps = sub.add_parser(
        "overlaps", parents=[common], help="test whether two CIDRs overlap"
    )
    p_overlaps.add_argument("cidr_a", metavar="CIDR_A", help="first network")
    p_overlaps.add_argument("cidr_b", metavar="CIDR_B", help="second network")
    p_overlaps.add_argument("--strict", action="store_true", help="reject host bits")
    p_overlaps.set_defaults(func=cmd_overlaps)

    p_sum = sub.add_parser(
        "summarize",
        parents=[common],
        help="collapse addresses/networks into a minimal CIDR set",
    )
    p_sum.add_argument("items", nargs="+", metavar="ADDR", help="addresses or networks")
    p_sum.add_argument("--strict", action="store_true", help="reject host bits")
    p_sum.set_defaults(func=cmd_summarize)

    p_range = sub.add_parser(
        "range",
        parents=[common],
        help="smallest CIDR set covering an inclusive address range",
    )
    p_range.add_argument("start", help="first address (inclusive)")
    p_range.add_argument("end", help="last address (inclusive)")
    p_range.set_defaults(func=cmd_range)

    # Options shared by commands that subtract CIDRs already in use.
    used_opts = argparse.ArgumentParser(add_help=False)
    used_opts.add_argument(
        "--used",
        action="append",
        metavar="CIDR",
        help="address or network already in use (repeatable)",
    )
    used_opts.add_argument(
        "--used-file",
        action="append",
        metavar="FILE",
        help="file with one used address/CIDR per line, '#' comments, '-' for stdin",
    )

    p_free = sub.add_parser(
        "free",
        parents=[common, used_opts],
        help="list the unallocated space left in a block",
    )
    p_free.add_argument("cidr", help="block to inspect")
    p_free.add_argument(
        "--min-prefix",
        type=_parse_prefix,
        metavar="N",
        help="hide free blocks smaller than /N",
    )
    p_free.add_argument(
        "--next",
        type=_parse_prefix,
        metavar="/N",
        help="print only the first free block of size /N (exit 1 if none)",
    )
    p_free.add_argument("--strict", action="store_true", help="reject host bits")
    p_free.set_defaults(func=cmd_free)

    p_plan = sub.add_parser(
        "plan",
        parents=[common, used_opts],
        help="allocate named, non-overlapping subnets from a supernet",
    )
    p_plan.add_argument(
        "supernet", nargs="?", help="block to allocate from (or 'supernet' in the spec)"
    )
    p_plan.add_argument("--spec", metavar="FILE", help="JSON plan spec, '-' for stdin")
    p_plan.add_argument(
        "--subnet",
        action="append",
        type=_parse_subnet_flag,
        metavar="NAME=SIZE",
        help="subnet to allocate: NAME=/PREFIX or NAME=HOSTS (repeatable)",
    )
    p_plan.add_argument(
        "--previous",
        metavar="FILE",
        help="JSON output of an earlier plan; its subnets keep their CIDRs",
    )
    p_plan.add_argument(
        "--format",
        choices=sorted(_PLAN_FORMATTERS),
        default="table",
        help="output format (default: table); --json is the same as --format json",
    )
    p_plan.add_argument("--out", metavar="FILE", help="write the plan to FILE")
    p_plan.add_argument("--strict", action="store_true", help="reject host bits")
    p_plan.set_defaults(func=cmd_plan)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    # A global "--json" (before the subcommand) folds into the per-command flag.
    args.json = getattr(args, "json", False) or getattr(args, "global_json", False)
    try:
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
