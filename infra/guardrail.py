#!/usr/bin/env python3
"""Create / update / publish / test an Amazon Bedrock Guardrail from YAML config.

The policy lives in config/guardrail.yml (deep-merged with config/<env>.yml):
    politics  -> denied topic "Politics"
    profanity -> AWS-managed PROFANITY word list
    rudeness  -> denied topic "Rudeness" + INSULTS content filter

Usage:
    python guardrail.py apply   [--env dev] [--publish] [--dry-run]
    python guardrail.py publish [--env dev]            # publish a new numbered version
    python guardrail.py show    [--env dev]            # id / arn / status / versions
    python guardrail.py test    [--env dev] [--version N] [TEXT ...]
    python guardrail.py delete  [--env dev] [--yes]

Credentials/region: --profile / --region, else config `aws:` section, else the
usual AWS_PROFILE / AWS_REGION environment and ~/.aws defaults.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from typing import Any

import boto3
import yaml
from botocore.exceptions import ClientError

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
BASE_CONFIG = "guardrail.yml"

# Bedrock limits (CreateGuardrail API).
MAX_TOPIC_NAME = 100
MAX_TOPIC_DEFINITION = 200
MAX_TOPIC_EXAMPLE = 100
MAX_TOPIC_EXAMPLES = 100
STRENGTHS = {"NONE", "LOW", "MEDIUM", "HIGH"}
PII_ACTIONS = {"BLOCK", "ANONYMIZE"}
READY_STATES = {"READY"}
FAILED_STATES = {"FAILED"}


# --------------------------------------------------------------------------- config


def load_config(env: str) -> dict:
    with open(os.path.join(CONFIG_DIR, BASE_CONFIG)) as f:
        config = yaml.safe_load(f) or {}
    env_file = os.path.join(CONFIG_DIR, f"{env}.yml")
    if os.path.exists(env_file):
        with open(env_file) as f:
            _deep_merge(config, yaml.safe_load(f) or {})
    return config


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# --------------------------------------------------------------------------- payload


def build_payload(config: dict) -> dict:
    """Translate the YAML config into the CreateGuardrail / UpdateGuardrail request body."""
    errors: list[str] = []
    payload: dict[str, Any] = {
        "name": _require(config, "name", errors),
        "description": config.get("description", "").strip(),
        "blockedInputMessaging": _require(config, "blocked_input_message", errors),
        "blockedOutputsMessaging": _require(config, "blocked_output_message", errors),
    }

    # Denied topics — politics, rudeness.
    topics = []
    for topic in config.get("denied_topics") or []:
        name = str(topic.get("name", "")).strip()
        definition = " ".join(str(topic.get("definition", "")).split())
        examples = [str(e).strip() for e in topic.get("examples") or []]
        if not name or len(name) > MAX_TOPIC_NAME:
            errors.append(f"topic name missing or > {MAX_TOPIC_NAME} chars: {name!r}")
        if not definition or len(definition) > MAX_TOPIC_DEFINITION:
            errors.append(
                f"topic {name!r}: definition must be 1-{MAX_TOPIC_DEFINITION} chars "
                f"(got {len(definition)})"
            )
        if len(examples) > MAX_TOPIC_EXAMPLES:
            errors.append(f"topic {name!r}: at most {MAX_TOPIC_EXAMPLES} examples")
        for ex in examples:
            if not ex or len(ex) > MAX_TOPIC_EXAMPLE:
                errors.append(f"topic {name!r}: example must be 1-{MAX_TOPIC_EXAMPLE} chars: {ex!r}")
        entry = {"name": name, "definition": definition, "type": "DENY"}
        if examples:
            entry["examples"] = examples
        topics.append(entry)
    if topics:
        payload["topicPolicyConfig"] = {"topicsConfig": topics}

    # Word filters — profanity (managed) + custom words.
    words = config.get("word_filters") or {}
    word_policy: dict[str, Any] = {}
    managed = [str(m).upper() for m in words.get("managed_lists") or []]
    if managed:
        word_policy["managedWordListsConfig"] = [{"type": m} for m in managed]
    custom = [str(w).strip() for w in words.get("custom_words") or [] if str(w).strip()]
    if custom:
        word_policy["wordsConfig"] = [{"text": w} for w in custom]
    if word_policy:
        payload["wordPolicyConfig"] = word_policy

    # Content filters — INSULTS backs rudeness; the rest are baseline.
    filters = []
    for cf in config.get("content_filters") or []:
        ftype = str(cf.get("type", "")).upper()
        in_s = str(cf.get("input", "HIGH")).upper()
        out_s = str(cf.get("output", "HIGH")).upper()
        if not ftype:
            errors.append("content filter without a type")
        if in_s not in STRENGTHS or out_s not in STRENGTHS:
            errors.append(f"content filter {ftype}: strength must be one of {sorted(STRENGTHS)}")
        filters.append({"type": ftype, "inputStrength": in_s, "outputStrength": out_s})
    if filters:
        payload["contentPolicyConfig"] = {"filtersConfig": filters}

    # Sensitive information — PII entities + regexes.
    pii = config.get("pii") or {}
    if pii.get("enabled", True):
        default_action = str(pii.get("default_action", "BLOCK")).upper()
        entities = []
        for ent in pii.get("entities") or []:
            if isinstance(ent, dict):
                etype = str(ent.get("type", "")).upper()
                action = str(ent.get("action", default_action)).upper()
            else:
                etype, action = str(ent).upper(), default_action
            if action not in PII_ACTIONS:
                errors.append(f"pii {etype}: action must be one of {sorted(PII_ACTIONS)}")
            entities.append({"type": etype, "action": action})
        regexes = []
        for rx in pii.get("regexes") or []:
            entry = {
                "name": rx["name"],
                "pattern": rx["pattern"],
                "action": str(rx.get("action", default_action)).upper(),
            }
            if rx.get("description"):
                entry["description"] = rx["description"]
            regexes.append(entry)
        sensitive: dict[str, Any] = {}
        if entities:
            sensitive["piiEntitiesConfig"] = entities
        if regexes:
            sensitive["regexesConfig"] = regexes
        if sensitive:
            payload["sensitiveInformationPolicyConfig"] = sensitive

    if errors:
        raise SystemExit("Config errors:\n  - " + "\n  - ".join(errors))
    return payload


def policy_fingerprint(payload: dict) -> str:
    """Short hash of the policy; stored in each published version's description so
    `publish` can skip re-publishing an unchanged DRAFT."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def _require(config: dict, key: str, errors: list[str]) -> str:
    value = str(config.get(key, "") or "").strip()
    if not value:
        errors.append(f"missing required config key: {key}")
    return value


