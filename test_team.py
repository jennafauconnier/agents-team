"""Test hors-ligne : faux modèles. QA refuse une fois, puis accepte ; le budget coupe les boucles."""
import team

models = [{"id": "petit", "in": 0.1, "out": 0.4}, {"id": "moyen", "in": 1, "out": 2}, {"id": "gros", "in": 5, "out": 25}]
calls = []


def fake(mid, prompt):
    role = next(r for r, p in team.PROMPTS.items() if prompt.startswith(p))
    calls.append((role, mid))
    n_qa = sum(1 for r, _ in calls if r == "QA")
    text = ("VERDICT: KO\nbug FRONT" if n_qa == 1 else "VERDICT: OK") if role == "QA" else f"doc {role}"
    return {"text": text, "in": 1000, "out": 100}


res = team.run_team("demande", models, fake, log=lambda *_: None)
roles = [r for r, _ in calls]
assert res["approved"], res
assert [r["approved"] for r in res["rounds"]] == [False, True] and res["rounds"][0]["front"] == "KO"  # historique des tours
assert [c["role"] for c in res["calls"]][:3] == ["PM", "PO", "TECH_LEAD"]
assert roles.count("QA") == 2 and roles.count("DEV_FRONT") == 2 and roles.count("DEV_BACK") == 2
first = {r: m for r, m in reversed(calls)}  # 1er modèle utilisé par rôle
assert first["PM"] == "petit" and first["TECH_LEAD"] == "gros" and first["DEV_BACK"] == "petit"
assert [m for r, m in calls if r == "DEV_FRONT"] == ["petit", "moyen"]  # la correction monte d'un cran

# sans correction autorisée : un KO reste NON approuvé
calls.clear()
assert not team.run_team("demande", models, fake, max_fix=0, log=lambda *_: None)["approved"]
assert [r for r, _ in calls].count("DEV_FRONT") == 1

# budget : un plafond minuscule coupe le run
try:
    team.run_team("demande", models, fake, budget=0.0001, log=lambda *_: None)
    assert False, "le budget aurait dû couper"
except RuntimeError as e:
    assert "Budget" in str(e)
# réponse vide : 1 réessai suffit, mais un agent muet arrête l'équipe au lieu de propager du vide
seen = {"n": 0}


def flaky(mid, prompt):
    r = fake(mid, prompt)
    if prompt.startswith(team.PROMPTS["PO"]):
        seen["n"] += 1
        if seen["n"] == 1:
            r["text"] = ""
    return r


calls.clear()
assert team.run_team("demande", models, flaky, log=lambda *_: None)["docs"]["PO"] == "doc PO"
try:
    team.run_team("demande", models, lambda m, p: {"text": " ", "in": 1, "out": 1}, log=lambda *_: None)
    assert False, "un agent muet aurait dû arrêter l'équipe"
except RuntimeError as e:
    assert "répondu vide" in str(e)

# modèle en panne (timeout) : l'équipe passe au suivant au lieu de planter
calls.clear()


def down(mid, prompt):
    if mid == "petit":
        raise RuntimeError("timeout simulé")
    return fake(mid, prompt)


res = team.run_team("demande", models, down, log=lambda *_: None)
assert res["approved"] and res["docs"]["PM"] == "doc PM"

# QA ne blâme que le BACK -> seul DEV_BACK est relancé ; les tests rouges priment sur un QA qui dit OK
def scripted(qa_texts, plan="## API\napi\n## FRONT\nftask\n## BACK\nbtask"):
    seen = {"DEV_FRONT": [], "DEV_BACK": []}
    def f(mid, prompt):
        role = next(r for r, p in team.PROMPTS.items() if prompt.startswith(p))
        calls.append((role, mid))
        if role in seen:
            seen[role].append(prompt)
        text = {"TECH_LEAD": plan}.get(role, f"doc {role}")
        if role == "QA":
            text = qa_texts.pop(0)
        return {"text": text, "in": 1000, "out": 100}
    return f, seen


calls.clear()
f, seen = scripted(["VERDICT: KO\nFRONT: OK\nBACK: KO\nbug", "VERDICT: OK\nFRONT: OK\nBACK: OK"])
assert team.run_team("demande", models, f, log=lambda *_: None)["approved"]
roles = [r for r, _ in calls]
assert roles.count("DEV_BACK") == 2 and roles.count("DEV_FRONT") == 1
assert "btask" in seen["DEV_BACK"][0] and "ftask" not in seen["DEV_BACK"][0] and "api" in seen["DEV_BACK"][0]  # chaque dev ne voit que sa part

calls.clear()
f, _ = scripted(["VERDICT: OK\nFRONT: OK\nBACK: OK", "VERDICT: OK\nFRONT: OK\nBACK: OK"])
runs = iter([(False, "FAIL test_x"), (True, "OK")])
res = team.run_team("demande", models, f, log=lambda *_: None, check=lambda fr, ba: next(runs))
assert res["approved"] and [r for r, _ in calls].count("DEV_BACK") == 2 and res["docs"]["TESTS"] == "OK"
calls.clear()
f, _ = scripted(["VERDICT: OK\nFRONT: OK\nBACK: OK"])
assert not team.run_team("demande", models, f, max_fix=0, log=lambda *_: None, check=lambda fr, ba: (False, "boom"))["approved"]

# écriture des fichiers + vrais tests exécutés (chemin hors dossier refusé)
import tempfile
from pathlib import Path
reply = ("### FILE: cart.py\n```python\ndef add(a, b):\n    return a + b\n```\n"
         "### FILE: test_cart.py\n```python\nimport unittest, cart\n\n\nclass T(unittest.TestCase):\n"
         "    def test_add(self):\n        self.assertEqual(cart.add(1, 2), %s)\n```\n"
         "### FILE: ../evil.py\n```python\nprint(1)\n```")
for expected, want in (("3", True), ("4", False)):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "work"
        root.mkdir()
        team.write_files(reply % expected, root)
        assert not (Path(d) / "evil.py").exists()
        ok, out = team.run_tests(root)
        assert ok is want, out
with tempfile.TemporaryDirectory() as d:  # tests rangés dans un sous-dossier : trouvés quand même
    root = Path(d)
    team.write_files("### FILE: app.py\n```\nX = 1\n```\n### FILE: tests/test_a.py\n```\nimport unittest, app\n\n\n"
                     "class T(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(app.X, 1)\n```", root)
    ok, out = team.run_tests(root)
    assert ok and "test_x" in out, out
with tempfile.TemporaryDirectory() as d:  # aucun test écrit = échec
    assert not team.run_tests(Path(d))[0]

# livrables sauvegardés au fil de l'eau, même si le run plante ensuite
saved = {}
try:
    team.run_team("demande", models, lambda m, p: {"text": " ", "in": 1, "out": 1} if p.startswith(team.PROMPTS["QA"]) else fake(m, p),
                  log=lambda *_: None, save=saved.__setitem__)
    assert False
except RuntimeError:
    assert saved["PM"] == "doc PM" and "DEV_BACK" in saved and "QA" not in saved

# le modèle plus fort répond vide pendant une correction : repli sur le précédent, le run va au bout
calls.clear()

def strong_mute(mid, prompt):
    r = fake(mid, prompt)
    if mid == "moyen" and prompt.startswith((team.PROMPTS["DEV_FRONT"], team.PROMPTS["DEV_BACK"])):
        r["text"] = ""
    return r


res = team.run_team("demande", models, strong_mute, log=lambda *_: None)
assert res["approved"] and [m for r, m in calls if r == "DEV_BACK"] == ["petit", "moyen", "gros"]
print("OK")
