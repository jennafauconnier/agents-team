"""Équipe d'agents LLM : PM -> PO -> Tech Lead -> Dev Front + Dev Back (en parallèle) -> tests -> QA (-> corrections).

    python3 team.py "Ajouter un panier à une boutique" [models.team.openrouter.json]

Chaque rôle = un prompt + un modèle (cheap pour cadrer, fort pour concevoir/vérifier).
Les agents ne "discutent" pas : chacun reçoit les LIVRABLES des étapes précédentes.
Le code du dev back est écrit sur disque (out/<horodatage>/work/) et ses tests `unittest` sont EXÉCUTÉS :
le QA juge d'après leur résultat. Après un KO, seul le côté fautif est refait, avec un modèle plus fort.
Résultats écrits dans out/<horodatage>/. Réutilise l'appel API + cache de llm-bench.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("MAX_TOKENS", "16000")  # Qwen (raisonnement) épuise 4000 tokens avant de répondre au QA
os.environ.setdefault("TIMEOUT", "300")
sys.path.insert(0, str(Path(__file__).parent))
import bench  # noqa: E402

FILES = ("Réponds UNIQUEMENT par des fichiers, chacun au format :\n"
         "### FILE: chemin/relatif.ext\n```\ncontenu\n```")
PROMPTS = {
    "PM": "Tu es PM. Cadre la demande : objectif, utilisateurs, périmètre, hors-périmètre, risques. 15 lignes max.",
    "PO": ("Tu es PO. Écris 3 stories MAXIMUM avec critères d'acceptation (Given/When/Then), testables. "
           "Strictement ce que la demande exige : pas de fonctionnalité en plus (synchro multi-onglets, fusion de comptes, expiration…)."),
    "TECH_LEAD": ("Tu es Tech Lead. Découpe en sections `## API` (endpoints + JSON), `## FRONT` (tâches), "
                  "`## BACK` (tâches). Reste minimal, pas de sur-ingénierie. Contraintes : back en Python "
                  "bibliothèque standard uniquement (logique en fonctions/classes, SANS framework web), front en HTML/JS sans build."),
    "DEV_FRONT": "Tu es dev front (HTML/JS sans build). Implémente la partie FRONT du plan, concis. " + FILES,
    "DEV_BACK": ("Tu es dev back (Python, bibliothèque standard uniquement). Implémente la partie BACK et l'API du plan, "
                 "concis, PLUS un fichier test_*.py (à la racine) en `unittest` qui vérifie le plan. "
                 "Aucun framework (pas de Flask) : la logique doit être importable et testable directement. " + FILES),
    "QA": ("Tu es QA pragmatique. Compare le code aux critères d'acceptation ; le résultat des tests fait foi pour le BACK. "
           "Un côté est OK si ses fonctions principales marchent. Ne le mets KO que pour un critère CLAIREMENT non rempli, "
           "jamais pour un libellé, une icône, du style, un cas limite ou de la concurrence. En cas de doute : OK. "
           "Si un test échoue, recalcule à la main : dis si c'est le CODE ou le TEST qui est faux. Ne cite que du code réellement présent. "
           "Format STRICT, sans raisonnement ni répétition : 3 lignes exactes `VERDICT: OK|KO`, `FRONT: OK|KO`, `BACK: OK|KO`, "
           "puis 3 défauts maximum (une phrase chacun, avec le critère concerné), ou rien si tout est OK."),
}
FILE_RE = re.compile(r"### FILE:\s*(\S+)\s*\n```[^\n]*\n(.*?)```", re.S)


def pick(models):
    """Modèle par rôle selon le prix : cheap pour cadrer et exécuter (code), fort pour concevoir et vérifier.
    (Le moins cher est souvent un modèle de raisonnement qui épuise ses tokens sur du code : réponse vide.)
    Un KO du QA fait monter le dev d'un cran dans l'échelle de prix."""
    m = sorted(models, key=lambda x: x["in"] + x["out"])
    return {"PM": m[0], "PO": m[0], "TECH_LEAD": m[-1], "DEV_FRONT": m[0], "DEV_BACK": m[0], "QA": m[-1]}


def part(plan, *names):
    """Sections `## NOM` du plan (ex. API + BACK) ; le plan entier si aucune n'est trouvée."""
    keep = [s for s in re.split(r"^## ", plan, flags=re.M)[1:] if s.strip().upper().startswith(names)]
    return "## " + "## ".join(keep) if keep else plan


