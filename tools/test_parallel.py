"""Shared concurrency options for repository verification and sandboxes."""

import argparse
import os


DEFAULT_WORKERS = 12
WORKER_ENVIRONMENT = "VIBEFLOW_TEST_WORKERS"


def positive_workers(value: str) -> int:
    try:
        workers = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("workers must be a positive integer") from exc
    if workers < 1:
        raise argparse.ArgumentTypeError("workers must be a positive integer")
    return workers


def add_worker_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workers", type=positive_workers,
                        default=os.environ.get(WORKER_ENVIRONMENT, str(DEFAULT_WORKERS)),
                        help=f"maximum concurrent test workers (default: {DEFAULT_WORKERS}; {WORKER_ENVIRONMENT})")
