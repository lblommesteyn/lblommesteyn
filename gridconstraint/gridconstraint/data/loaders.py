"""Loaders for the real public inputs staged in data/raw_public.

All of these are genuinely public datasets that happened to be mirrored on GitHub
(the only host reachable from the build sandbox besides PyPI):

* ICARUS PJM nodal testbed (Johns Hopkins, CC-BY-4.0): 17,467-bus / 21,554-branch
  PJM-footprint case with reactances and MVA ratings, clipped from the Breakthrough
  Energy USATestSystem. Used as the *hidden* ISO planning case.
* HIFLD substations (DHS, public domain): names / voltages / coordinates.
* EIA-860 generators (via TransmissionMap mirror).
* PJM zonal hourly load 1998-2018 (PJM Data Miner mirror).
* PJM TC2 cycle projects (ICARUS 21-zone package) and a MISO queue snapshot (gridstatus
  schema) used to calibrate the synthetic queue's size/fuel/arrival distributions.
"""
from __future__ import annotations
import pandas as pd
from .. import config as C


def load_bus() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "icarus_pjm_bus.csv.gz")


def load_branch() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "icarus_pjm_branch.csv.gz")


def load_plant() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "icarus_pjm_plant.csv.gz")


def load_zone() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "icarus_pjm_zone.csv")


def load_zone_demand_2016() -> pd.DataFrame:
    d = pd.read_csv(C.RAW / "icarus_pjm_zone_demand_2016.csv.gz")
    d["UTC Time"] = pd.to_datetime(d["UTC Time"])
    return d.set_index("UTC Time")


def load_hifld_substations() -> pd.DataFrame:
    d = pd.read_csv(C.RAW / "hifld_substations.csv.gz")
    d["name"] = d["name"].fillna("").astype(str).str.strip()
    return d


def load_eia_generators() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "eia_generators.csv.gz", low_memory=False)


def load_pjm_zonal_load() -> pd.DataFrame:
    d = pd.read_csv(C.RAW / "pjm_hourly_zonal_load_1998_2018.csv.gz")
    d["Datetime"] = pd.to_datetime(d["Datetime"])
    return d.set_index("Datetime")


def load_pjm_tc2_projects() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "icarus_pjm_tc2_cycle_projects.csv")


def load_miso_queue() -> pd.DataFrame:
    return pd.read_csv(C.RAW / "miso_queue_snapshot_2026-09-16.csv.gz", low_memory=False)