# --------------------------------------------------------------------------- aws


class GuardrailClient:
    def __init__(self, profile: str | None, region: str | None):
        session = boto3.Session(profile_name=profile, region_name=region)
        self.region = session.region_name
        self.bedrock = session.client("bedrock")
        self.runtime = session.client("bedrock-runtime")

    def find_by_name(self, name: str) -> dict | None:
        paginator = self.bedrock.get_paginator("list_guardrails")
        for page in paginator.paginate():
            for g in page.get("guardrails", []):
                if g["name"] == name:
                    return g
        return None

    def versions(self, guardrail_id: str) -> list[dict]:
        """All published versions (excludes DRAFT), newest last."""
        paginator = self.bedrock.get_paginator("list_guardrails")
        out = []
        for page in paginator.paginate(guardrailIdentifier=guardrail_id):
            out.extend(g for g in page.get("guardrails", []) if g["version"] != "DRAFT")
        return sorted(out, key=lambda g: int(g["version"]))

    def wait_ready(self, guardrail_id: str, version: str = "DRAFT", timeout: int = 300) -> dict:
        deadline = time.time() + timeout
        while True:
            g = self.bedrock.get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion=version)
            status = g["status"]
            if status in READY_STATES:
                return g
            if status in FAILED_STATES:
                raise SystemExit(
                    f"Guardrail {guardrail_id} v{version} is {status}: "
                    + "; ".join(g.get("failureRecommendations") or g.get("statusReasons") or [])
                )
            if time.time() > deadline:
                raise SystemExit(f"Timed out waiting for guardrail {guardrail_id} (status {status})")
            time.sleep(3)

    def create(self, payload: dict, tags: dict) -> dict:
        kwargs = dict(payload, clientRequestToken=str(uuid.uuid4()))
        if tags:
            kwargs["tags"] = [{"key": k, "value": str(v)} for k, v in tags.items()]
        return self.bedrock.create_guardrail(**kwargs)

    def update(self, guardrail_id: str, arn: str, payload: dict, tags: dict) -> dict:
        resp = self.bedrock.update_guardrail(guardrailIdentifier=guardrail_id, **payload)
        if tags:
            self.bedrock.tag_resource(
                resourceARN=arn, tags=[{"key": k, "value": str(v)} for k, v in tags.items()]
            )
        return resp

    def publish(self, guardrail_id: str, description: str) -> str:
        resp = self.bedrock.create_guardrail_version(
            guardrailIdentifier=guardrail_id,
            description=description,
            clientRequestToken=str(uuid.uuid4()),
        )
        return resp["version"]

    def apply(self, guardrail_id: str, version: str, source: str, text: str) -> dict:
        return self.runtime.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source=source,
            content=[{"text": {"text": text}}],
        )

    def delete(self, guardrail_id: str) -> None:
        self.bedrock.delete_guardrail(guardrailIdentifier=guardrail_id)


