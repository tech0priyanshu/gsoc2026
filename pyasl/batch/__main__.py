"""Entry point for `python -m pyasl.batch`."""
from __future__ import annotations

import argparse
import logging
import sys
from .engine import BatchEngine
from .job import BatchJob, BatchStatus
from .report import generate_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a single PyASL batch job from the command line."
    )
    parser.add_argument(
        "data_dir",
        help="Path to the input data directory for the batch job.",
    )
    parser.add_argument(
        "config_path",
        help="Path to the pipeline YAML configuration file.",
    )
    parser.add_argument(
        "--pipeline-type",
        choices=("legacy", "dag"),
        default="legacy",
        help="Pipeline execution mode.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum number of parallel workers to use.",
    )
    parser.add_argument(
        "--report-dir",
        default=".",
        help="Directory to write batch report files.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not generate an HTML/JSON batch report.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )

    job = BatchJob(
        data_dir=args.data_dir,
        config_path=args.config_path,
        pipeline_type=args.pipeline_type,
    )

    engine = BatchEngine(max_workers=args.max_workers)
    results = engine.run([job])

    for result in results:
        print(
            f"Job {result.job_id}: {result.status.value} "
            f"({result.duration:.2f}s)"
            if result.duration is not None
            else f"Job {result.job_id}: {result.status.value}"
        )
        if result.error:
            print(f"Error: {result.error}")

    if not args.no_report:
        html_path, json_path = generate_report(
            results, output_dir=args.report_dir
        )
        print(f"Report written: {html_path}")
        print(f"Summary JSON: {json_path}")

    success = all(result.status == BatchStatus.COMPLETED for result in results)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
