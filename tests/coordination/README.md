<!-- vibeflow-directory-purpose -->
# Coordination tests

Real loopback routing and process/Target handshakes. No test may stop unrelated
processes. Workflow clients, temporary services and owned test children are
closed in fixtures/finally; generated files use the isolated test directory.
