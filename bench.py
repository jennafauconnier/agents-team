"""llm-bench : compare des LLM sur TES cas, en coût par tâche réussie,
et mesure le gain d'un routeur "moins cher d'abord".

    export OPENROUTER_API_KEY=...
    python3 bench.py            # appelle les vrais modèles (réponses mises en cache)
"""
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / ".cache"


def call_openrouter(model, prompt):
    """Retourne {"text", "in", "out"}. Cache disque : un même appel n'est payé qu'une fois."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / hashlib.sha256(f"{model}|{prompt}".encode()).hexdigest()
    if f.exists():
        cached = json.loads(f.read_text())
        if (cached["text"] or "").strip():  # ignore d'anciennes réponses vides mises en cache
            return cached
    # OPENAI_API_KEY -> API OpenAI directe ; sinon OPENROUTER_API_KEY -> OpenRouter
    if "OPENAI_API_KEY" in os.environ:
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")  # serveur compatible OpenAI (optionnel)
        url, key = base + "/chat/completions", os.environ["OPENAI_API_KEY"]
        # modèles "reasoning" : le raisonnement consomme des tokens ; MAX_TOKENS pour changer la limite
        n = int(os.environ.get("MAX_TOKENS", 4000))
        limit = {"max_tokens": n} if "OPENAI_BASE_URL" in os.environ else {"max_completion_tokens": n}
    elif "OPENROUTER_API_KEY" in os.environ:
        url, key = "https://openrouter.ai/api/v1/chat/completions", os.environ["OPENROUTER_API_KEY"]
        # le raisonnement mange les tokens (réponse vide) : désactivé par défaut
        limit = {"max_tokens": int(os.environ.get("MAX_TOKENS", 4000)),
                 "reasoning": {"enabled": False}}  # REASONING_EFFORT=low|medium|high pour le laisser réfléchir
    else:
        raise RuntimeError("Aucune clé : fais `export OPENAI_API_KEY=...` (ou OPENROUTER_API_KEY) dans ce terminal.")
    if "REASONING_EFFORT" in os.environ and "reasoning" in limit:
        limit["reasoning"] = {"effort": os.environ["REASONING_EFFORT"]}
    timeout = int(os.environ.get("TIMEOUT", 180))  # secondes ; les modèles "reasoning" sont lents

    def post(extra):
        req = urllib.request.Request(
            url,
            data=json.dumps({"model": model, **extra,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    try:
        try:
            r = post(limit)
        except urllib.error.HTTPError as e:
            if e.code != 400 or "reasoning" not in limit:
                raise
            r = post({k: v for k, v in limit.items() if k != "reasoning"})  # ce modèle refuse de couper le raisonnement
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} pour {model} : {e.read().decode()[:400]}")
    except OSError as e:  # timeout, réseau coupé…
        raise RuntimeError(f"{model} : {type(e).__name__} après {timeout}s max (export TIMEOUT=300 pour attendre plus)")
    out = {"text": r["choices"][0]["message"].get("content") or "",
           "in": r["usage"]["prompt_tokens"], "out": r["usage"]["completion_tokens"]}
    if out["text"].strip():  # une réponse vide (modèle "reasoning" à court de tokens) n'est pas mise en cache
        f.write_text(json.dumps(out))
    return out


def price(model, r):
    """Coût $ d'une réponse. model = {"in": $/M, "out": $/M}."""
    return (r["in"] * model["in"] + r["out"] * model["out"]) / 1e6


def passes(case, text):
    return case["expected"].lower() in text.lower()


def bench(models, cases, call):
    """Chaque modèle sur chaque cas -> stats par modèle."""
    stats = {}
    for m in models:
        ok = spent = 0
        for c in cases:
            r = call(m["id"], c["prompt"])
            spent += price(m, r)
            ok += passes(c, r["text"])
            print(f"  {m['id']}: {c['prompt'][:30]!r} -> {r['text'][:40]!r}", file=sys.stderr, flush=True)
        stats[m["id"]] = {"ok": ok, "n": len(cases), "cost": spent,
                          "cost_per_success": spent / ok if ok else float("inf")}
    return stats


def route(models, cases, call):
    """Essaie les modèles du moins cher au plus cher, s'arrête au 1er qui passe."""
    ordered = sorted(models, key=lambda m: m["in"] + m["out"])
    ok = spent = 0
    for c in cases:
        for m in ordered:
            r = call(m["id"], c["prompt"])
            spent += price(m, r)
            if passes(c, r["text"]):
                ok += 1
                break
    return {"ok": ok, "n": len(cases), "cost": spent,
            "cost_per_success": spent / ok if ok else float("inf")}


def report(stats, routed):
    print(f"{'modèle':40} {'réussite':>9} {'coût $':>10} {'$/succès':>10}")
    for k, s in stats.items():
        print(f"{k:40} {s['ok']:>4}/{s['n']:<4} {s['cost']:>10.5f} {s['cost_per_success']:>10.5f}")
    s = routed
    print(f"{'ROUTEUR (cheap -> gros)':40} {s['ok']:>4}/{s['n']:<4} {s['cost']:>10.5f} {s['cost_per_success']:>10.5f}")


if __name__ == "__main__":
    # usage : python3 bench.py [fichier_modeles.json]  (défaut : models.json)
    models = json.loads((HERE / (sys.argv[1] if len(sys.argv) > 1 else "models.json")).read_text())
    cases = json.loads((HERE / "cases.json").read_text())
    try:
        report(bench(models, cases, call_openrouter), route(models, cases, call_openrouter))
    except RuntimeError as e:
        sys.exit(str(e))
