import json
from pathlib import Path

import pytest

from boaz.accounts import initial_settings, install_assets, remember_account
from boaz.army import recommend
from boaz.config import Settings


def village(th=12, camp=10):
    return {'buildings':[{'data':1000001,'lvl':th},
        {'data':1000000,'lvl':camp,'cnt':4},{'data':1000020,'lvl':6},
        {'data':1000029,'lvl':1}],
        'units':[{'data':i,'lvl':1} for i in (4000001,4000003,4000004,4000012)],
        'spells':[{'data':i,'lvl':1} for i in (26000000,26000002,26000005)],
        'siege_machines':[{'data':4000062,'lvl':1}]}


def test_observed_account_army():
    army = recommend(village(),12)
    assert [(u.name,u.count) for u in army] == [('Valkyrie',35),('Rage',5),('Freeze',1),('Stone Slammer',1)]


def test_capacity_remainder_and_starter():
    assert [(u.name,u.count) for u in recommend(village(8,3),8)][:2] == [('Valkyrie',17),('Wall Breaker',2)]
    assert recommend(village(7,3),7)[0].name == 'Giant'
    assert recommend(village(7,3),7)[1].name == 'Archer'
    data = village()
    data['siege_machines'] = []
    assert all(u.name != 'Stone Slammer' for u in recommend(data,12))
    data['units'] = []
    with pytest.raises(ValueError,match='not unlocked'):
        recommend(data,12)
    with pytest.raises(ValueError,match='differs'):
        recommend(village(),13)


def test_remember_account_roundtrip_and_path_validation(tmp_path):
    cfg = Settings()
    cfg.walls.player_tag = '#QGYJ0VQQ0'
    cfg.farming.composition = recommend(village(),12)
    remember_account(tmp_path,cfg)
    assert initial_settings(tmp_path) == cfg
    (tmp_path/'last-account.json').write_text(json.dumps({'account':'../outside'}))
    with pytest.raises(ValueError):
        initial_settings(tmp_path)


def test_asset_install_preserves_existing_files(tmp_path):
    install_assets(tmp_path)
    files = [p for p in tmp_path.rglob('*') if p.is_file()]
    assert files, 'Recognition assets must ship with the application'
    file = files[0]
    file.write_bytes(b'custom calibration')
    install_assets(tmp_path)
    assert file.read_bytes() == b'custom calibration'
