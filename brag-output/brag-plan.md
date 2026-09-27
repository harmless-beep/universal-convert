# Brag Plan: Universal Convert

## What is this app?
A "Convert With…" entry that lives in your right-click menu. Select any files — images, PDFs, Office docs — pick what you want, and it does the thing in one batch dialog with live progress, per-file results, and a working Cancel button. No editor, no upload, no web tab. Cross-platform desktop utility built with Python + Tkinter.

## The angle
The utility you wish you'd written yourself. It doesn't replace an app — it slots into the menu you already use every day and then gets out of the way.

## Hook (first 2-3 seconds)
Right-click menu animation: the context menu opens and "Convert With…" glows briefly as the cursor lands on it. Single word appears: "Convert."

## Key moments (the middle)
- 40 PNGs selected → cursor clicks "Convert With…" → one dialog opens pre-filled for the whole batch
- Action chosen (resize → Web 1920). Output folder preview shows the destination path before anything is written
- Progress bar fills 0→100% with live file name ("Converting shot_09.png…"). Cancel button active mid-run
- Bar hits green. Results window slides in: per-file ✓/✗ list with output names, "Open log" and "Copy all" buttons

## Outro / punchline
Final frame: the app name in clean type. Tagline: "Right-click. Convert. Done."

## User flow worth showing
Right-click files → "Convert With…" → single dialog → pick action/options → progress bar with live file label + Cancel → green status → per-file results list

## Tone
- Preset: polished
- Creative direction: quiet premium product film
- Interpretation: Slow, deliberate reveals. Clean negative space. Typography-first. The raw Tkinter UI is elevated into a premium, honest-to-the-product aesthetic — no fake plastic, but the motion and framing make it feel purpose-built.

## Format: landscape — 1920x1080
## Duration: 18s

## Visual identity (from the project)
- Background: #0f0f12 (elevated from native Tk default, deep enough for contrast)
- Text: #e8e8e8 (primary), #a0a0a8 (secondary/muted)
- Accent: #1a7a2e (the app's own success-green from the status line)
- Display font: Inter or system sans-serif (clean, geometric)
- Body font: Inter or system sans-serif (legible at small sizes)
- Strongest visual element: the context-menu → single dialog → results flow. The green progress completion is the emotional payoff.

## Share copy (draft)
Universal Convert: right-click any files, convert them in one dialog. Images, PDFs, Office docs — resize, compress, merge, split, batch. No editor, no upload, just the menu you already use.

## Audio direction
- Role: warm bed
- Music: happy-beats-business-moves-vol-11-by-ende-dot-app (clean, upbeat, professional)
- Music treatment: Start low (0.3), fade under final frame. Light presence throughout.
- Music cue guidance: Bundled preset track. 1-3 strong cues near: dialog opening (~1.5s), progress bar completion (~13s), logo landing (~16s)
- Audio-reactive treatment: subtle; progress bar fill and dialog reveals may breathe with RMS
- Audio-coupled moments:
  - Menu item glow on cursor hover (subtle click SFX)
  - "Convert" word appears with a clean type-on
  - Progress bar ticks forward with light UI click accents per file
  - Results list items slide in one by one with soft card sounds
  - Final logo lands with an announcement hit over a music swell
- SFX posture: sparse, motion-matched, professional restraint

## Storyboard

### Scene 1 — Right-click hook — 2.5s
Dark context menu slides up from cursor. "Convert With…" entry pulses once with an amber glow (#a05a00 from the app's warning color). Single word "Convert." fades in center screen with a clean type-on and a soft click SFX.
Sequential/interaction: Menu item pulse + text type-on arrive on separate 0.5s beats
Audio intent: Establishes the product's entry point with a satisfying click
Audio-coupled idea: Text types out with a subtle key-tick
Transition: clean crossfade → Scene 2

### Scene 2 — Dialog opens — 4s
The Tk-style dialog materializes (elevated, premium rendering): header reads "40 files selected", subtext "PNG · 40 · · 3 paths shown". Output preview line: "Output → /Converted". Radio row: Convert / Compress / Resize, Resize pre-selected. The quality/length of the dialog reveal is deliberate.
Sequential/interaction: Header → subtext → output line → radio options arrive over ~1.2s with soft card sounds
Audio intent: Calm, confident. The dialog is the product — treat it with respect
Audio-coupled idea: Each panel section reveals with a soft card sound synced to motion
Transition: soft crossfade → Scene 3

### Scene 3 — Progress in motion — 5s
Progress bar fills left to right. Live status: "Converting shot_09.png… (9/40)". Percentage ticks up: 23% → 46% → 71% → 94% → 100%. Cancel button is visible and enabled. Bar hits 100% and the status line goes green (#1a7a2e).
Sequential/interaction: Percentage ticks snap to beats. Bar fills smoothly with a final green flash.
Audio intent: Building confidence — the work is happening
Audio-coupled idea: Each percentage tick fires a soft UI click SFX; final green fill gets an announcement hit synced to a strong music cue
Transition: hard cut to green → Scene 4

### Scene 4 — Results list — 4s
Results window slides in. Top line: "40 files processed — 40 succeeded". List populates one by one with ✓ marks and output names: "✓  shot_01.png → shot_01.jpg", "✓  shot_02.png → shot_02.jpg", etc. "Open log" and "Copy all" buttons in the footer.
Sequential/interaction: 3-4 list rows slide in one by one with card sounds; rest appear as a group hold
Audio intent: Satisfaction — job complete, everything succeeded
Audio-coupled idea: List rows arrive with soft card-tap SFX on the beat grid
Transition: soft crossfade → Scene 5

### Scene 5 — Logo + tagline — 2.5s
Clean final frame. App name "Universal Convert" in large display type. Tagline beneath: "Right-click. Convert. Done." The green success accent (#1a7a2e) underlines the tagline subtly. Fades to deep background.
Sequential/interaction: Name drops in, tagline slides up from below
Audio intent: The final statement — confident, complete
Audio-coupled idea: Logo lands with an announcement hit over music swell; music fades under
Transition: hold to end

**Music mood for this video:** upbeat professional
**Audio summary:** Warm business bed carries the whole video. Sparse motion-matched SFX (clicks, card taps, announcement hits) punctuate each product moment. Music ducks under the final logo.
