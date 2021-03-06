#!/usr/bin/env python
# flake8: noqa

from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pytest

from nemspy import ModelingSystem
from nemspy.model.atmosphere import AtmosphericMeshEntry
from nemspy.model.base import ModelVerbosity
from nemspy.model.hydrology import NationalWaterModelEntry
from nemspy.model.ice import IceMeshEntry
from nemspy.model.ocean import ADCIRCEntry
from nemspy.model.waves import WaveMeshEntry
from nemspy.utilities import repository_root

REFERENCE_DIRECTORY = repository_root() / 'tests/reference'
ATMOSPHERIC_MESH_FILENAME = '~/wind_atm_fin_ch_time_vec.nc'
ICE_MESH_FILENAME = '~/sea_ice.nc'
WAVE_MESH_FILENAME = '~/ww3.Constant.20151214_sxy_ike_date.nc'


def test_interface():
    start_time = datetime(2020, 6, 1)
    duration = timedelta(days=1)
    interval = timedelta(hours=1)
    atmospheric_mesh = AtmosphericMeshEntry(ATMOSPHERIC_MESH_FILENAME)
    wave_mesh = WaveMeshEntry(WAVE_MESH_FILENAME)
    ocean_model = ADCIRCEntry(11)
    hydrological_model = NationalWaterModelEntry(769, Verbosity=ModelVerbosity.MAX)

    nems = ModelingSystem(
        start_time,
        start_time + duration,
        interval,
        atm=atmospheric_mesh,
        wav=wave_mesh,
        ocn=ocean_model,
    )

    assert nems['ATM'] is atmospheric_mesh
    assert nems['WAV'] is wave_mesh
    assert nems['OCN'] is ocean_model

    with pytest.raises(KeyError):
        nems['HYD']
    with pytest.raises(KeyError):
        nems['nonexistent']

    nems['HYD'] = hydrological_model

    assert nems['HYD'] is hydrological_model

    assert nems.interval == interval
    assert nems.attributes['Verbosity'] == 'off'

    new_interval = timedelta(minutes=30)
    nems.interval = new_interval

    assert nems.interval == new_interval

    nems.attributes = {'Verbosity': ModelVerbosity.MAX}
    nems.attributes['Verbosity'] = ModelVerbosity.LOW

    assert nems.attributes['Verbosity'] == 'max'


def test_connection():
    start_time = datetime(2020, 6, 1)
    duration = timedelta(days=1)
    interval = timedelta(hours=1)
    ocean_model = ADCIRCEntry(11)
    wave_mesh = WaveMeshEntry(WAVE_MESH_FILENAME)

    nems = ModelingSystem(
        start_time, start_time + duration, interval, ocn=ocean_model, wav=wave_mesh
    )
    nems.connect('WAV', 'OCN')

    with pytest.raises(KeyError):
        nems.connect('ATM', 'OCN')
    with pytest.raises(KeyError):
        nems.connect('WAV', 'HYD')
    with pytest.raises(KeyError):
        nems.connect('WAV', 'nonexistent')
    with pytest.raises(KeyError):
        nems.connect('WAV', 'OCN', 'nonexistent')

    assert nems.connections == ['WAV -> OCN   :remapMethod=redist']


def test_mediation():
    start_time = datetime(2020, 6, 1)
    duration = timedelta(days=1)
    interval = timedelta(hours=1)
    atmospheric_mesh = AtmosphericMeshEntry(ATMOSPHERIC_MESH_FILENAME)
    ice_mesh = IceMeshEntry(ICE_MESH_FILENAME)
    ocean_model = ADCIRCEntry(11)

    nems = ModelingSystem(
        start_time,
        start_time + duration,
        interval,
        ice=ice_mesh,
        ocn=ocean_model,
        atm=atmospheric_mesh,
    )

    nems.connect('OCN', 'MED')
    nems.mediate('ATM', 'ICE', functions=['MedPhase_prep_ice'])
    nems.mediate('ICE', None, functions=['MedPhase_atm_ocn_flux', 'MedPhase_accum_fast'])
    nems.mediate(None, 'OCN', functions=['MedPhase_prep_ocn'])

    nems.sequence = [
        'ATM',
        'ATM -> MED -> ICE',
        'ICE',
        'ICE -> MED',
        'MED -> OCN',
        'OCN',
        'OCN -> MED',
    ]

    with pytest.raises(KeyError):
        nems.connect('HYD', 'OCN')
    with pytest.raises(KeyError):
        nems.connect('WAV', 'nonexistent')
    with pytest.raises(KeyError):
        nems.connect('WAV', 'OCN', 'nonexistent')

    assert nems.connections == [
        'ATM -> MED   :remapMethod=redist\n'
        'MED MedPhase_prep_ice\n'
        'MED -> ICE   :remapMethod=redist',
        'ICE -> MED   :remapMethod=redist\n'
        'MED MedPhase_atm_ocn_flux\n'
        'MED MedPhase_accum_fast',
        'MED MedPhase_prep_ocn\n' 'MED -> OCN   :remapMethod=redist',
        'OCN -> MED   :remapMethod=redist',
    ]


