import json

p = "data/skill_cache.json"
d = json.load(open(p))
bad = [k for k, v in d["cache"].items() if "teams" in v.get("skill_id", "")]
for k in bad:
    d["cache"].pop(k)
json.dump(d, open(p, "w"), indent=2)
print(f"Removed {len(bad)} Teams entries, {len(d['cache'])} remaining")
