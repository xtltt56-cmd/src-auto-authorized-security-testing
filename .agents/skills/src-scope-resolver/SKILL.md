---
name: src-scope-resolver
description: Resolve a platform rule snapshot into a human-confirmable, explicit scope file.
---

# SRC Scope Resolver

Read current platform rules, record source and test window, normalize roots/hosts/ports, and write a candidate file. Never set `confirmed` or `allow_network_contact` automatically. A human must create the confirmed snapshot.
