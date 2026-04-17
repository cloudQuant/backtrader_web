"""Date and timing utility helpers."""

import time

__all__ = ["timer"]


def timer(msg_body, previous_time):
    """Print elapsed time since *previous_time* and return current timestamp."""
    current_time = time.time()
    run_time = current_time - previous_time
    message = "\nFinished " + msg_body + " (required {:.2f} seconds)."
    print(message.format(run_time))

    return current_time
