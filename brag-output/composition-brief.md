# Hyperframes Composition Brief: Universal Convert

## Objective
Create a short launch-style brag video for Universal Convert.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 18s

## Source Material
- Project root: `C:\Users\retro\universal-convert-brag`
- Primary files read: README.md, main.py, ui/dialog.py, docs/*.png (screenshots)
- Product name: Universal Convert
- Tagline / strongest claim: "Right-click. Convert. Done."
- Key UI or visual moment to recreate: The context menu → dialog → progress → results flow
- Copy that must appear verbatim:
  - "Convert With…"
  - "Convert."
  - "40 files selected"
  - "Output → /Converted"
  - "40 files processed — 40 succeeded"
  - "Right-click. Convert. Done."

## Creative Direction
- Tone preset: polished
- Creative direction: quiet premium product film
- Interpretation: Slow, deliberate reveals. Clean negative space. Typography-first. The raw Tkinter UI is elevated into a premium, honest-to-the-product aesthetic — no fake plastic, but the motion and framing make it feel purpose-built.
- Angle: The utility you wish you'd written yourself. It doesn't replace an app — it slots into the menu you already use every day and then gets out of the way.
- Hook: Right-click menu animation — "Convert With…" glows as cursor lands on it. Word "Convert." appears center screen.
- Outro / punchline: Final frame with app name and tagline.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Over-animation that obscures the product UI

## Visual Identity
- Background: #0f0f12
- Text: #e8e8e8 (primary), #a0a0a8 (secondary/muted)
- Accent: #1a7a2e (success-green from the app's status line)
- Display font: Inter (via CDN) or system-ui fallback
- Body font: Inter (via CDN) or system-ui fallback
- Visual references from the project:
  - The right-click context menu with "Convert With…" entry (docs/step1-menu.png)
  - The single dialog for 40 files (docs/step2-options.png)
  - Progress bar with live file name (docs/step3-progress.png)
  - Green completion state (docs/step4-done.png)
  - Per-file results list (docs/step5-results.png)

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. Right-click hook — 2.5s — Menu slides up, "Convert With…" pulses, "Convert." types on
2. Dialog opens — 4s — Elevated dialog materializes with panels revealing sequentially
3. Progress in motion — 5s — Bar fills 0→100%, live status ticks, green completion
4. Results list — 4s — Window slides in, rows populate one by one with checkmarks
5. Logo + tagline — 2.5s — App name drops, tagline slides up, green underline

## Audio
- Audio role: warm bed
- Audio arc: Consistent presence. Sparse SFX punctuate key product moments. Music fades under final logo.
- Music: happy-beats-business-moves-vol-11-by-ende-dot-app.mp3
- Music treatment: Start at volume 0.3. Fade to 0.15 under final logo. Ducking on any audio-coupled moments.
- Music cue guidance: Bundled preset track available. 1-3 strong cues near: dialog opening (~1.5s), progress bar completion (~13s), logo landing (~16s). Beat grid for sequential reveals in Scenes 2, 3, 4.
- Audio-reactive treatment: subtle; progress bar fill and dialog panel reveals may breathe with RMS
- Audio-coupled moments:
  - Scene 1: Menu item pulse + "Convert." type-on with key-tick SFX
  - Scene 2: Dialog panels reveal with soft card sounds on beat grid
  - Scene 3: Progress percentage ticks with UI click SFX; final green flash with announcement hit
  - Scene 4: Results rows slide in with card-tap SFX on beat grid
  - Scene 5: Logo lands with announcement hit over music swell; music fades
- SFX selection guidance: Use `skills/brag/assets/sfx/sfx-analysis.md` for selection. Prefer low high-frequency-risk files for repeated or polished moments. Use interface clicks for UI actions, card sounds for list/item reveals, announcement hits for major payoffs.
- Exact SFX choice: Hyperframes should choose filenames, timestamps, density, and volume based on the implemented animation.
- Audio files: copy the chosen music and any Hyperframes-selected SFX into `brag-output/composition/assets/`

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). /brag is its own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo / launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project.
- Keep all text readable in the final render.
- Keep the video within 15-25 seconds.
- Include the planned music/SFX layer unless audio was explicitly disabled or documented as intentionally silent.
- Treat `/brag` audio notes as guidance, not a fixed cue sheet. Choose SFX after the visual animation exists.
- Treat music cue metadata as optional timing hints. Hyperframes decides exact animation timing and should ignore cues that hurt readability, scene pacing, or the product story.
- Major reveals may move toward nearby strong cues within about 0.15s. Smaller entrances may align to nearby beat points within about 0.10s. Use only 1-3 strong cue locks in a 15-25s video unless the edit clearly benefits from more.
- Use SFX to support motion and interaction: card sounds for card-like reveals, short announcement cues for major payoffs, key/click sounds for text or user actions, and restraint when the edit is already busy.
- Honor planned music treatment such as fade-outs, ducking, beat-aligned reveals, or letting a final SFX ring over the music, using the best Hyperframes-supported implementation.
- When music is present and the treatment is not `none`, consider Hyperframes audio-reactive workflow: extract audio data and use RMS/frequency bands for subtle, brand-specific motion. Good targets are glow, depth, background warmth, card presence, title emphasis, or other existing visual elements. Avoid waveform/equalizer visuals, musical-note graphics, generic particle systems, strobing, or heavy pulsing.
- Use local assets for audio and any required runtime/media dependencies when possible.
- Run `hyperframes check` before render — it is brag's single gate.