def test_sequence():
    start_time = datetime(2020, 6, 1)
    duration = timedelta(days=1)
    interval = timedelta(hours=1)
    atmospheric_mesh = AtmosphericMeshEntry(ATMOSPHERIC_MESH_FILENAME)
    wave_mesh = WaveMeshEntry(WAVE_MESH_FILENAME)
    ocean_model = ADCIRCEntry(11)

    nems = ModelingSystem(
        start_time,
        start_time + duration,
        interval,
        atm=atmospheric_mesh,
        wav=wave_mesh,
        ocn=ocean_model,
    )

    assert atmospheric_mesh.start_processor == 0
    assert atmospheric_mesh.end_processor == 0
    assert wave_mesh.start_processor == 1
    assert wave_mesh.end_processor == 1
    assert ocean_model.start_processor == 2
    assert ocean_model.end_processor == 12

    assert nems.sequence == ['ATM', 'WAV', 'OCN']
    with pytest.raises(KeyError):
        nems.sequence = ['HYD']
    with pytest.raises(KeyError):
        nems.sequence = ['nonexistent']
    with pytest.raises(KeyError):
        nems.sequence = ['OCN', 'ATM', 'WAV', 'WAV -> OCN ']
    assert nems.sequence == ['ATM', 'WAV', 'OCN']

    nems.sequence = ['OCN', 'ATM', 'WAV']

    assert nems.sequence == ['OCN', 'ATM', 'WAV']

    assert ocean_model.start_processor == 0
    assert ocean_model.end_processor == 10
    assert atmospheric_mesh.start_processor == 11
    assert atmospheric_mesh.end_processor == 11
    assert wave_mesh.start_processor == 12
    assert wave_mesh.end_processor == 12

    nems.sequence = [
        'ATM',
        'WAV',
        'OCN',
    ]

    nems.connect('ATM', 'OCN')
    nems.connect('WAV', 'OCN')
    nems.sequence = [
        'ATM -> OCN',
        'WAV -> OCN',
        'ATM',
        'WAV',
        'OCN',
    ]

    assert atmospheric_mesh.start_processor == 0
    assert atmospheric_mesh.end_processor == 0
    assert wave_mesh.start_processor == 1
    assert wave_mesh.end_processor == 1
    assert ocean_model.start_processor == 2
    assert ocean_model.end_processor == 12


def test_configuration_files():
    start_time = datetime(2020, 6, 1)
    duration = timedelta(days=1)
    interval = timedelta(hours=1)
    atmospheric_mesh = AtmosphericMeshEntry(ATMOSPHERIC_MESH_FILENAME)
    wave_mesh = WaveMeshEntry(WAVE_MESH_FILENAME, Verbosity='low')
    ocean_model = ADCIRCEntry(11)
    hydrological_model = NationalWaterModelEntry(769, Verbosity=ModelVerbosity.MAX)

    nems = ModelingSystem(
        start_time,
        start_time + duration,
        interval,
        atm=atmospheric_mesh,
        wav=wave_mesh,
        ocn=ocean_model,
        hyd=hydrological_model,
        Verbosity='off',
    )
    nems.connect('ATM', 'OCN')
    nems.connect('WAV', 'OCN')
    nems.connect('ATM', 'HYD')
    nems.connect('WAV', 'HYD')
    nems.connect('OCN', 'HYD')

    sequence = [
        'ATM -> OCN',
        'WAV -> OCN',
        'ATM -> HYD',
        'WAV -> HYD',
        'OCN -> HYD',
        'ATM',
        'WAV',
        'OCN',
        'HYD',
    ]

    nems.sequence = sequence

    assert nems.processors == 782

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_directory = Path(temporary_directory)
        nems.write(temporary_directory, overwrite=True, include_version=False)
        for test_filename in temporary_directory.iterdir():
            reference_filename = REFERENCE_DIRECTORY / test_filename.name
            with open(test_filename) as test_file:
                with open(reference_filename) as reference_file:
                    assert test_file.read() == reference_file.read()
