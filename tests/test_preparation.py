from pathlib import Path
import cv2
import pytest
from boaz.recognition import OCR,RecognitionError,Recognizer,load_profile,Slot
import numpy as np
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from boaz.config import Settings,ArmyUnit,town_hall_army
from boaz.live import LiveRunner,UncertainAction


def test_capacity_warning_and_touching_separator():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition/numeric-font'
    executable=Path(__file__).parents[1]/'local/tesseract/tesseract.exe'
    if not executable.is_file():
        pytest.skip('Live captured touching glyph requires installed English Tesseract')
    ocr=OCR(str(executable),root)
    fixtures=Path(__file__).parent/'fixtures'
    for name,used in [('army-preparation-empty',0),('army-preparation-80',80)]:
        frame=cv2.imread(str(fixtures/(name+'.png')))
        assert ocr.ratio(frame[157:180,580:690]) == (used,280)
    with pytest.raises(RecognitionError):
        ocr.ratio(frame[0:23,580:690])


def test_wall_deselection_uses_clear_ground():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-default'),OCR('',root/'numeric-font'))
    frame=cv2.imread(str(Path(__file__).parent/'fixtures/oneclick-wall.png'))
    x,y=rec.clear_ground(frame)
    patch=cv2.cvtColor(frame[y-15:y+16,x-15:x+16],cv2.COLOR_BGR2HSV)
    assert np.all(cv2.inRange(patch,(20,50,70),(85,255,230)))
    with pytest.raises(RecognitionError,match='No clear grass'):
        rec.clear_ground(np.zeros_like(frame))


def test_selected_siege_flash_retains_deployed_arrow():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-queen-unavailable'),OCR('',root/'numeric-font'))
    frame=cv2.imread(str(Path(__file__).parent/'fixtures/siege-selected-flash.png'))
    assert rec.slot_state('battle',Slot(kind='troop',slot=2,single=True),frame) == ('deployed',0)


def test_real_wall_offer_and_elixir_confirmation():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-queen-unavailable'),OCR('',root/'numeric-font'))
    fixtures=Path(__file__).parent/'fixtures'
    frame=cv2.imread(str(fixtures/'oneclick-wall.png'))
    assert rec.read('wall.cost_gold',frame) == rec.read('wall.cost_elixir',frame) == 750000
    confirm=cv2.imread(str(fixtures/'oneclick-elixir-confirm.png'))
    assert rec.matches('confirm.currency_elixir',confirm)
    assert rec.matches('confirm.accept',confirm)
    assert rec.read('confirm.cost',confirm) == 750000


@pytest.mark.parametrize('failure',[None,UncertainAction('Unknown outcome'),asyncio.CancelledError()])
def test_preparation_replaces_once_and_never_replays_failed_action(tmp_path,monkeypatch,failure):
    async def scenario():
        cfg=Settings()
        cfg.farming.army=town_hall_army(12)
        cfg.farming.composition=[ArmyUnit(name='Valkyrie',count=35)]
        prepared=False
        def matches(key,frame):
            return prepared or key!='army.troops.layout'
        rec=SimpleNamespace(profile=SimpleNamespace(prepared_army=cfg.farming.composition),matches=matches)
        runner=LiveRunner(None,rec,asyncio.Lock(),tmp_path)
        runner.settings=cfg
        runner.village_data={}
        monkeypatch.setattr('boaz.live.recommend',lambda *args:cfg.farming.composition)
        runner._screen=AsyncMock(return_value=None)
        runner._delay=AsyncMock()
        runner._tap=AsyncMock()
        runner._transition=AsyncMock()
        runner._army_capacity=AsyncMock(side_effect=[(8,280),(0,280)])
        async def fill(*args):
            nonlocal prepared
            if failure:
                raise failure
            prepared=True
        runner._fill_army=AsyncMock(side_effect=fill)
        if failure:
            with pytest.raises(type(failure)):
                await runner._prepare_army()
            runner._tap.assert_not_called()
        else:
            await runner._prepare_army()
            runner._tap.assert_awaited_once_with('army_picker',point=(900,105))
        runner._fill_army.assert_awaited_once()
        assert [call.args[1] for call in runner._transition.await_args_list] == [
            'army.clear_troops','remove_troops.accept','army.edit_troops']
    asyncio.run(scenario())


def test_hero_flash_is_observed_without_another_portrait_tap(tmp_path):
    async def scenario():
        runner=LiveRunner(None,None,asyncio.Lock(),tmp_path)
        runner._inventory_once=AsyncMock(side_effect=[RecognitionError('Deployment flash'),{'hero.1':('deployed',0)}])
        runner._delay=AsyncMock()
        runner._recover=AsyncMock()
        assert await runner._inventory('battle','hero.1') == {'hero.1':('deployed',0)}
        assert runner._inventory_once.await_count == 2
        runner._recover.assert_not_called()
    asyncio.run(scenario())


def test_selected_ready_warden_scale():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-three-hero-geometry'),OCR('',root/'numeric-font'))
    frame=cv2.imread(str(Path(__file__).parent/'fixtures/warden-selected-ready.png'))
    assert rec.slot_state('battle',Slot(kind='hero',slot=1),frame) == ('ready',1)


def test_selected_wall_ignores_bright_scenery_behind_caption():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-queen-unavailable'),OCR('',root/'numeric-font'))
    frame=cv2.imread(str(Path(__file__).parent/'fixtures/wall-selected-changing-scenery.png'))
    rec.expect('build_wall',frame)
    assert rec.matches('build_wall.close',frame)
    with pytest.raises(RecognitionError):
        rec.expect('build_wall',np.zeros_like(frame))


def test_unsupported_scenery_is_filtered_before_placement():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-queen-unavailable'),OCR('',root/'numeric-font'))
    fixtures=Path(__file__).parent/'fixtures'
    assert not rec.supports_deployment_scenery(cv2.imread(str(fixtures/'unsupported-enemy-scenery.png')))
    assert rec.supports_deployment_scenery(cv2.imread(str(fixtures/'placement-minimum-zoom.png')))


def test_wall_level_width_change_keeps_complete_digits():
    root=Path(__file__).parents[1]/'src/boaz/assets/recognition'
    rec=Recognizer(root,load_profile(root,'boaz-queen-unavailable'),OCR('',root/'numeric-font'))
    fixtures=Path(__file__).parent/'fixtures'
    assert rec.read('wall.level',cv2.imread(str(fixtures/'wall-level-13-clipped.png'))) == 13
    assert rec.read('wall.level',cv2.imread(str(fixtures/'oneclick-wall.png'))) == 12


@pytest.mark.parametrize('settled',[True,False])
def test_home_zoom_is_verified_and_bounded(tmp_path,settled):
    async def scenario():
        frame=np.zeros((720,1280,3),dtype=np.uint8)
        device=SimpleNamespace(capture=lambda:frame,zoom_out=lambda **kwargs:None)
        rec=SimpleNamespace(expect=lambda screen,frame:None)
        runner=LiveRunner(device,rec,asyncio.Lock(),tmp_path)
        runner._gate.set()
        runner._delay=AsyncMock()
        runner._screen=AsyncMock(return_value=frame if settled else np.full_like(frame,100))
        if settled:
            await runner._normalize_camera()
        else:
            with pytest.raises(RecognitionError,match='did not settle'):
                await runner._normalize_camera()
        assert runner._screen.await_count == (3 if settled else 5)
    asyncio.run(scenario())