def parse_qa(qa, tests_ok):
    """-> (approuvé, côtés à corriger). Des tests rouges l'emportent sur un QA trop gentil."""
    ko = {s for s in ("FRONT", "BACK") if (m := re.search(rf"^{s}:\s*(OK|KO)", qa, re.I | re.M)) and m[1].upper() == "KO"}
    if tests_ok is False:
        ko.add("BACK")
    approved = qa.strip().upper().startswith("VERDICT: OK") and not ko
    return approved, ko or {"FRONT", "BACK"}  # KO sans détail : on refait tout


def write_files(text, root):
    """Écrit les blocs `### FILE: chemin` d'une réponse sous root ; refuse les chemins qui en sortent."""
    root = root.resolve()
    for path, code in FILE_RE.findall(text):
        p = (root / path).resolve()
        if root in p.parents:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(code)


def run_tests(root, timeout=60):
    """Lance les tests du code généré -> (ok, sortie). Env minimal : pas de clé d'API pour du code non relu."""
    for t in Path(root).rglob("test_*.py"):  # discover n'entre pas dans un dossier sans __init__.py
        for d in t.parents:
            if d == Path(root).resolve() or d == Path(root):
                break
            (d / "__init__.py").touch()
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-v"], cwd=root, capture_output=True,
                           text=True, timeout=timeout, env={"PATH": os.environ.get("PATH", "")})
    except subprocess.TimeoutExpired:
        return False, f"tests interrompus après {timeout}s"
    out = (r.stdout + r.stderr)[-3000:]
    if "Ran 0 tests" in out:
        return False, out + "\nAucun test trouvé : livre un fichier test_*.py à la racine."
    return r.returncode == 0, out


