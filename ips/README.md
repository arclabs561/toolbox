# ips

Show local/public IP addresses and run bounded, read-only network diagnostics.

## Usage

```sh
ips          # local interfaces + public IP
ips -v       # add geo info (city, country, org)
ips -4       # force IPv4 for public lookup
ips -6       # force IPv6 for public lookup
ips -c       # copy public IP to clipboard
ips -p       # public IP only (skip local)
ips diag      # inspect route, DNS, HTTPS, and gateway latency
ips link      # show local configuration and addresses
ips peers     # show passive neighbor-cache entries
ips speed HOST  # bounded TCP throughput probe to an iperf3 server
ips diag --json
```

`diag` performs a bounded gateway ping, DNS resolution, and HTTPS request using
stable built-in targets. It reports percentile latency, variance, loss, and
explicitly labeled delay variation. `link` identifies the active interface;
`wifi` describes the local radio link, not whether the upstream connection is a
hotspot or an infrastructure access point. `peers` reads the native neighbor
cache; it does not prove that a device is currently online. The latency
statistics are RTT statistics from the gateway ping; `rtt_ipdv` and `rtt_pdv`
must not be read as one-way delay measurements. Variance is the sample
variance (`n - 1`).

`speed HOST` is deliberately not an internet speed test. It requires an
iperf3 server on `HOST`, runs a fixed 10-second TCP test, and is the only mode
that intentionally moves substantial data. None of these modes scans the LAN,
captures traffic, or changes network state.

For richer passive LAN observation, Bettercap can be used separately with its
read-only `net.recon` module; `ips` deliberately does not start it or enable
active probing.
