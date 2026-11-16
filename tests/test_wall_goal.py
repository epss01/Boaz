from collections import Counter
import json

import pytest

from boaz.village import WallProgress, read_village


def export(levels, **extra):
    buildings = [{'data':1000001,'lvl':13}]
    buildings.extend({'data':1000010,'lvl':level,'cnt':count} for level,count in levels)
    return json.dumps(dict(tag='#PY2',timestamp=100,buildings=buildings) | extra)


def test_home_walls_only_and_completion():
    mixed = read_village(export([(12,200),(13,5),(14,95)], buildings2=[{'data':1000010,'lvl':3}]),
                         '#PY2',99,100)
    assert mixed.target == 14 and mixed.remaining == 205
    assert mixed.eligible(12) and not mixed.eligible(14)
    assert not read_village(export([(14,300)]),'#PY2',99,100).remaining
    partial = WallProgress('#PY2',100,18,19,75,Counter({17:5,18:240,19:75}))
    assert partial.remaining == 5 and partial.eligible(17) and not partial.eligible(18)


@pytest.mark.parametrize('raw,tag,since', [
    (export([(14,300)]),'#Q2',99), (export([(14,300)]),'#PY2',101),
    (export([]),'#PY2',99), (export([(14,0)]),'#PY2',99),
    (export([(15,1)]),'#PY2',99), (export([(14,True)]),'#PY2',99)])
def test_unusable_export_never_proves_completion(raw,tag,since):
    with pytest.raises(ValueError):
        read_village(raw,tag,since,100)
