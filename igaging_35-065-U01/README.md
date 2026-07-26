# iGaging 35-065-U01 TwinForce EZ Data Micrometer

Purchased from [Amazon](https://www.amazon.com/dp/B08JKPQ912) in June 2026; manufacturer site: [iGaging](http://www.igaging.com/ip65-ez-data-twinforce-mics-sets.html).

This advertises a "Micro USB data output" but quite frustratingly it's only a MicroUSB *connector*; it actually uses a proprietary protocol that is completely incompatible with USB and requires iGaging's `100-700-USB-MC` wired USB data kit or `35-BT28-MC` Bluetooth data kit.

This directory holds an ongoing effort to reverse-engineer that port and read the mic directly.

**Start with [`STATUS.md`](STATUS.md)** — current state, what's confirmed, and what to try next.

| | |
|---|---|
| [`STATUS.md`](STATUS.md) | Where things stand; next experiments |
| [`BENCH_LOG.md`](BENCH_LOG.md) | Chronological bench record |
| [`igaging_protcol_research.md`](igaging_protcol_research.md) | Protocol reference and sources |
| [`review.md`](review.md) | Audit of the above against the raw captures |
| [`ARCHIVE/`](ARCHIVE/) | Retired docs — superseded, not current |
