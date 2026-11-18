import unittest

from catalog import get_catalog
from cart import reconcile, add, update, remove


def _cat():
    return get_catalog()


class TestReconcile(unittest.TestCase):
    def test_empty(self):
        r = reconcile({"lines": {}}, _cat())
        self.assertEqual(r["lines"], [])
        self.assertEqual(r["subtotal"], 0.0)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["warnings"], [])

    def test_ok(self):
        r = reconcile({"lines": {"A1": 2, "A5": 1}}, _cat())
        skus = {l["sku"]: l for l in r["lines"]}
        self.assertEqual(skus["A1"]["status"], "OK")
        self.assertEqual(skus["A1"]["line_total"], 19.8)
        self.assertEqual(skus["A5"]["status"], "OK")
        self.assertEqual(skus["A5"]["line_total"], 15.0)
        self.assertEqual(r["subtotal"], 34.8)
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["warnings"], [])

    def test_stock_low(self):
        r = reconcile({"lines": {"A1": 10}}, _cat())
        line = r["lines"][0]
        self.assertEqual(line["status"], "STOCK_LOW")
        self.assertEqual(line["qty"], 5)
        self.assertEqual(line["line_total"], 49.5)
        self.assertEqual(r["count"], 5)
        self.assertEqual(r["subtotal"], 49.5)
        self.assertEqual(len(r["warnings"]), 1)
        w = r["warnings"][0]
        self.assertEqual(w["code"], "STOCK_LOW")
        self.assertEqual(w["sku"], "A1")
        self.assertEqual(w["max"], 5)

    def test_unavailable_unknown_sku(self):
        r = reconcile({"lines": {"ZZ": 1}}, _cat())
        self.assertEqual(r["lines"][0]["status"], "UNAVAILABLE")
        self.assertEqual(r["subtotal"], 0.0)
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["warnings"][0]["code"], "UNAVAILABLE")

    def test_unavailable_inactive(self):
        r = reconcile({"lines": {"A4": 1}}, _cat())
        self.assertEqual(r["lines"][0]["status"], "UNAVAILABLE")
        self.assertEqual(r["subtotal"], 0.0)
        self.assertEqual(r["count"], 0)

    def test_unavailable_stock_zero(self):
        r = reconcile({"lines": {"A2": 1}}, _cat())
        self.assertEqual(r["lines"][0]["status"], "UNAVAILABLE")
        self.assertEqual(r["count"], 0)

    def test_count_excludes_unavailable(self):
        r = reconcile({"lines": {"A1": 1, "A2": 2, "A5": 3}}, _cat())
        self.assertEqual(r["count"], 4)  # A1 qty=1 + A5 qty=3
        self.assertAlmostEqual(r["subtotal"], round(9.9 + 45.0, 2))

    def test_subtotal_rounding(self):
        r = reconcile({"lines": {"A3": 1}}, _cat())
        self.assertEqual(r["subtotal"], 24.5)


