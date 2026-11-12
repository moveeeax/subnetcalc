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

Requires Python 3.11+. For development (tests and lint):

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
Multicast:    False
Reserved:     False
Loopback:     False
Link-local:   False

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

A split that would produce more than 1,000,000 subnets is rejected with an
error instead of hanging or exhausting memory — e.g. `10.0.0.0/8 --prefix 32`
(16,777,216 subnets) or any sufficiently large IPv6 split.

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

### free — unallocated space left in a block

Subtract the CIDRs already in use and print what is left, in minimal CIDR
form, plus a total.

```console
$ subnetcalc free 10.0.0.0/16 --used 10.0.1.0/24 --used 10.0.4.0/22
10.0.0.0/24
10.0.2.0/23
10.0.8.0/21
10.0.16.0/20
10.0.32.0/19
10.0.64.0/18
10.0.128.0/17
Total: 64256 addresses in 7 blocks
```

- `--used CIDR` can be repeated; addresses count as `/32` or `/128`.
- `--used-file FILE` reads one entry per line (commas also separate
  entries, `#` starts a comment, `-` reads stdin). It can be repeated and
  combined with `--used`.
- Used entries that do not overlap the block, including the other IP
  version, are skipped and listed under `ignored` in the JSON output, so one
  file of every CIDR in use works for any block.
- `--min-prefix N` hides free blocks smaller than `/N`; the total then
  counts only the listed blocks and says how much was left out.
- `--next /N` (or `--next N`) prints only the lowest free `/N` block. The
  exit code is `1` if there is none.

```console
$ subnetcalc free 10.0.0.0/16 --used 10.0.0.0/24 --used 10.0.2.0/24 --next /23
10.0.4.0/23
```

### plan — allocate named subnets from a supernet

`plan` replaces the address-plan spreadsheet: describe the subnets you need,
and it allocates non-overlapping blocks and emits them as a table, JSON,
YAML or Terraform `locals`.

The spec is a JSON file:

```json
{
  "supernet": "10.42.0.0/16",
  "subnets": [
    {"name": "public-a", "prefix": 24, "group": "public"},
    {"name": "public-b", "prefix": 24, "group": "public"},
    {"name": "app-a", "hosts": 500, "group": "app"},
    {"name": "app-b", "hosts": 500, "group": "app"},
    {"name": "vpn", "cidr": "10.42.255.0/24"}
  ]
}
```

Each subnet has a `name` and one of `prefix` (prefix length) or `hosts`
(required usable hosts, counted as in `info`, so `500` gives a `/23` in IPv4).
`cidr` pins a subnet to a fixed block; a size given next to it must match.
`group` (a tier, an availability zone) is optional. Names and groups use
letters, digits, `_`, `.` and `-`.

```console
$ subnetcalc plan --spec network.json
NAME      GROUP   CIDR            USABLE
public-a  public  10.42.4.0/24    254
public-b  public  10.42.5.0/24    254
app-a     app     10.42.0.0/23    510
app-b     app     10.42.2.0/23    510
vpn       -       10.42.255.0/24  254

Supernet: 10.42.0.0/16
Free: 63744 addresses in 12 blocks, largest 10.42.64.0/18, fragmentation 50.0%
  10.42.6.0/23
  ...
```

How allocation works:

- Pinned (`cidr`) subnets and subnets kept from `--previous` are placed
  first. The rest go largest first (ties in spec order), each at the lowest
  free address where it fits. Output keeps spec order.
- `--used CIDR` / `--used-file FILE` (same format as for `free`) mark space
  already taken outside the plan. Nothing is allocated there, and a pinned
  subnet that collides with a used CIDR, another pin or the supernet edge is
  an error, so a collision shows up before `terraform apply`.
- Largest-first means that adding a big subnet to the spec can move the
  others. To keep existing subnets where they are, save the JSON output and
  pass it back with `--previous`: names found there keep their CIDR, new
  names fill the free space, and names no longer in the spec are freed and
  listed as `released`. Changing the size of a kept subnet is an error.
- `--strict` applies to the supernet and used CIDRs. CIDRs in the spec and
  in the `--previous` file are always parsed strictly: host bits there are
  treated as a typo.
- The run fails with exit code `2` if a subnet does not fit.

The free-space report lists what is left. Fragmentation is
`1 - largest_free / ideal`, where `ideal` is the largest power of two not
above the free address count: `0%` means the largest free block is as big
as the remaining space allows, `50%` means it is half that. In the example
above the pinned `vpn` block at the top of the supernet keeps any free
`/17` from existing, so the largest block left is a `/18`.

For quick plans, `--subnet NAME=/PREFIX` or `--subnet NAME=HOSTS` can be
used instead of, or on top of, a spec file; the supernet then comes from the
positional argument.

```console
$ subnetcalc plan 10.0.0.0/24 --subnet web=/26 --subnet db=20 --format yaml
supernet: "10.0.0.0/24"
subnets:
  "web": "10.0.0.0/26"
  "db": "10.0.0.64/27"
free:
  - "10.0.0.96/27"
  - "10.0.0.128/25"
free_addresses: 160
fragmentation: 0.0
```

`--format hcl` writes Terraform `locals`, laid out the way `terraform fmt`
leaves them; `subnet_groups` appears only when some subnet has a group:

```console
$ subnetcalc plan --spec network.json --format hcl --out cidrs.tf
$ cat cidrs.tf
# Generated by subnetcalc plan from 10.42.0.0/16; do not edit by hand.
# Free: 63744 addresses in 12 blocks, largest 10.42.64.0/18, fragmentation 50.0%
locals {
  subnet_cidrs = {
    "public-a" = "10.42.4.0/24"
    ...
  }

  subnet_groups = {
    "public" = {
      "public-a" = "10.42.4.0/24"
      "public-b" = "10.42.5.0/24"
    }
    ...
  }
}
```

A typical loop keeps both files in the repository:

```console
$ subnetcalc plan --spec network.json --previous plan.json --json --out plan.json.new
$ mv plan.json.new plan.json
$ subnetcalc plan --spec network.json --previous plan.json --format hcl --out cidrs.tf
```

The spec format is JSON so that the tool keeps no dependencies outside the
standard library.

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
core.free_space("10.0.0.0/16", ["10.0.1.0/24"])
core.next_free("10.0.0.0/16", ["10.0.1.0/24"], 24)
core.plan_subnets("10.0.0.0/16", core.parse_plan_spec(spec)[1])
```

## License

MIT — see [LICENSE](LICENSE).
