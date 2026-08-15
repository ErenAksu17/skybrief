"""
Eval setini bir CI kapısı olarak koşar: tüm vakalar geçmeli, sıfır fabrication.
"""

from evaluation.run import run_eval


def test_all_eval_cases_pass():
    report = run_eval()
    failed = [c.id for c in report.cases if not c.passed]
    assert not failed, f"Başarısız vakalar: {failed}"


def test_no_fabrication():
    assert run_eval().fabrication_total == 0


def test_abstain_recall_perfect():
    # Abstain gereken tüm vakalarda gerçekten abstain edilmeli (recall = 1.0)
    _, recall = run_eval().abstain_metrics()
    assert recall == 1.0


def test_has_25_cases():
    assert run_eval().total == 25
