"""Parser behaviour on report language modelled on real PJM System Impact Study reports
(illustrative fixture text written from the public report style; not copied from any report)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridconstraint.extract.pdf_parser import parse_findings_from_text, parse_meta
from gridconstraint.extract.normalize import FacilityNormalizer
import pandas as pd

FIXTURE = """Generation Interconnection System Impact Study Report
For Queue Project AE2-281
Alburtis 500 kV
April 12, 2019
1. Introduction
The Interconnection Customer proposes a 150.0 MW solar photovoltaic facility interconnecting at the Alburtis 500 kV substation in the PPL area.
The request was received on March 30, 2018.
2. Summary of Results
The project was found to contribute (DFAX of 5% or greater) to 2 overloaded facilities. The total estimated cost of the network upgrades allocated to this project is $4,250,000.
3. Network Impacts
3.1 Generator Deliverability and Single Contingency Analysis
The Alburtis - Hosensack 500 kV line is overloaded to 103.7% of its 2,598 MVA emergency rating for the loss of the Juniata - Alburtis 500 kV
line. The project contributes 7.2% DFAX (10.8 MW) to this overload.
For the loss of Alburtis 500/230 kV Transformer #2, the Alburtis 500/230 kV Transformer #1 loads to 108.1% of its 750 MVA rating. Project DFAX: 12.5%.
3.2 Multiple Facility Contingency Analysis
"""


def test_prose_patterns():
    f = parse_findings_from_text(FIXTURE)
    assert len(f) == 2, f
    assert f[0]["facility_str"].startswith("Alburtis - Hosensack 500 kV")
    assert abs(f[0]["loading_pct"] - 103.7) < 1e-6 and f[0]["rating_mva"] == 2598 and abs(f[0]["dfax_pct"] - 7.2) < 1e-6
    assert "Transformer #1" in f[1]["facility_str"] and abs(f[1]["loading_pct"] - 108.1) < 1e-6
    m = parse_meta(FIXTURE)
    assert m["project_id"] == "AE2-281" and m["mw"] == 150.0 and m["total_cost_usd"] == 4250000 and m["n_facilities_stated"] == 2


def test_normaliser_variants():
    subs = pd.DataFrame(dict(sub_id=[1, 2, 3], name=["Alburtis", "Hosensack", "Juniata"], max_kv=[500, 500, 500], min_kv=[230, 230, 500],
                             lat=[40.5, 40.4, 40.6], lon=[-75.6, -75.5, -77.5]))
    fac = pd.DataFrame(dict(fid=["L:1:2:500", "L:1:3:500", "X:1:500:230"], kind=["L", "L", "X"], sub_a=[1, 1, 1], sub_b=[2, 3, None], kv=[500, 500, 500], length_km=[10, 120, 0]))
    N = FacilityNormalizer(subs, fac)
    for s in ["Alburtis - Hosensack 500 kV line", "HOSENSACK-ALBURTIS 500 KV", "Hosensack – Alburtis 500kV Ckt 1", "Alburtis to Hosensack 500.0 kV Circuit 2", "Albutris - Hosensack 500 kV"]:
        assert N.normalize(s)["fid"] == "L:1:2:500", s
    for s in ["Alburtis 500/230 kV Transformer #1", "ALBURTIS 500-230 KV XFMR T2", "Alburtis 500 kV/230 kV Autotransformer Bank 1"]:
        assert N.normalize(s)["fid"] == "X:1:500:230", s


if __name__ == "__main__":
    test_prose_patterns(); test_normaliser_variants(); print("parser fixture tests passed")
