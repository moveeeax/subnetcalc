# Changelog

All notable changes to this project are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0]

### Added
- `info` command: network/broadcast/netmask/wildcard, host range, usable host
  count, prefix, and classification flags (private, global, multicast,
  reserved, loopback, link-local) for IPv4 and IPv6.
- `split` command: subdivide a block by target `--prefix` or into `--count`
  equal parts.
- `contains` command: address/network membership test with a result-driven
  exit code.
- `overlaps` command: report whether two networks intersect.
- `summarize` command: collapse addresses/networks into a minimal CIDR set.
- `range` command: smallest CIDR set covering an inclusive address range.
- `--json` output for every command, accepted before or after the subcommand.
- Pure, I/O-free `subnetcalc.core` API for library use.
