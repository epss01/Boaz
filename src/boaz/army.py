"""One shared recommendation for the banner and the in-game army import."""
from .config import ArmyUnit

# IDs and housing from the ClashKing game-file catalog; army links use ID offsets.
UNITS = {
    'Valkyrie': (4000012,8,'troop','valkyrie'),
    'Wall Breaker': (4000004,2,'troop','wall_breaker'),
    'Giant': (4000003,5,'troop','giant'),
    'Archer': (4000001,1,'troop','archer'),
    'Rage': (26000002,2,'spell','rage'),
    'Freeze': (26000005,1,'spell','freeze'),
    'Lightning': (26000000,1,'spell','lightning'),
    'Stone Slammer': (4000062,1,'siege','stone_slammer'),
    'Wall Wrecker': (4000051,1,'siege','wall_wrecker'),
}
CAMP_CAPACITY = (20,30,35,40,45,50,55,60,65,70,75,80,85,88)


def recommend(village, town_hall):
    if type(town_hall) is not int or not 7 <= town_hall <= 18:
        raise ValueError('Choose a supported Town Hall from 7 to 18')
    rows = village['buildings']
    if next(r['lvl'] for r in rows if r['data']==1000001) != town_hall:
        raise ValueError('Selected Town Hall differs from this account. Check the account again.')
    capacity = 0
    for row in rows:
        if row['data']==1000000:
            level,count = row['lvl'],row.get('cnt',1)
            if type(level) is not int or not 1<=level<=len(CAMP_CAPACITY) or type(count) is not int or not 1<=count<=4:
                raise ValueError('Unrecognized army camp capacity')
            capacity += CAMP_CAPACITY[level-1]*count
    factory = next((r['lvl'] for r in rows if r['data']==1000020),0)
    if type(factory) is not int or not 1<=factory<=9 or not 1<=capacity<=500:
        raise ValueError('Could not verify army and spell capacity')
    spells = min(factory*2,10) + int(any(r['data']==1000029 for r in rows))
    unlocked = {r['data'] for field in ('units','spells','siege_machines') for r in village.get(field,[]) if r.get('lvl',0)>0}
    result = []
    def add(name,count):
        if count:
            if UNITS[name][0] not in unlocked:
                raise ValueError(f'{name} is not unlocked on this account')
            result.append(ArmyUnit(name=name,count=count))
    main = 'Giant' if town_hall==7 else 'Valkyrie'
    count = (capacity*4//5 if main=='Giant' else capacity)//UNITS[main][1]
    remainder = capacity-count*UNITS[main][1]
    add(main,count)
    if main=='Giant':
        add('Archer',remainder)
    else:
        add('Wall Breaker',remainder//2)
        add('Archer',remainder%2)
    add('Rage',spells//2)
    add('Freeze' if 26000005 in unlocked else 'Lightning',spells%2)
    for name in ('Stone Slammer','Wall Wrecker'):
        if UNITS[name][0] in unlocked:
            add(name,1)
            break
    return result