# --------------------------------------------------------------------------- commands


def cmd_apply(args: argparse.Namespace, config: dict) -> int:
    payload = build_payload(config)
    tags = config.get("tags") or {}
    fingerprint = policy_fingerprint(payload)

    if args.dry_run:
        print(json.dumps({"payload": payload, "tags": tags, "fingerprint": fingerprint}, indent=2))
        return 0

    client = _client(args, config)
    existing = client.find_by_name(payload["name"])
    if existing:
        print(f"Updating guardrail {payload['name']} ({existing['id']}) in {client.region} ...")
        client.update(existing["id"], existing["arn"], payload, tags)
        guardrail_id, arn = existing["id"], existing["arn"]
    else:
        print(f"Creating guardrail {payload['name']} in {client.region} ...")
        resp = client.create(payload, tags)
        guardrail_id, arn = resp["guardrailId"], resp["guardrailArn"]

    client.wait_ready(guardrail_id)
    print(f"DRAFT ready: id={guardrail_id} arn={arn} policy={fingerprint}")

    version = "DRAFT"
    if args.publish:
        version = _publish(client, guardrail_id, fingerprint)

    _print_env(guardrail_id, version)
    return 0


def cmd_publish(args: argparse.Namespace, config: dict) -> int:
    payload = build_payload(config)
    client = _client(args, config)
    existing = _existing_or_exit(client, payload["name"])
    version = _publish(client, existing["id"], policy_fingerprint(payload))
    _print_env(existing["id"], version)
    return 0


def _publish(client: GuardrailClient, guardrail_id: str, fingerprint: str) -> str:
    description = f"policy {fingerprint}"
    published = client.versions(guardrail_id)
    if published and published[-1].get("description") == description:
        version = published[-1]["version"]
        print(f"Version {version} already carries policy {fingerprint}; not re-publishing.")
        return version
    print("Publishing new version ...")
    version = client.publish(guardrail_id, description)
    client.wait_ready(guardrail_id, version)
    print(f"Published version {version} ({description})")
    return version


def cmd_show(args: argparse.Namespace, config: dict) -> int:
    payload = build_payload(config)
    client = _client(args, config)
    existing = client.find_by_name(payload["name"])
    if not existing:
        print(f"No guardrail named {payload['name']} in {client.region}.")
        return 1
    draft = client.bedrock.get_guardrail(guardrailIdentifier=existing["id"], guardrailVersion="DRAFT")
    print(f"name:        {existing['name']}")
    print(f"id:          {existing['id']}")
    print(f"arn:         {existing['arn']}")
    print(f"region:      {client.region}")
    print(f"status:      {draft['status']}")
    print(f"updated:     {draft['updatedAt']}")
    print(f"local policy fingerprint: {policy_fingerprint(payload)}")
    versions = client.versions(existing["id"])
    print("versions:" if versions else "versions:    (none published — only DRAFT)")
    for v in versions:
        print(f"  v{v['version']:<4} {v['status']:<8} {v.get('description', '')}")
    if args.json:
        draft.pop("ResponseMetadata", None)
        print(json.dumps(draft, indent=2, default=str))
    return 0


def cmd_test(args: argparse.Namespace, config: dict) -> int:
    payload = build_payload(config)
    client = _client(args, config)
    existing = _existing_or_exit(client, payload["name"])
    version = args.version or _latest_version(client, existing["id"])

    if args.text:
        cases = [{"text": t, "source": args.source} for t in args.text]
    else:
        cases = config.get("tests") or []
        if not cases:
            raise SystemExit("No TEXT given and no `tests:` in config.")

    print(f"Testing {existing['name']} v{version} in {client.region} ({len(cases)} case(s))\n")
    failures = 0
    for case in cases:
        text = case["text"]
        source = str(case.get("source", "INPUT")).upper()
        expect = str(case.get("expect", "")).upper() or None
        resp = client.apply(existing["id"], version, source, text)
        blocked = resp["action"] == "GUARDRAIL_INTERVENED"
        actual = "BLOCK" if blocked else "ALLOW"
        reasons = _assessment_reasons(resp.get("assessments") or [])
        ok = expect is None or expect == actual
        failures += 0 if ok else 1
        mark = "  " if expect is None else ("PASS" if ok else "FAIL")
        print(f"{mark} [{source:<6}] {actual:<5} {text!r}")
        if reasons:
            print(f"        -> {', '.join(reasons)}")
    if failures:
        print(f"\n{failures} of {len(cases)} case(s) did not match expectation.")
        return 1
    print("\nAll cases matched." if any(c.get("expect") for c in cases) else "")
    return 0


