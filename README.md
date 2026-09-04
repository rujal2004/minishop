# MiniShop

MiniShop is a deliberately small Flask shop for learning Datadog logs, APM,
custom metrics, and monitors. It has only login, products, and checkout flows.

## Run locally

Requirements: Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open http://127.0.0.1:5000/login (or the forwarded port URL in Codespaces). The
seed users are `alice/password` and
`bob/password`. Products are seeded automatically in `minishop.db`.

Routes: `/login`, `/products`, `/checkout`, `/api/login`, `/api/products`,
`/api/checkout`, `/api/health`, `/api/slow`, and `/api/error`.

## Datadog setup

The app writes JSON logs to stdout and sends DogStatsD counters over UDP. It
does not include RUM.

### 1. Install and configure the Agent

Install the Datadog Agent using the [Agent install documentation](https://docs.datadoghq.com/agent/),
providing `DD_API_KEY` and your Datadog site. Ensure the Agent is running with
DogStatsD enabled on UDP port `8125` (the default). Set `DD_AGENT_HOST` in
`.env` if the Agent is not local.

### 2. Send application logs

Every log line is a JSON object on stdout. Configure the Agent Logs agent to
collect this process output, or redirect stdout to a file and add:

```yaml
logs:
	- type: file
		path: /absolute/path/to/minishop.log
		service: minishop
		source: python
```

Enable JSON parsing. Useful facets include `endpoint`, `user_id`, `status`,
and `duration_ms`.

### 3. Enable APM with ddtrace

```bash
pip install ddtrace
DD_SERVICE=minishop DD_ENV=dev DD_VERSION=1.0 ddtrace-run python app.py
```

`ddtrace-run` automatically instruments Flask and SQLAlchemy. The application
does not require ddtrace for normal local runs.

### 4. Send custom metrics with StatsD

Set these values in `.env` (the defaults target a local Agent):

```dotenv
DD_AGENT_HOST=127.0.0.1
DD_DOGSTATSD_PORT=8125
DD_STATSD_ENABLED=true
```

Metrics Explorer names are `minishop.app.requests`,
`minishop.app.login.success`, `minishop.app.login.failure`,
`minishop.app.checkout.success`, and `minishop.app.checkout.failure`.

### 5. Build a dashboard

Add widgets for request rate (`sum:minishop.app.requests{*}.as_rate()` grouped
by endpoint), API error rate (APM 5xx rate or log count of `status:5xx`), p95
latency (APM service `minishop`), login failures
(`sum:minishop.app.login.failure{*}`), and successful checkout count
(`sum:minishop.app.checkout.success{*}`). `/api/slow` is useful for testing
latency.

### 6. Create monitors

Create an API error monitor for 5xx responses from service `minishop`, a p95
latency monitor above a threshold such as one second, and a failed-login metric
monitor such as `sum:minishop.app.login.failure{*}` above 5 in five minutes.
Include the endpoint in notifications so the failing route is visible.