# subnetcalc

A small, dependency-free CIDR / subnet toolkit for network admins. Built on
Python's standard-library `ipaddress` module, so it handles IPv4 and IPv6
equally well. Every subcommand can emit human-readable text or `--json`.

## Install

```console
$ python -m venv venv
$ . venv/bin/activate
$ pip install -e .
```

Requires Python 3.7+. For development (tests and lint):

```console
$ pip install -e . -r requirements-dev.txt
$ python -m pytest -q
$ python -m flake8 .
```

## Usage

Run `subnetcalc --help` or `subnetcalc <command> --help` for details. The
`--json` flag works either before or after the subcommand.

### info — describe a network

```console
$ subnetcalc info 192.168.1.0/24
CIDR:         192.168.1.0/24
Version:      IPv4
Network:      192.168.1.0
Broadcast:    192.168.1.255
Netmask:      255.255.255.0
Wildcard:     0.0.0.255
Prefix:       /24
Hosts:        192.168.1.1 - 192.168.1.254
Addresses:    256
Usable hosts: 254
Private:      True
Global:       False

$ subnetcalc info 2001:db8::/64 --json
{
  "cidr": "2001:db8::/64",
  "version": 6,
  ...
}
```

`Usable hosts` always counts exactly the addresses in the `Hosts` range shown
above it, matching the standard library's `ipaddress.hosts()`:

| Block | Usable hosts | Why |
| --- | --- | --- |
| IPv4 `/32` | 1 | the address itself |
| IPv4 `/31` | 2 | point-to-point link, no network or broadcast address (RFC 3021) |
| IPv4 other | `2^(32-n) - 2` | network and broadcast addresses are not assignable |
| IPv6 `/128` | 1 | the address itself |
| IPv6 `/127` | 2 | point-to-point link (RFC 6164) |
| IPv6 other | `2^(128-n) - 1` | the all-zeros interface ID is the Subnet-Router anycast address (RFC 4291 §2.6.1) |

By default host bits are masked off (`10.1.2.3/24` is read as `10.1.2.0/24`);
pass `--strict` to reject them instead. `--strict` applies to every network
argument of a command.

### split — subdivide a block

By target prefix length:

```console
$ subnetcalc split 192.168.0.0/24 --prefix 26
192.168.0.0/26
192.168.0.64/26
192.168.0.128/26
192.168.0.192/26
```

Or into K equal parts (K must be a power of two):

```console
$ subnetcalc split 10.0.0.0/24 --count 4
10.0.0.0/26
10.0.0.64/26
10.0.0.128/26
10.0.0.192/26
```

### contains — membership test

Exit code is `0` when the address/network is inside the CIDR, `1` otherwise.

```console
$ subnetcalc contains 10.0.0.0/24 10.0.0.42
true
$ subnetcalc contains 10.0.0.0/24 10.0.1.0/24
false
```

### overlaps — do two CIDRs intersect?

Exit code `0` on overlap, `1` otherwise.

```console
$ subnetcalc overlaps 10.0.0.0/16 10.0.1.0/24
true
```

### summarize — collapse into a minimal set

Accepts a mix of addresses and networks, IPv4 and/or IPv6.

```console
$ subnetcalc summarize 192.168.0.0/25 192.168.0.128/25
192.168.0.0/24
```

### range — cover an inclusive address range

```console
$ subnetcalc range 192.168.0.1 192.168.0.10
192.168.0.1/32
192.168.0.2/31
192.168.0.4/30
192.168.0.8/31
192.168.0.10/32
```

## Library use

The `subnetcalc.core` module exposes the same functionality as pure,
I/O-free functions returning `ipaddress` objects or plain dicts:

```python
from subnetcalc import core

core.network_info("10.0.0.0/24")
core.split_network("10.0.0.0/24", count=4)
core.contains("10.0.0.0/8", "10.1.2.3")
core.summarize(["10.0.0.0/25", "10.0.0.128/25"])
core.range_to_cidrs("192.168.0.0", "192.168.0.255")
```

## License

MIT — see [LICENSE](LICENSE).
