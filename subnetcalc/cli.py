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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="subnetcalc",
        description="CIDR / subnet toolkit for network admins.",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_info = sub.add_parser("info", help="show details about a CIDR block")
    p_info.add_argument("cidr", help="network in CIDR notation, e.g. 10.0.0.0/24")
    p_info.add_argument(
        "--strict", action="store_true", help="reject host bits in the network"
    )
    p_info.set_defaults(func=cmd_info)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
