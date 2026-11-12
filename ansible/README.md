# CodeGuessr CI/CD (Ansible; no Docker Compose on production)

GitHub Actions runs tests and Docker Compose smoke tests on every PR to `master` and
push to `master`. For non-draft PRs **from branches inside this repository** it
builds and pushes commit-tagged Docker images and redeploys production using Ansible.
The same happens after merging into `master`. Fork PRs run tests only, without access
to secrets. A manual `workflow_dispatch` is also available.

Images:

- `divancode74/codeguessr-backend:<40-character git SHA>`
- `divancode74/codeguessr-frontend:<40-character git SHA>`

**Warning:** A PR deployment replaces the live production version with unmerged
code. Anyone able to push to trusted repository branches may be able to run code
inside the privileged GitHub runner, so grant write access only to people you trust
with the deployment secrets. For a strict production-only policy, deploy only after
merging to `master` by removing the PR condition from the `build` job.

## Configure repository secrets and variables

In **Settings → Secrets and variables → Actions**, add:

| Type | Name | Meaning |
| --- | --- | --- |
| Secret (required) | `DOCKERHUB_TOKEN` | Docker Hub access token with write access to `codeguessr-*` repositories; also used to pull images on the server |
| Secret (required) | `SSH_PASSWORD` | Password for the SSH user in `ansible/deploy/inventory` (defaults to `root`) |
| Secret (optional) | `GITHUB_API_TOKEN` | Fine-grained GitHub personal access token, read-only where possible, passed to Backend as `GITHUB_TOKEN` |
| Variable (required) | `SSH_KNOWN_HOSTS` | **Verified** public SSH host key line, e.g. `201.34.148.71 ssh-ed25519 AAAA...` |
| Variable (optional) | `DOCKERHUB_USERNAME` | Docker Hub namespace (defaults to `divancode74`) |

Use **Secrets**, not plain Actions Variables, for tokens and passwords. The
`GITHUB_API_TOKEN` is **not** `${{ secrets.GITHUB_TOKEN }}`, which is the short-lived
automatic token for GitHub Actions itself. `GITHUB_API_TOKEN` is optional; with no
token, the Backend can still use GitHub's unauthenticated public API with lower limits.

`SSH_KNOWN_HOSTS` is a public *server host key*, used to verify the SSH endpoint.
It is not your SSH private login key. Because authentication here uses a password,
`SSH_PRIVATE_KEY` is not needed. To obtain a **candidate** entry:

```bash
ssh-keyscan -t ed25519 201.34.148.71
```

Verify the key fingerprint through the server console or another trusted channel;
do **not** blindly trust the value from `ssh-keyscan`.

The domain is **not secret** and is configured in `ansible/deploy/playbook.yml`
as `guessr.coduels.pro`. The public production host is specified in
`ansible/deploy/inventory`. No `ansible/credentials.yml`, Ansible Vault, Vault
password or production `.env` file is needed.

For **local development only**, `compose.yaml` continues reading `.env` from
`.env.example`. This does not conflict with injecting `GITHUB_API_TOKEN` as the
`GITHUB_TOKEN` container environment variable during production deployment.

## Server prerequisites

On `201.34.148.71`:

1. Install Docker Engine, Python 3 and the Python `requests` package (on Ubuntu,
   `sudo apt-get install python3-requests`), and make sure the daemon is running.
2. Enable SSH password authentication for the account configured in the inventory;
   `root` login must be enabled if you retain the default user. Prefer a dedicated
   deploy account with narrowly scoped access where practical.
3. Open TCP 80/443 and UDP 443. DNS for `guessr.coduels.pro` must resolve to the
   server for Caddy's automatic HTTPS certificates. Nothing else can bind ports
   80/443. If an old Compose deployment exists, stop it with `docker compose down`
   (not `down -v`) before the first Ansible deployment.
4. If you use GitHub Environment `production` protection rules, ensure they permit
   the intended deployments (including PR branches if you keep PR deployment).

## Workflow and playbooks

GitHub Actions automatically installs Ansible, `sshpass` and the required
`community.docker` collection on its runners. The production host requires Docker
Engine, not Python-based Ansible; the playbook uses Docker's CLI for pulls and the
collection for container management.

The playbooks follow the CoDuels pattern: build/push on the GitHub runner,
Ansible connects over SSH and directly creates two Docker networks and manages
Backend, Frontend and Caddy containers (no Compose on production). The existing
Nginx-to-Backend and Caddy-to-Frontend service DNS names are retained via network
aliases. Caddy TLS state is persisted under `/opt/codeguessr/caddy`.

To build or deploy manually, set the same environment variables locally:

```bash
python3 -m pip install 'ansible-core==2.18.11'
ansible-galaxy collection install -r ansible/requirements.yml
# on Debian/Ubuntu: sudo apt-get install sshpass

export DOCKERHUB_TOKEN='...'
export SSH_PASSWORD='...'
export SSH_KNOWN_HOSTS='201.34.148.71 ssh-ed25519 <verified-base64-key>'
# optionally: export GITHUB_API_TOKEN='...'

ansible-playbook -i ansible/build/inventory ansible/build/playbook.yml \
  --extra-vars "version=$(git rev-parse HEAD)"
ansible-playbook -i ansible/deploy/inventory ansible/deploy/playbook.yml \
  --extra-vars "version=$(git rev-parse HEAD)"
```

Roll back by deploying an earlier SHA already present on Docker Hub. Every
published tag identifies a specific commit (no `latest`). Deployments briefly
restart containers, and automatic rollback is not implemented. If your server
already hosts a reverse proxy on ports 80/443, integrate with that proxy rather
than starting another Caddy on the same ports.
