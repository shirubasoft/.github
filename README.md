# Shared workflows

`aspire-deploy.yml` deploys Aspire 13.6.1 applications from GitHub-hosted Linux
runners. Call it at the owner-controlled `main` ref with a `staging` or `production`
`environment` input. Tailscale issuance requires this exact reusable workflow
ref, the caller's `refs/heads/main`, and organization ID `184028621`. The deployment
job uses that GitHub Environment's variables. The caller passes
`ASPIRE_SECRET_PARAMETERS` by name (`secrets: ASPIRE_SECRET_PARAMETERS: ${{ secrets.ASPIRE_SECRET_PARAMETERS }}`);
GitHub resolves it from the Environment inside the deployment job and gives an
unpassed secret an empty value. Only `push` and `workflow_dispatch` on `main` can run it.

The application supplies `global.json`, `.node-version`, and `deploy.json`:

```json
{
  "apphost": "apphost/AppHost.csproj",
  "parameters": ["database-password", "my-app-staging-tunnel-token"],
  "health_paths": ["/health"],
  "tunnel": {"hostname": "my-app-staging.shiruba.software", "service": "web", "targetPort": 8080}
}
```

List every publish-mode parameter, including generated passwords and connector
tokens. Pin an exact .NET SDK with `rollForward: disable` and an exact Node version.
AppHosts use named volumes and fixed tunnel target ports. The standard onboarding
command in the homelab repository creates the Environment, inputs, tunnel and
caller at `main`. The AppHost uses `AddCloudflareTunnelConnector`; onboarding
owns ingress and DNS, and deploys get only that tunnel's connector token. It supports private and public application repositories.

The Environment supplies `DEPLOY_PROJECT`, `DEPLOY_DOCKER_HOST`,
`DEPLOY_KNOWN_HOSTS`, `DEPLOY_URL`, `ASPIRE_PARAMETERS`, `TS_DEPLOY_CLIENT_ID`,
and `TS_DEPLOY_AUDIENCE` as variables. `ASPIRE_SECRET_PARAMETERS` is a JSON map
stored as an Environment secret. Values become `Parameters__name` configuration
inputs; dashes in names become underscores. Each deploy starts with an empty
Aspire deployment-state directory and removes generated files afterward.

## Platform revision

The callable ref moves when the owner updates the platform's `main` branch. A
caller therefore follows reviewed platform changes instead of reproducing a
fixed platform revision forever. The workflow logs its signed `job_workflow_sha`
and checks out deployment scripts at that exact SHA, keeping each run internally
consistent. Onboarding records the reviewed revision in `.deploy-platform-ref`
for workstation replay. Refresh that file when selecting another platform
revision locally; CI always uses the SHA of the workflow it actually runs.

## Local deployment

Use the same script and the 0600 input file produced by onboarding:

```sh
python3 scripts/deploy.py --repo /path/to/app --inputs /path/to/inputs.json
```

The local machine must already be on the tailnet and have the pinned toolchains,
Docker Compose and buildx installed. `--preflight-only` verifies the pinned SSH
connection and lists Aspire's pipeline without changing the deployment.

## Compose identity in Aspire 13.6.1

The [pinned Aspire implementation](https://github.com/dotnet/aspire/blob/3751e615ad660621f2a7aa4c390ef48e08a0eed8/src/Aspire.Hosting.Docker/DockerComposeEnvironmentResource.cs)
passes a checkout-path-derived name explicitly to Compose. `COMPOSE_PROJECT_NAME`
and Compose's `name:` cannot override that argument. There is no project-name
property in this version's public API.

`scripts/docker.py` adapts only the explicit Compose project argument to
`DEPLOY_PROJECT`, normally `<app>-<environment>`. It preserves the rest of
Aspire's deploy pipeline, including builds and connector startup, and rejects
missing, duplicate or foreign project arguments. Engine and build commands pass
through unchanged. The adapter provides deterministic names only. Deploy access
to this shared Docker daemon controls every stack, container, secret and volume. This belongs in deployment orchestration rather than an
AppHost extension because the same script works across AppHost languages.

The entrypoint also isolates Docker configuration and requires a pinned SSH host
key. It uses no SSH private keys. Tailscale authorizes the runner's ephemeral
identity, and the action removes it after the job.

## Validation

```sh
python3 -m unittest discover -s tests
scripts/lint-workflows.sh
```

Dependency upgrades must revalidate the Docker invocation contract and the live
deployment from a clean checkout before changing the tool pins.
