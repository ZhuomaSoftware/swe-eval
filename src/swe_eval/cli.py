from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmarks.local import LocalBenchmark
from .config import ConfigurationError, Settings, load_models
from .security import configure_logging
from .service import enqueue, public_run, repository


def print_json(value):
    print(json.dumps(value, indent=2))


def direct(settings, task_id, profile_id, *, patch=None, profiles=None):
    from .worker import Worker

    worker = Worker(settings)
    worker.install_signal_handlers()
    worker.acquire()
    try:
        from .benchmarks.official import TaskRegistry
        record = enqueue(worker.repo, TaskRegistry(settings), profiles or load_models(settings.models_file),
                         task_id, profile_id, mode="patch_verification" if patch is not None else "agent")
        record = worker.repo.claim(worker.owner, record["id"])
        return worker.supervise(record, supplied_patch=patch)
    finally:
        worker.repo.release(worker.owner)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent SWE evaluation service")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    commands.add_parser("doctor")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    run = commands.add_parser("run")
    run.add_argument("--task", required=True)
    run.add_argument("--model", required=True, help="model profile ID, not upstream model name")
    verify = commands.add_parser("verify-fixture")
    verify.add_argument("--case", choices=["good", "bad", "both"], default="both")
    dataset=commands.add_parser("dataset")
    actions=dataset.add_subparsers(dest="dataset_action",required=True)
    for action in ("list","status","import","validate"):
        sub=actions.add_parser(action)
        if action!="list":sub.add_argument("dataset",choices=["swebench-verified"])
        sub.add_argument("--revision",default="main" if action=="import" else None)
        sub.add_argument("--instance",action="append")
        sub.add_argument("--repo")
        sub.add_argument("--limit",type=int)
        sub.add_argument("--status")
        sub.add_argument("--subset",choices=["curated-20","curated-20-v1"])
        sub.add_argument("--dry-run",action="store_true")
        if action=="validate":
            sub.add_argument("--prepare",action="store_true",help="Explicitly pull selected official images")
            sub.add_argument("--timeout",type=int,default=600)
            sub.add_argument("--resume",action="store_true")
            sub.add_argument("--continue-on-error",action="store_true",help="Continue independent tasks after validation failures (maximum 20)")
    args = parser.parse_args(argv)
    configure_logging()
    try:
        settings = Settings.from_env()
        if args.command == "dataset":
            from .benchmarks.official import Catalogue,SUBSET
            from .official_harness import OfficialHarness
            catalogue=Catalogue(settings.data_dir)
            if args.limit is not None and not 1<=args.limit<=500:raise ValueError("limit must be 1..500")
            if args.dataset_action=="import":
                result=OfficialHarness(settings).import_dataset(args.revision,instance_ids=args.instance,repo=args.repo,limit=args.limit,dry_run=args.dry_run,validation_status=args.status)
                if args.subset and not args.dry_run:result["subset"]=catalogue.select_subset(result["revision"])
                print_json(result)
            elif args.dataset_action in ("list","status"):
                tasks=catalogue.list_tasks(revision=args.revision,repo=args.repo,search=args.instance[0] if args.instance else None,status=args.status,subset=SUBSET if args.subset else None)
                print_json({"revisions":catalogue.revisions(),"count":len(tasks),"items":[t.public() for t in tasks[:args.limit]] if args.limit else [t.public() for t in tasks]})
            else:
                from .dataset_validation import validate
                result=validate(settings,args);print_json(result)
                return 0 if args.dry_run or all(x["status"]=="validated" for x in result["items"]) else 1
        elif args.command == "init-db":
            repository(settings)
            print_json({"database": str(settings.database), "schema": 2})
        elif args.command == "serve":
            import uvicorn
            from .api import create_app

            uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)
        elif args.command == "worker":
            from .worker import Worker

            service = Worker(settings)
            service.install_signal_handlers()
            service.run(once=args.once)
        elif args.command == "run":
            record = direct(settings, args.task, args.model)
            print_json(public_run(record))
            return 0 if record["state"] == "completed" and record["metrics"]["resolved"] else 1
        elif args.command == "verify-fixture":
            # Use the same supervisor, engine, patch application, and hidden grader as real runs.
            profile_id = "fixture-verification"
            config = [{"id": profile_id, "upstream_id": "no-inference", "model_id": "none",
                       "base_url": "https://unused.invalid/v1", "allow_no_api_key": True,
                       "max_evaluation_duration": 120}]
            # The child loads its own file; use an isolated temporary config, not user models.
            import tempfile
            from dataclasses import replace

            success = True
            with tempfile.TemporaryDirectory(prefix="swe-verify-") as directory:
                config_path = Path(directory) / "models.json"
                config_path.write_text(json.dumps(config))
                verify_settings = replace(settings, models_file=config_path)
                benchmark = LocalBenchmark(settings.task_dir)
                task = benchmark.get_task("intervals-001")
                good = (benchmark.tasks[task.id][1] / "known_good.patch").read_text()
                cases = ["good", "bad"] if args.case == "both" else [args.case]
                for case in cases:
                    record = direct(verify_settings, task.id, profile_id, patch=good if case == "good" else "")
                    expected = case == "good"
                    matched = record["state"] == "completed" and record["metrics"]["resolved"] == expected
                    success &= matched
                    print_json({"case": case, "expected_resolved": expected, "matched": matched,
                                "run": public_run(record)})
            return 0 if success else 1
        elif args.command == "doctor":
            import os
            from .agent import verify_mini_api
            from .sandbox import run_process

            report = {"python": sys.version.split()[0], "models": len(load_models(settings.models_file)),
                      "tasks": len(LocalBenchmark(settings.task_dir).list_tasks())}
            os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(settings.data_dir / "mini-config")
            try:
                report["mini_version"] = verify_mini_api()[3]
            except (RuntimeError, ImportError):
                report["mini_version"] = "unavailable or incompatible"
            try:
                result = run_process([settings.docker_bin, "info", "--format={{.ServerVersion}}"], timeout=10)
                report["docker"] = result.output.strip() if not result.returncode else "unavailable"
            except RuntimeError:
                report["docker"] = "unavailable"
            print_json(report)
            return 0 if report["docker"] != "unavailable" and report["mini_version"] == "2.4.6" else 1
        return 0
    except ConfigurationError as error:
        print(f"swe-eval: {error}", file=sys.stderr)
        return 2
    except (Exception, KeyboardInterrupt) as error:
        # Do not echo configuration values, exception reprs, or provider credentials.
        print(f"swe-eval: {type(error).__name__}; check configuration, dependencies, Docker, and persisted run logs", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
