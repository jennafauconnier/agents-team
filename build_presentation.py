"""Génère docs/index.html depuis presentation.html + un run : python3 build_presentation.py demo   (ou out/<run>)"""
import json, os, re, sys
R = sys.argv[1].rstrip("/") + "/"
rd = lambda p: open(R + p).read()
t = rd("work/test_cart.py")
labels = {"TestAdd": "Ajout", "TestUpdate": "Mise à jour", "TestRemove": "Suppression",
          "TestReconcile": "Stock, prix, totaux", "TestIntegration": "Parcours complet"}
parts = {c.split("(")[0]: c for c in re.split(r"^class ", t, flags=re.M)[1:]}
groups = [{"label": labels[n], "tests": re.findall(r"def (test_\w+)", parts[n])} for n in labels]
po = rd("2-PO.md"); i = po.index("## Story 1")
tl = rd("3-TECH_LEAD.md")
c = rd("work/cart.py"); k = c.index("def add(")
code = c[k:c.index("\n\n\ndef ", k)].strip() + "\n\n# --- et son test ---\n" + \
    re.search(r"    def test_add_out_of_stock.*?\n\n", t, re.S).group(0).replace("    ", "", 1).strip()
tests = "python3 -m unittest discover -v\n\n" + "\n".join(
    l for l in rd("6-TESTS.md").split("\n") if "ok" in l or l.startswith(("Ran", "OK", "---")))[-1800:]
data = {"pm": "\n".join(rd("1-PM.md").strip().split("\n")[:6]), "po": po[i:po.index("**CA3")].strip(),
        "tl": tl[:tl.index("**Formats**")].strip(), "code": code,
        "front": "\n".join(rd("work/app.js").split("\n")[:28]).strip(), "testout": tests,
        "qa": rd("7-QA.md").strip()[:200], "groups": groups}
mods = json.load(open("models.team.openrouter.json"))
roles = {"deepseek": "PM, PO et devs (exécution)", "mimo": "devs après un KO (monte d'un cran)", "hy4": "Tech Lead et QA (conception, vérification)"}
data["budget"] = {"cap": 0.50,
    "models": [{**m, "role": next(v for k, v in roles.items() if k in m["id"])} for m in mods],
    # coûts relevés dans le terminal, runs OpenRouter
    "runs": [{"label": "Bouton + compteur", "cost": 0.00697, "ok": True, "rounds": 1},
             {"label": "Bouton + compteur, QA strict", "cost": 0.02723, "ok": False, "rounds": 4},
             {"label": "Panier, QA strict", "cost": 0.07345, "ok": False, "rounds": 4},
             {"label": "Panier, QA strict, 5 corrections", "cost": 0.07838, "ok": False, "rounds": 6}]}
if os.path.exists(R + "run.json"):
    data["run"] = json.load(open(R + "run.json"))
page = open("presentation.html").read().replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w").write('<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n' + page + "\n</body>\n</html>\n")
