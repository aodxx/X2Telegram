import json
import sys
from .urls import parse_batch

def main():
    raw=sys.stdin.read(); posts=parse_batch(raw)
    print(json.dumps({"status":"parsed","input_count":len(raw.splitlines()),"valid_unique_posts":len(posts),"posts":[{"username":p.username,"post_id":p.post_id,"source_url":p.normalized_url} for p in posts]},ensure_ascii=False,indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
