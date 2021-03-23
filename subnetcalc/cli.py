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
    lines = [
        "CIDR:         %s" % info["cidr"],
        "Version:      IPv%d" % info["version"],
        "Network:      %s" % info["network_address"],
        "Broadcast:    %s" % info["broadcast_address"],
        "Netmask:      %s" % info["netmask"],
        "Wildcard:     %s" % info["hostmask"],
        "Prefix:       /%d" % info["prefixlen"],
        "Hosts:        %s - %s" % (info["first_host"], info["last_host"]),
        "Addresses:    %d" % info["num_addresses"],
        "Usable hosts: %d" % info["num_usable"],
        "Private:      %s" % info["is_private"],
        "Global:       %s" % info["is_global"],
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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="subnetcalc",
        description="CIDR / subnet toolkit for network admins.",
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
