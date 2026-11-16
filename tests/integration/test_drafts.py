# Author: Nicola Antonello
from regulator_graded_rag.citations import definitions
from regulator_graded_rag.ecfr import UnitText


def test_the_editions_definitions_reach_the_labels(
    ecfr_edition: dict[str, UnitText],
) -> None:
    terms = definitions(ecfr_edition)
    assert terms["hazmat employee"] == "Hazmat%20employee"
    # 269 definitions; a key naming two terms answers to either name too.
    assert len(set(terms.values())) == 269
    assert terms["gross weight"] == "Gross%20weight%20or%20Gross%20mass"
