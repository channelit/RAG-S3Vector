"""Ask the Bedrock Flow one question from the command line.

The flow (iac/resources/resource_flow.py) classifies the question and answers
it from the knowledge base for that category: CSMS messages, or the scraper's
collection statistics. InvokeFlow is a streaming API that the AWS CLI cannot
call, so this script is the way to try the deployed flow:

    python backend/flow_ask.py "How many CSMS messages are there?"
    python backend/flow_ask.py --trace "What changed for Entry Type 13?"
    python backend/flow_ask.py --alias-id TSTALIASID "..."     # the flow's working draft

Usage (from app/ui/container, reads .env.local for FLOW_ID, FLOW_ALIAS_ID and
AWS_PROFILE; the stack's ContainerUiEnv output has both IDs).

It only invokes the flow and prints what comes back. The answer is text only:
a flow's knowledge base node returns no citations and takes no date filter.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from kb_report import load_env_file

INPUT_NODE = "FlowInputNode"       # node names set in iac/resources/resource_flow.py
OUTPUT_NODE_PREFIX = "Output_"     # Output_<route>: the output node names the route that answered


def ask(client, flow_id: str, alias_id: str, question: str, trace: bool = False) -> dict:
    """Invoke the flow once. Returns {route, answer, completion, trace}."""
    response = client.invoke_flow(
        flowIdentifier=flow_id,
        flowAliasIdentifier=alias_id,
        enableTrace=trace,
        inputs=[{"nodeName": INPUT_NODE, "nodeOutputName": "document", "content": {"document": question}}],
    )
    result: dict = {"route": None, "answer": None, "completion": None, "trace": []}
    for event in response["responseStream"]:
        if "flowOutputEvent" in event:
            output = event["flowOutputEvent"]
            node = output["nodeName"]
            result["route"] = node.removeprefix(OUTPUT_NODE_PREFIX)
            result["answer"] = output["content"]["document"]
        elif "flowCompletionEvent" in event:
            result["completion"] = event["flowCompletionEvent"]["completionReason"]
        elif "flowTraceEvent" in event:
            step = event["flowTraceEvent"]["trace"]
            if "nodeOutputTrace" in step:
                node = step["nodeOutputTrace"]
                for output_field in node.get("fields", []):
                    result["trace"].append(
                        f"{node['nodeName']}.{output_field['nodeOutputName']} = "
                        f"{output_field.get('content', {}).get('document')!r}"
                    )
            elif "conditionNodeResultTrace" in step:
                node = step["conditionNodeResultTrace"]
                satisfied = [c["conditionName"] for c in node.get("satisfiedConditions", [])]
                result["trace"].append(f"{node['nodeName']} satisfied: {', '.join(satisfied)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--flow-id", default=None, help="defaults to $FLOW_ID")
    parser.add_argument("--alias-id", default=None, help="defaults to $FLOW_ALIAS_ID")
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parent.parent / ".env.local")
    parser.add_argument("--trace", action="store_true",
                        help="also print what the classifier replied and which condition matched")
    args = parser.parse_args()

    load_env_file(args.env_file)
    flow_id = args.flow_id or os.environ.get("FLOW_ID")
    alias_id = args.alias_id or os.environ.get("FLOW_ALIAS_ID")
    if not flow_id or not alias_id:
        parser.error("FLOW_ID and FLOW_ALIAS_ID are required (env, .env.local or --flow-id / --alias-id)")

    session = boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE") or None,
        region_name=os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or None,
    )
    try:
        result = ask(session.client("bedrock-agent-runtime"), flow_id, alias_id, args.question, trace=args.trace)
    except (BotoCoreError, ClientError) as exc:
        # Includes errors raised while reading the stream, such as a node that failed.
        print(f"Flow invocation failed: {exc}", file=sys.stderr)
        return 1

    for line in result["trace"]:
        print(f"trace:  {line}")
    print(f"route:  {result['route']}")
    print(f"answer: {result['answer']}")
    if result["completion"] != "SUCCESS":
        print(f"completion: {result['completion']}", file=sys.stderr)
    return 0 if result["answer"] is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