def _assessment_reasons(assessments: list[dict]) -> list[str]:
    reasons = []
    for a in assessments:
        for t in a.get("topicPolicy", {}).get("topics", []):
            reasons.append(f"topic:{t['name']}")
        for f in a.get("contentPolicy", {}).get("filters", []):
            reasons.append(f"content:{f['type']}({f.get('confidence')})")
        wp = a.get("wordPolicy", {})
        for w in wp.get("managedWordLists", []):
            reasons.append(f"words:{w['type']}:{w.get('match')!r}")
        for w in wp.get("customWords", []):
            reasons.append(f"words:custom:{w.get('match')!r}")
        sp = a.get("sensitiveInformationPolicy", {})
        for p in sp.get("piiEntities", []):
            reasons.append(f"pii:{p['type']}")
        for r in sp.get("regexes", []):
            reasons.append(f"regex:{r['name']}")
    return reasons


def cmd_delete(args: argparse.Namespace, config: dict) -> int:
    payload = build_payload(config)
    client = _client(args, config)
    existing = _existing_or_exit(client, payload["name"])
    if not args.yes:
        answer = input(f"Delete guardrail {existing['name']} ({existing['id']}) and all versions? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return 1
    client.delete(existing["id"])
    print(f"Deleted {existing['name']} ({existing['id']}).")
    return 0


# --------------------------------------------------------------------------- helpers


def _client(args: argparse.Namespace, config: dict) -> GuardrailClient:
    aws = config.get("aws") or {}
    profile = args.profile or aws.get("profile") or os.environ.get("AWS_PROFILE")
    region = args.region or aws.get("region") or os.environ.get("AWS_REGION")
    try:
        return GuardrailClient(profile, region)
    except Exception as exc:  # noqa: BLE001 — surface credential/profile problems plainly
        raise SystemExit(f"Could not create AWS session (profile={profile!r}, region={region!r}): {exc}")


def _existing_or_exit(client: GuardrailClient, name: str) -> dict:
    existing = client.find_by_name(name)
    if not existing:
        raise SystemExit(f"No guardrail named {name} in {client.region}. Run `apply` first.")
    return existing


def _latest_version(client: GuardrailClient, guardrail_id: str) -> str:
    versions = client.versions(guardrail_id)
    return versions[-1]["version"] if versions else "DRAFT"


def _print_env(guardrail_id: str, version: str) -> None:
    print("\n# paste into app/ui/container/.env.local (and the query Lambda env):")
    print(f"GUARDRAIL_ID={guardrail_id}")
    print(f"GUARDRAIL_VERSION={version}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", default="dev", help="config/<env>.yml overlay (default: dev)")
    parser.add_argument("--profile", help="AWS profile (default: config aws.profile, then AWS_PROFILE)")
    parser.add_argument("--region", help="AWS region (default: config aws.region, then AWS_REGION)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("apply", help="create the guardrail, or update its DRAFT if it already exists")
    p.add_argument("--publish", action="store_true", help="also publish a numbered version")
    p.add_argument("--dry-run", action="store_true", help="print the API payload; call nothing")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("publish", help="publish the current DRAFT as a new numbered version")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("show", help="print id / arn / status / published versions")
    p.add_argument("--json", action="store_true", help="also dump the DRAFT definition as JSON")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("test", help="run ApplyGuardrail on config `tests:` or the given TEXT")
    p.add_argument("text", nargs="*", metavar="TEXT")
    p.add_argument("--version", help="guardrail version to test (default: latest published, else DRAFT)")
    p.add_argument("--source", default="INPUT", choices=["INPUT", "OUTPUT"], help="for TEXT args")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("delete", help="delete the guardrail and all its versions")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(func=cmd_delete)

    args = parser.parse_args(argv)
    config = load_config(args.env)
    try:
        return args.func(args, config)
    except ClientError as exc:
        err = exc.response.get("Error", {})
        raise SystemExit(f"AWS error {err.get('Code')}: {err.get('Message')}")


if __name__ == "__main__":
    sys.exit(main())
