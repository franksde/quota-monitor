from unittest.mock import patch, MagicMock
from quota_monitor.cli._wrangler import deploy_cf_relay, prepare_cf_relay_workdir


def _ok(stdout=""):
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def test_prepare_cf_relay_workdir_copies_bundled_worker_files(tmp_path):
    relay_dir = prepare_cf_relay_workdir(tmp_path / "relay-workdir")

    assert (relay_dir / "wrangler.toml.example").exists()
    assert (relay_dir / "package.json").exists()
    assert (relay_dir / "src" / "worker.js").exists()
    assert "SCHEDULE_TOMBSTONE" in (relay_dir / "wrangler.toml.example").read_text()
    assert "ALERTS_QUEUE" in (relay_dir / "src" / "worker.js").read_text()


def test_deploy_pushes_secrets_and_deploys(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text(
        'name = "qm-relay"\nmain = "src/worker.js"\n\n[[queues.producers]]\nqueue = "quota-monitor-alerts"\nbinding = "ALERTS_QUEUE"\n'
    )
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["wrangler", "worker"] and "list" in cmd:
            return _ok(stdout='[]\n')
        if cmd[:2] == ["wrangler", "deploy"]:
            return _ok(stdout='Published https://qm-relay-frank.workers.dev\n')
        return _ok()

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url == "https://qm-relay-frank.workers.dev"
    toml = (relay_dir / "wrangler.toml").read_text()
    assert "ALERTS_QUEUE" in toml
    secret_cmds = [c for c in calls if c[:3] == ["wrangler", "secret", "put"]]
    assert any("TELEGRAM_BOT_TOKEN" in c for c in secret_cmds)
    assert any("TELEGRAM_CHAT_ID" in c for c in secret_cmds)


def test_deploy_returns_none_on_wrangler_failure(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text('name = "qm-relay"\n')

    def fake_run(cmd, **kw):
        if cmd[:2] == ["wrangler", "worker"] and "list" in cmd:
            return _ok(stdout='[]\n')
        return MagicMock(returncode=1, stdout="", stderr="boom")

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url is None


# Wrangler 4.x prints a banner before the JSON payload on stdout. The setup
# wizard must tolerate this when parsing `kv namespace list` output, otherwise
# the KV binding never reaches wrangler.toml and the deployed worker silently
# loses tombstone-based dedupe (resulting in duplicate "quota recovered"
# notifications — observed in the field on 2026-05-18).
WRANGLER4_LIST_OUTPUT = '''
 ⛅️ wrangler 4.92.0
 ───────────────────
[
  {
    "id": "ebec9f4d55d64ee7b296cccf36c8b7b1",
    "title": "ALERTS_KV",
    "supports_url_encoding": true
  },
  {
    "id": "aba6d133976c45d6b19ea2efcd305ebe",
    "title": "SCHEDULE_TOMBSTONE",
    "supports_url_encoding": true
  }
]
'''

WRANGLER4_CREATE_TOML_OUTPUT = '''
 ⛅️ wrangler 4.92.0
 ───────────────────
🌀 Creating namespace with title "SCHEDULE_TOMBSTONE"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
[[kv_namespaces]]
binding = "SCHEDULE_TOMBSTONE"
id = "1234567890abcdef1234567890abcdef"
'''


def _write_example_toml(relay_dir):
    (relay_dir / "wrangler.toml.example").write_text(
        'name = "qm-relay"\nmain = "src/worker.js"\n\n'
        '[[queues.producers]]\nqueue = "quota-monitor-alerts"\nbinding = "ALERTS_QUEUE"\n'
    )


def test_kv_binding_written_when_create_succeeds(tmp_path):
    """Happy path: fresh `wrangler kv namespace create` with banner-prefixed
    TOML output. Regex must still extract the id."""
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    _write_example_toml(relay_dir)

    def fake_run(cmd, **kw):
        if cmd[:2] == ["wrangler", "worker"] and "list" in cmd:
            return _ok(stdout='[]\n')
        if cmd[1:4] == ["kv", "namespace", "create"]:
            return _ok(stdout=WRANGLER4_CREATE_TOML_OUTPUT)
        if cmd[:2] == ["wrangler", "deploy"]:
            return _ok(stdout='Published https://qm-relay.workers.dev\n')
        return _ok()

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )

    toml = (relay_dir / "wrangler.toml").read_text()
    assert 'binding = "SCHEDULE_TOMBSTONE"' in toml
    assert 'id = "1234567890abcdef1234567890abcdef"' in toml


def test_kv_binding_recovered_when_namespace_already_exists(tmp_path):
    """Reproduces the 2026-05-18 production bug: `kv namespace create` returns
    'already exists', wizard falls back to `kv namespace list`, but wrangler
    4.x prefixes the JSON array with a banner so `json.loads` would throw.
    The wizard must still extract the id and write the KV binding to
    wrangler.toml — otherwise the worker is deployed without dedupe and the
    user gets duplicate notifications at reset time."""
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    _write_example_toml(relay_dir)

    create_err = (
        '✘ [ERROR] A KV namespace with the title "SCHEDULE_TOMBSTONE" '
        'already exists.\n'
    )

    def fake_run(cmd, **kw):
        if cmd[:2] == ["wrangler", "worker"] and "list" in cmd:
            return _ok(stdout='[]\n')
        if cmd[1:4] == ["kv", "namespace", "create"]:
            return MagicMock(returncode=1, stdout="", stderr=create_err)
        if cmd[1:4] == ["kv", "namespace", "list"]:
            return _ok(stdout=WRANGLER4_LIST_OUTPUT)
        if cmd[:2] == ["wrangler", "deploy"]:
            return _ok(stdout='Published https://qm-relay.workers.dev\n')
        return _ok()

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )

    toml = (relay_dir / "wrangler.toml").read_text()
    assert 'binding = "SCHEDULE_TOMBSTONE"' in toml
    assert 'id = "aba6d133976c45d6b19ea2efcd305ebe"' in toml
