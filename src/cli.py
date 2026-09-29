import argparse
import json
import sys
from .config import Config
from .metadata import YtDlpMetadataProvider
from .processor import PostProcessor
from .urls import parse_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Send public X post media to Telegram")
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()
    raw = sys.stdin.read()
    posts = parse_batch(raw)
    payload = {"status": "completed", "input_count": len(raw.splitlines()),
               "valid_unique_posts": len(posts), "results": []}
    if args.parse_only:
        payload["results"] = [{"username": p.username, "post_id": p.post_id,
                                "source_url": p.normalized_url, "status": "ready"} for p in posts]
    else:
        try:
            config = Config.from_env()
            worker = PostProcessor(config, YtDlpMetadataProvider(config.timeout_seconds))
            payload["results"] = [worker.process(post).__dict__ for post in posts]
            for item in payload["results"]:
                item["status"] = item["status"].value
        except Exception as exc:
            payload["status"] = "configuration_error"
            payload["error"] = str(exc)
    output = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(output)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
