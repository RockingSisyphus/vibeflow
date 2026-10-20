"""Explicit retirement of checks for the deleted native IO parser.

Keep reference.json intact. Ordinary SDK port behavior is exercised by native
runtime integration and portable conformance; two old IDs remain as migration
diagnostics. No other historical case may disappear.
"""
RETIRED = {"tooling": frozenset({
    "tooling.system_io.provides", "tooling.system_io.receive_empty", "tooling.system_io.requires",
    "tooling.system_io.send_normal", "tooling.system_io.send_optional",
    "tooling.variant.io.async", "tooling.variant.io.object", "tooling.variant.io.operation",
    "tooling.variant.io.port", "tooling.variant.io.receive_two", "tooling.variant.io.unknown",
})}
