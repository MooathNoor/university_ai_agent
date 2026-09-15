import sys
import types
import time

# Keep the test offline: telegram_bot only needs these two main entry points.
main_stub = types.ModuleType("main")
main_stub.get_fast_conversation_response = lambda text: "fast"
main_stub.process_user_message = lambda text: "processed"
sys.modules["main"] = main_stub

import telegram_bot as tb

# Fast social turns must NOT bypass the FIFO worker anymore.
assert tb._try_fast_response({"message": {"chat": {"id": 1}, "text": "مساء الخير"}}) is False

# Verify worker FIFO ordering directly without Telegram/network calls.
seen = []
original = tb.process_telegram_message
tb.process_telegram_message = lambda update: seen.append(update["seq"])
worker = tb._start_message_worker()
try:
    tb._MESSAGE_QUEUE.put({"seq": 1})
    tb._MESSAGE_QUEUE.put({"seq": 2})
    tb._MESSAGE_QUEUE.put({"seq": 3})
    tb._MESSAGE_QUEUE.join()
    assert seen == [1, 2, 3], seen
finally:
    tb.process_telegram_message = original
    tb._MESSAGE_QUEUE.put(tb._WORKER_STOP)
    worker.join(timeout=2)

print("PASS: Phase 5 Telegram FIFO ordering assertions")