class TestAdd(unittest.TestCase):
    def test_add_new(self):
        state, ok, err = add({"lines": {}}, "A1", 2, _cat())
        self.assertTrue(ok)
        self.assertEqual(state, {"lines": {"A1": 2}})
        self.assertEqual(err, "")

    def test_add_accumulates(self):
        """Story 1 CA2 : ajout sur une ligne existante incrément la quantité."""
        state, ok, err = add({"lines": {"A1": 1}}, "A1", 1, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 2})

    def test_add_accumulates_multiple_times(self):
        state = {"lines": {}}
        state, ok, _ = add(state, "A1", 2, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 2})
        state, ok, _ = add(state, "A1", 3, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 5})

    def test_add_accumulates_exceeds_stock(self):
        """L'accumulation qui dépasse le stock est refusée et l'état est inchangé."""
        state = {"lines": {"A1": 4}}
        new_state, ok, err = add(state, "A1", 2, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")
        self.assertEqual(new_state, {"lines": {"A1": 4}})

    def test_add_out_of_stock(self):
        state, ok, err = add({"lines": {}}, "A1", 6, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")

    def test_add_inactive(self):
        _, ok, err = add({"lines": {}}, "A4", 1, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")

    def test_add_unknown(self):
        _, ok, err = add({"lines": {}}, "ZZ", 1, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "OUT_OF_STOCK")

    def test_add_invalid_qty(self):
        _, ok, err = add({"lines": {}}, "A1", "x", _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "INVALID_QTY")

    def test_add_zero_qty(self):
        _, ok, err = add({"lines": {}}, "A1", 0, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "INVALID_QTY")

    def test_add_negative_qty(self):
        _, ok, err = add({"lines": {}}, "A1", -1, _cat())
        self.assertFalse(ok)
        self.assertEqual(err, "INVALID_QTY")


class TestUpdate(unittest.TestCase):
    def test_update_clamp(self):
        state = update({"lines": {"A1": 1}}, "A1", 99, _cat())
        self.assertEqual(state["lines"]["A1"], 5)

    def test_update_zero_removes(self):
        state = update({"lines": {"A1": 2}}, "A1", 0, _cat())
        self.assertNotIn("A1", state["lines"])

    def test_update_new_line(self):
        state = update({"lines": {}}, "A3", 2, _cat())
        self.assertEqual(state["lines"]["A3"], 2)

    def test_update_unavailable_keeps_line(self):
        """Une ligne indisponible est conservée dans le state pour affichage/suppression."""
        state = update({"lines": {}}, "A2", 1, _cat())
        self.assertEqual(state["lines"], {"A2": 1})

    def test_update_negative_removes(self):
        state = update({"lines": {"A1": 2}}, "A1", -1, _cat())
        self.assertNotIn("A1", state["lines"])


class TestRemove(unittest.TestCase):
    def test_remove(self):
        state = remove({"lines": {"A1": 2, "A5": 1}}, "A1")
        self.assertEqual(state["lines"], {"A5": 1})

    def test_remove_missing(self):
        state = remove({"lines": {"A5": 1}}, "ZZ")
        self.assertEqual(state["lines"], {"A5": 1})


class TestIntegration(unittest.TestCase):
    def test_flow(self):
        state = {"lines": {}}
        state, ok, _ = add(state, "A1", 2, _cat())
        self.assertTrue(ok)
        state, ok, _ = add(state, "A3", 1, _cat())
        self.assertTrue(ok)

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["subtotal"], round(9.9 * 2 + 24.5, 2))

        state = update(state, "A3", 99, _cat())
        self.assertEqual(state["lines"]["A3"], 3)

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 5)
        self.assertAlmostEqual(r["subtotal"], round(9.9 * 2 + 24.5 * 3, 2))

        state = remove(state, "A1")
        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["subtotal"], round(24.5 * 3, 2))

    def test_flow_with_accumulation(self):
        """Story 1 CA2 : add successifs accumulent, le panier grandit correctement."""
        state = {"lines": {}}
        state, ok, _ = add(state, "A5", 3, _cat())
        self.assertTrue(ok)
        state, ok, _ = add(state, "A5", 2, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A5": 5})

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 5)
        self.assertEqual(r["subtotal"], 75.0)

    def test_flow_state_preserved_on_add(self):
        """Story 1 CA1/CA2 : le state est envoyé et préservé d'un appel add à l'autre."""
        state = {"lines": {}}
        state, ok, _ = add(state, "A1", 2, _cat())
        self.assertTrue(ok)
        state, ok, _ = add(state, "A3", 1, _cat())
        self.assertTrue(ok)
        self.assertEqual(state["lines"], {"A1": 2, "A3": 1})

        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["subtotal"], round(9.9 * 2 + 24.5, 2))

    def test_unavailable_line_remains_in_state(self):
        """Story 3 CA2 : une ligne UNAVAILABLE reste dans le state pour suppression."""
        state = {"lines": {"A2": 1, "A1": 2}}
        r = reconcile(state, _cat())
        self.assertEqual(r["count"], 2)
        self.assertAlmostEqual(r["subtotal"], 19.8)
        # A2 est bien présent
        skus = [l["sku"] for l in r["lines"]]
        self.assertIn("A2", skus)
        self.assertIn("A1", skus)
        # suppression possible
        state = remove(state, "A2")
        self.assertNotIn("A2", state["lines"])
        self.assertIn("A1", state["lines"])


if __name__ == "__main__":
    unittest.main()