def run_team(request, models, call, max_fix=5, budget=0.50, log=print, check=None, save=lambda role, text: None):
    """Retourne {"docs", "cost", "approved"}. Garde-fous : max_fix boucles QA, budget en $.
    check(front, back) -> (ok, sortie) exécute le code ; None = le QA ne fait que relire.
    save(rôle, texte) est appelé à chaque livrable : un run qui plante ne perd rien."""
    who, docs, cost, lock = pick(models), {}, 0.0, threading.Lock()
    calls, rounds = [], []  # historique : un appel par réponse utile, un tour par passage tests + QA
    ladder = sorted(models, key=lambda x: x["in"] + x["out"])

    def ask(role, context, up=0):
        """up = nombre de crans à monter dans l'échelle de prix (correction après un KO)."""
        nonlocal cost
        # réponse vide (modèle de raisonnement à court de tokens) : on passe au modèle suivant, plus cher
        err = None
        base = ladder.index(who[role])
        start = min(base + up, len(ladder) - 1)
        # si le modèle plus fort échoue (vide, timeout), on retombe sur celui d'avant plutôt que de planter
        for m in ladder[start:] + ladder[:start][::-1]:  # d'abord plus fort, puis les moins chers
            try:
                r = call(m["id"], PROMPTS[role] + "\n\n---\n" + context)
            except RuntimeError as e:  # timeout, HTTP 5xx… : modèle suivant
                err = e
                log(f"[{role:9}] {m['id']} : {e} -> modèle suivant")
                continue
            with lock:  # front et back tournent en parallèle
                cost += bench.price(m, r)  # une réponse vide est quand même facturée
                if cost > budget:  # sans plafond, une boucle QA/dev peut coûter très cher
                    raise RuntimeError(f"Budget dépassé après {role} : ${cost:.4f} > ${budget}")
            if r["text"].strip():
                break
            log(f"[{role:9}] {m['id']} : réponse vide ({r['out']} tokens) -> modèle suivant")
        else:
            raise RuntimeError(f"{role} : aucun modèle n'a répondu ({err or 'tous ont répondu vide'}). "
                               "Essaie : export MAX_TOKENS=8000 TIMEOUT=300")
        docs[role] = r["text"]
        calls.append({"role": role, "model": m["id"], "cost": round(cost, 5)})
        save(role, docs[role])
        log(f"[{role:9}] {m['id']}  (cumul ${cost:.5f})")
        return r["text"]

    def devs(jobs):
        """jobs = {rôle: (contexte, up)} ; les devs travaillent en parallèle."""
        with ThreadPoolExecutor(2) as ex:
            futs = {r: ex.submit(ask, r, c, up) for r, (c, up) in jobs.items()}
            return {r: f.result() for r, f in futs.items()}

    pm = ask("PM", f"Demande : {request}")
    po = ask("PO", f"Demande : {request}\n\nCadrage PM :\n{pm}")
    plan = ask("TECH_LEAD", f"Stories PO :\n{po}")
    fplan, bplan = part(plan, "API", "FRONT"), part(plan, "API", "BACK")  # chaque dev ne reçoit que sa part
    got = devs({"DEV_FRONT": (f"Plan :\n{fplan}", 0), "DEV_BACK": (f"Plan :\n{bplan}", 0)})
    front, back = got["DEV_FRONT"], got["DEV_BACK"]
    approved = False
    for i in range(max_fix + 1):
        tests_ok, report = check(front, back) if check else (None, "non exécutés")
        if check:
            docs["TESTS"] = report
            save("TESTS", report)
            log(f"[TESTS    ] {'OK' if tests_ok else 'KO'}")
        qa = ask("QA", f"Critères (PO) :\n{po}\n\nCode FRONT :\n{front}\n\nCode BACK :\n{back}\n\nTests BACK :\n{report}")
        approved, ko = parse_qa(qa, tests_ok)
        rounds.append({"tests": tests_ok, "front": "KO" if "FRONT" in ko else "OK", "back": "KO" if "BACK" in ko else "OK",
                       "approved": approved, "cost": round(cost, 5)})
        if approved or i == max_fix:
            break
        jobs = {}
        if "FRONT" in ko:
            jobs["DEV_FRONT"] = (f"Plan :\n{fplan}\n\nTon code :\n{front}\n\nRetours QA (corrige le FRONT ; renvoie les fichiers COMPLETS) :\n{qa}", i + 1)
        if "BACK" in ko:
            jobs["DEV_BACK"] = (f"Plan :\n{bplan}\n\nTon code :\n{back}\n\nRetours QA et tests (corrige le BACK : recalcule à la main les valeurs attendues d'après le plan ; si le test attend une valeur fausse, corrige le TEST, sinon le code ; renvoie TOUJOURS le fichier test_*.py en plus du code, corrigé si le QA dit que le test est faux ; fichiers COMPLETS, imports compris) :\n{qa}\n{report}", i + 1)
        got = devs(jobs)  # correction avec un modèle plus fort que la fois précédente
        front, back = got.get("DEV_FRONT", front), got.get("DEV_BACK", back)
    return {"docs": docs, "cost": cost, "approved": approved, "rounds": rounds, "calls": calls}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    models = json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent / "models.team.openrouter.json").read_text())
    out = Path(__file__).parent / "out" / time.strftime("%Y%m%d-%H%M%S")
    work = out / "work"
    work.mkdir(parents=True)

    def check(front, back):
        write_files(front, work)
        write_files(back, work)
        return run_tests(work)

    names = {}

    def save(role, text):  # écrit tout de suite ; un rôle garde son numéro quand il est refait
        (out / f"{names.setdefault(role, len(names) + 1)}-{role}.md").write_text(text)

    try:
        res = run_team(sys.argv[1], models, bench.call_openrouter, check=check, save=save)
    except RuntimeError as e:
        sys.exit(f"{e}\nLivrables déjà produits : {out}")
    (out / "run.json").write_text(json.dumps({"request": sys.argv[1], "approved": res["approved"], "cost": round(res["cost"], 5),
                                              "rounds": res["rounds"], "calls": res["calls"]}, ensure_ascii=False, indent=1))
    print(f"\nQA : {'APPROUVÉ' if res['approved'] else 'NON APPROUVÉ'} · coût ${res['cost']:.5f} · {out}")
