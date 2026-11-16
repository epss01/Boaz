"""Read Home Village wall progress from the game's own export."""
from collections import Counter
from dataclasses import dataclass
import json
import re


@dataclass(frozen=True)
class WallProgress:
    tag: str
    timestamp: int
    town_hall: int
    target: int
    top_limit: int
    levels: Counter

    @property
    def remaining(self):
        below = sum(n for level, n in self.levels.items() if level < self.target - 1)
        need_top = self.top_limit - self.levels[self.target]
        return max(below, need_top)

    def eligible(self, level):
        return self.levels[level] > 0 and (level < self.target-1 or
               level == self.target-1 and self.levels[self.target] < self.top_limit)


def read_village(raw, tag, since, now):
    data = json.loads(raw)
    if not isinstance(data, dict) or not re.fullmatch(r'#[0289PYLQGRJCUV]+', tag) or data.get('tag') != tag:
        raise ValueError('Village export does not match the configured player tag')
    ts = data.get('timestamp')
    if type(ts) is not int or not since <= ts <= now + 2 or now-ts > 60:
        raise ValueError('Village export is stale or has an invalid timestamp')
    rows = data.get('buildings')
    if not isinstance(rows, list) or not all(isinstance(r, dict) and type(r.get('data')) is int for r in rows):
        raise ValueError('Invalid Home Village buildings')
    halls = [r for r in rows if r['data'] == 1000001]
    if len(halls) != 1 or type(halls[0].get('cnt', 1)) is not int or halls[0].get('cnt', 1) != 1:
        raise ValueError('Expected one Home Village Town Hall')
    th = halls[0].get('lvl')
    # Fully released wall tiers. Refuse newer halls until their segment cap is verified.
    if type(th) is not int or not 2 <= th <= 18:
        raise ValueError('Unverified wall limit for this Town Hall')
    target = th if th <= 8 else th+1
    levels = Counter()
    for row in rows:
        if row['data'] == 1000010:
            level, count = row.get('lvl'), row.get('cnt',1)
            if type(level) is not int or not 1 <= level <= target or type(count) is not int or not 1 <= count <= 500:
                raise ValueError('Invalid wall group in village export')
            levels[level] += count
    capacity = (25,50,75,100,125,175,225,250,275,300,300,300,325,325,325,325,325)[th-2]
    if not 1 <= levels.total() <= capacity:
        raise ValueError('Village export has no valid wall inventory')
    return WallProgress(tag,ts,th,target,levels.total(),levels)


def clipboard_export():
    import tkinter
    window = tkinter.Tk()
    window.withdraw()
    try:
        return window.clipboard_get()
    finally:
        window.destroy()
