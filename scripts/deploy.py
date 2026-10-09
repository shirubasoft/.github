#!/usr/bin/env python3
"""Deploy an Aspire AppHost with explicit inputs and disposable local state."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ASPIRE_VERSION = "13.6.1"
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
PARAMETER = re.compile(r"[a-z][a-z0-9-]*")


def fail(message):
    raise RuntimeError(message)


def parameter_environment(parameters):
    result = {}
    for name, value in parameters.items():
        if not PARAMETER.fullmatch(name) or not isinstance(value, str) or not value:
            fail("Invalid or empty deployment parameter")
        result["Parameters__" + name.replace("-", "_")] = value
    return result


def run(command, env, secrets=(), cwd=None):
    # Aspire/build tools sometimes include parameter values in diagnostics.
    hidden = sorted({v for value in secrets for v in
                     (value, urllib.parse.quote(value, safe="")) if v}, key=len, reverse=True)
    with subprocess.Popen(command, env=env, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True) as process:
        for line in process.stdout:
            for value in hidden:
                line = line.replace(value, "[redacted]")
            print(line, end="", flush=True)
        if process.wait():
            fail("Deployment command failed; secret values withheld")


def check_url(url):
    # Bound the rollout check to two minutes; never print response bodies.
    for attempt in range(24):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "shirubasoft-aspire-deploy/1.0"})
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        if attempt < 23:
            time.sleep(5)
    fail("Public endpoint did not return HTTP 200")


def deploy(root, inputs, preview=False):
    config = json.loads((root / "deploy.json").read_text())
    environment = inputs["environment"]
    project = inputs["project"]
    if not NAME.fullmatch(environment) or not NAME.fullmatch(project):
        fail("Invalid environment or Compose project name")
    apphost = (root / config["apphost"]).resolve()
    if not apphost.is_relative_to(root) or not apphost.is_file():
        fail("AppHost must be a file inside the application checkout")
    secrets = inputs["secrets"]
    variables = inputs["parameters"]
    if set(secrets) & set(variables):
        fail("A parameter cannot be both secret and non-secret")
    parameters = {**variables, **secrets}
    if set(config["parameters"]) != set(parameters):
        fail("Deployment inputs must supply exactly the parameters in deploy.json")
    host = inputs["docker_host"]
    address = urllib.parse.urlsplit(host)
    if address.scheme != "ssh" or address.username != "deploy" or not address.hostname or address.password or address.port:
        fail("Docker host must use ssh://deploy@hostname")
    known_hosts = inputs["known_hosts"]
    lines = [line.split() for line in known_hosts.splitlines() if line and not line.startswith("#")]
    if len(lines) != 1 or lines[0][0] != address.hostname or lines[0][1] != "ssh-ed25519" or len(lines[0]) != 3:
        fail("Supply one pinned ed25519 known_hosts line for the Docker host")
    binaries = {name: shutil.which(name) for name in ("aspire", "docker", "ssh", "node", "dotnet")}
    if not all(binaries.values()):
        fail("Install Aspire, Docker with Compose/buildx, SSH, Node and .NET first")
    if subprocess.check_output([binaries["aspire"], "--version"], text=True).strip().split("+")[0] != ASPIRE_VERSION:
        fail("Aspire CLI must be " + ASPIRE_VERSION)
    node_version = (root / ".node-version").read_text().strip()
    if subprocess.check_output([binaries["node"], "--version"], text=True).strip() != "v" + node_version:
        fail("Node must match .node-version")
    sdk = json.loads((root / "global.json").read_text())["sdk"]["version"]
    if subprocess.check_output([binaries["dotnet"], "--version"], cwd=root, text=True).strip() != sdk:
        fail("The .NET SDK must match global.json exactly")

    with tempfile.TemporaryDirectory(prefix="aspire-deploy-") as scratch:
        scratch = Path(scratch)
        (scratch / "bin").mkdir()
        (scratch / "home").mkdir()
        (scratch / "docker").mkdir()
        # Preserve only executable plugins, not workstation Docker contexts or credentials.
        plugin_dir = Path(os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker"))) / "cli-plugins"
        if plugin_dir.is_dir():
            (scratch / "docker/cli-plugins").symlink_to(plugin_dir)
        key_file = scratch / "known_hosts"
        key_file.write_text(known_hosts)
        key_file.chmod(0o600)
        ssh_config = scratch / "ssh_config"
        ssh_config.write_text(f"Host *\n  BatchMode yes\n  StrictHostKeyChecking yes\n  UserKnownHostsFile {key_file}\n  GlobalKnownHostsFile /dev/null\n  IdentityFile none\n  IdentityAgent none\n  ControlMaster no\n  ConnectTimeout 15\n")
        ssh_config.chmod(0o600)
        # Docker invokes ssh by name. This wrapper also prevents ~/.ssh/config from
        # supplying keys or weakening verification in workstation runs.
        ssh_wrapper = scratch / "bin/ssh"
        ssh_wrapper.write_text("#!/usr/bin/env python3\nimport os,sys\nos.execv(" + repr(binaries["ssh"]) + ", [" + repr(binaries["ssh"]) + ", '-F', " + repr(str(ssh_config)) + ", *sys.argv[1:]])\n")
        ssh_wrapper.chmod(0o700)
        shutil.copyfile(Path(__file__).with_name("docker.py"), scratch / "bin/docker")
        (scratch / "bin/docker").chmod(0o700)
        env = os.environ.copy()
        for key in list(env):
            if key.lower().startswith("parameters__") or key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "ASPIRE_SECRET_PARAMETERS"):
                del env[key]
        env.update(parameter_environment(parameters))
        env.update({"DOCKER_CONFIG": str(scratch / "docker"), "DOCKER_HOST": host,
                    "ASPIRE_CONTAINER_RUNTIME": "docker", "DEPLOY_PROJECT": project,
                    "DEPLOY_REAL_DOCKER": binaries["docker"],
                    "PATH": str(scratch / "bin") + os.pathsep + env["PATH"],
                    "DOTNET_NOLOGO": "1", "DOTNET_CLI_TELEMETRY_OPTOUT": "1"})
        run([binaries["docker"], "info", "--format", "Docker connection verified"], env, secrets.values(), root)
        command = [binaries["aspire"], "deploy", "--apphost", str(apphost), "--environment", environment,
                   "--non-interactive", "--nologo", "--pipeline-log-level", "warning", "-o", str(scratch / "output")]
        if preview:
            command.append("--list-steps")
        command.extend(["--", "--ASPIRE_HOME", str(scratch / "state")])
        run(command, env, secrets.values(), root)
        if preview:
            return
        result = subprocess.check_output([binaries["docker"], "ps", "-a", "--filter", "label=com.docker.compose.project=" + project,
                                          "--format", "{{.State}}"], env=env, text=True, stderr=subprocess.DEVNULL).splitlines()
        if not result or any(state != "running" for state in result):
            fail("Some Compose services are not running")
        check_url(inputs["url"])
        for path in config.get("health_paths", []):
            check_url(inputs["url"].rstrip("/") + path)
        print(f"Verified {project}: {len(result)} running services, public endpoints HTTP 200")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--inputs", type=Path, help="0600 onboarding input file; otherwise use CI environment")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.inputs:
            path = args.inputs.expanduser()
            if path.is_symlink() or path.stat().st_mode & 0o077:
                fail("Deployment input file must be a regular 0600 file")
            inputs = json.loads(path.read_text())
        else:
            # GitHub passes an unset or unforwarded environment secret as an empty string.
            empty = [name for name in ("ASPIRE_PARAMETERS", "ASPIRE_SECRET_PARAMETERS") if not os.environ.get(name)]
            if empty:
                fail("Empty deployment input: " + ", ".join(empty))
            inputs = {"environment": os.environ["DEPLOY_ENVIRONMENT"], "project": os.environ["DEPLOY_PROJECT"],
                      "docker_host": os.environ["DEPLOY_DOCKER_HOST"], "known_hosts": os.environ["DEPLOY_KNOWN_HOSTS"],
                      "url": os.environ["DEPLOY_URL"], "parameters": json.loads(os.environ["ASPIRE_PARAMETERS"]),
                      "secrets": json.loads(os.environ["ASPIRE_SECRET_PARAMETERS"])}
        deploy(args.repo.resolve(), inputs, args.preflight_only)
    except RuntimeError as error:
        sys.exit(str(error))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        sys.exit("Deployment failed. Check input names, tool versions and redacted diagnostics; values withheld.")


if __name__ == "__main__":
    main()
