// remap.js — retime the original 156.6 s film onto 潮汐 (31.84 s, 118 BPM).
//
// The film is animated on 88 BPM beats. Inside every segment the film plays at 118/88 = 1.3409x,
// so one film beat becomes exactly one song beat: every bounce, splash and flip in the film lands
// on our beat. Each lyric line gets one segment, and every cut is made exactly on a beat (卡点).
//
// Segment starts are film *beats* B(k) = 0.21 + k·60/88, so the film's own internal cuts also stay
// on the 118 grid. Song cuts are on the 118 grid: t = 0.05 + b·60/118.
const SLOW = 118 / 88;                     // film seconds per song second
const SONG0 = 0.05, SONG_BEAT = 60 / 118;  // our downbeat grid
const FILM0 = 0.21, FILM_BEAT = 60 / 88;   // the film's downbeat grid
const tSong = n => SONG0 + n * SONG_BEAT;
const tFilm = k => FILM0 + k * FILM_BEAT;

// [song beat, film beat] — the shot that starts on that song beat.
const CUTS = [
  [0   , 0  ],   // 0.05  curtain up: the painted backdrop and 潮汐, Clawd through the trapdoor
  [4   , 115],   // 2.08  我奔跑寻找昔日的足迹 — the museum of obsolete mainframes
  [8   , 130],   // 4.12  夕阳下倒影迷人的美丽 — the moon over the dusk road
  [12  , 136],   // 6.15  可我却丢失故事和你 — alone at the cliff, then the fall
  [16  , 43 ],   // 8.19  你说过向往大海的神秘 — the teal sea-shoggoth
  [20  , 66 ],   // 10.22 也憧憬我们遗失的过去 — floating in space above the planet
  [24  , 78 ],   // 12.25 分享给大海秘密 — two Clawds, hearts, a secret
  [28  , 84 ],   // 14.29 (build) — the giant heart Clawd
  [32  , 95 ],   // 16.32 蓝色的海底 — the deep blue: a moon adrift in space
  [36  , 120],   // 18.35 远山的风景 — the road sign, the motorcycle, the hills at dusk
  [40  , 148],   // 20.39 我们的距离 遥不可及 — the Clawd planet, one figure far off
  [44  , 189],   // 22.42 退守的爱情 还剩下回忆 — the chalkboard flashback
  [48  , 182],   // 24.45 疯狂的寻觅 你的身影 — red alert
  [52  , 162],   // 26.49 the crescendo — the endless tower of Clawds
  [56  , 202],   // 28.52 the reveal: was it all for show?
  [58  , 210],   // 29.53 the bows
  [59.5, 222 ]   // 30.30 the house curtain falls on the big 潮汐 title
];

const INTRO_RATE = .63;                    // the title card holds through the 2 s intro
function SCENE_T(t) {
  if (t < SONG0 + 4 * SONG_BEAT) return clamp(FILM0 + (t - SONG0) * INTRO_RATE, 0, 156.55);
  const beats = (t - SONG0) / SONG_BEAT;
  let i = 0;
  while (i + 1 < CUTS.length && beats >= CUTS[i + 1][0]) i++;
  const [b, f] = CUTS[i];
  return clamp(tFilm(f) + (beats - b) * SLOW * FILM_BEAT, 0, 156.55);
}

if (location.search.includes('raw')) window.SCENE_T = t => t;   // ?raw — preview the film itself
