<!-- vibeflow-directory-purpose -->
# Local workflow coordination

Shared JSON protocol, mailbox routing, launch handshake and native client. The
application explicitly starts the service and configures launch commands. This
package never owns run groups, kills children on caller exit, retries business
operations or maintains a process pool. Target bindings and preview rendering
are outside this directory. Tests and generated projects use external scratch.
