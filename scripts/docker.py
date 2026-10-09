#!/usr/bin/env python3
"""Give Aspire a deterministic Compose project name. This does not isolate apps."""
import os
import sys


def arguments(args, project):
    if not args or args[0] != "compose":
        return args
    # Aspire 13.6.1 always supplies this option. Fail closed on a changed contract.
    if args.count("--project-name") != 1 or "-p" in args:
        raise ValueError("Unexpected Aspire Compose project argument")
    index = args.index("--project-name") + 1
    if index >= len(args) or not args[index].startswith("aspire-"):
        raise ValueError("Unexpected Aspire Compose project identity")
    return args[:index] + [project] + args[index + 1:]


if __name__ == "__main__":
    try:
        args = arguments(sys.argv[1:], os.environ["DEPLOY_PROJECT"])
    except (ValueError, KeyError):
        sys.exit("Unsupported Aspire Docker invocation; deployment stopped")
    docker = os.environ["DEPLOY_REAL_DOCKER"]
    os.execv(docker, [docker, *args])
