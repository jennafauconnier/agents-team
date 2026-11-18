test_add_accumulates (test_cart.TestAdd)
Story 1 CA2 : ajout sur une ligne existante incrément la quantité. ... ok
test_add_accumulates_exceeds_stock (test_cart.TestAdd)
L'accumulation qui dépasse le stock est refusée et l'état est inchangé. ... ok
test_add_accumulates_multiple_times (test_cart.TestAdd) ... ok
test_add_inactive (test_cart.TestAdd) ... ok
test_add_invalid_qty (test_cart.TestAdd) ... ok
test_add_negative_qty (test_cart.TestAdd) ... ok
test_add_new (test_cart.TestAdd) ... ok
test_add_out_of_stock (test_cart.TestAdd) ... ok
test_add_unknown (test_cart.TestAdd) ... ok
test_add_zero_qty (test_cart.TestAdd) ... ok
test_flow (test_cart.TestIntegration) ... ok
test_flow_state_preserved_on_add (test_cart.TestIntegration)
Story 1 CA1/CA2 : le state est envoyé et préservé d'un appel add à l'autre. ... ok
test_flow_with_accumulation (test_cart.TestIntegration)
Story 1 CA2 : add successifs accumulent, le panier grandit correctement. ... ok
test_unavailable_line_remains_in_state (test_cart.TestIntegration)
Story 3 CA2 : une ligne UNAVAILABLE reste dans le state pour suppression. ... ok
test_count_excludes_unavailable (test_cart.TestReconcile) ... ok
test_empty (test_cart.TestReconcile) ... ok
test_ok (test_cart.TestReconcile) ... ok
test_stock_low (test_cart.TestReconcile) ... ok
test_subtotal_rounding (test_cart.TestReconcile) ... ok
test_unavailable_inactive (test_cart.TestReconcile) ... ok
test_unavailable_stock_zero (test_cart.TestReconcile) ... ok
test_unavailable_unknown_sku (test_cart.TestReconcile) ... ok
test_remove (test_cart.TestRemove) ... ok
test_remove_missing (test_cart.TestRemove) ... ok
test_update_clamp (test_cart.TestUpdate) ... ok
test_update_negative_removes (test_cart.TestUpdate) ... ok
test_update_new_line (test_cart.TestUpdate) ... ok
test_update_unavailable_keeps_line (test_cart.TestUpdate)
Une ligne indisponible est conservée dans le state pour affichage/suppression. ... ok
test_update_zero_removes (test_cart.TestUpdate) ... ok

----------------------------------------------------------------------
Ran 29 tests in 0.001s

OK
