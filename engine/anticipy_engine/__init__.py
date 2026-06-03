"""Anticipy local engine ("the brain").

A local-first service that runs on 127.0.0.1 and is the hub every other room
talks to. The SwiftUI app and the browser extension are clients; they never
think on their own — everything routes through this engine.
"""

__version__ = "0.1.0"
