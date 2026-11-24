#!/usr/bin/env node
// Render worker of `render_video` (design §9 step 6).
//
//   node engine/scripts/render.mjs <spec.json>
//
// Bundles the engine once, then renders either stills (one file per time) or one video file.
// The Python side (src/omniframe/tools/render.py) writes the spec and reads our stdout:
// every protocol line starts with "@@OMNIFRAME " followed by a JSON object, anything else is
// log noise from webpack/Chromium that Python keeps only for error messages.
//
//   {"event": "progress", "value": 0..1, "note": "..."}   progress of the whole script
//   {"event": "bundled"}                                     the bundle is built; engine/src is no longer read
//   {"event": "result", ...}                                 the last line on success (has `timing`, seconds)
//   {"event": "error", "message": "..."}                     the last line on failure
//
// Spec fields:
//   mode          "stills" | "media"
//   props         engine props (plan v2 with media paths relative to the public dir)
//   publicDir     directory served as the engine's public dir (fonts, media, audio)
//   bundleDir     where the bundle is written
//   serveUrl      an existing bundle folder to render from (skips the bundle step), optional
//   browser       path of Chrome/Edge, or null to let Remotion pick its own
//   concurrency   render workers, or null for the Remotion default
//   stills:       times [s], outputs [file per time], quality (JPEG 1..100)
//   media:        output (mp4 path), scale, crf

import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {bundle} from '@remotion/bundler';
import {openBrowser, renderMedia, renderStill, selectComposition} from '@remotion/renderer';

const ENGINE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const COMPOSITION_ID = 'Kinetic';
const FRAME_TIMEOUT_MS = 120_000;

// Share of the whole progress bar per stage.
const BUNDLE_SHARE = 0.25;

const emit = (obj) => process.stdout.write(`@@OMNIFRAME ${JSON.stringify(obj)}\n`);
const progress = (value, note) => emit({event: 'progress', value: Math.max(0, Math.min(1, value)), note});
// Seconds with milliseconds, from a monotonic clock.
const now = () => performance.now() / 1000;
const round = (s) => Math.round(s * 1000) / 1000;

async function main() {
  const specPath = process.argv[2];
  if (!specPath) {
    throw new Error('usage: node render.mjs <spec.json>');
  }
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8').replace(/^\uFEFF/, ''));
  const browserExecutable = spec.browser || null;
  const common = {logLevel: 'error', browserExecutable, timeoutInMilliseconds: FRAME_TIMEOUT_MS};
  const timing = {};

  progress(0, 'bundling the engine');
  let t0 = now();
  // A bundle of the same engine state from an earlier job (`serveUrl`) is served as it is.
  const serveUrl = spec.serveUrl || (await bundle({
    entryPoint: path.join(ENGINE_DIR, 'src', 'index.ts'),
    outDir: spec.bundleDir,
    publicDir: spec.publicDir,
    onProgress: (p) => progress((p / 100) * BUNDLE_SHARE, 'bundling the engine'),
  }));
  timing.bundle_s = round(now() - t0);
  timing.bundle_reused = Boolean(spec.serveUrl);
  // The bundle is self-contained: Python may now restore engine/src and free the engine lock.
  emit({event: 'bundled'});
  progress(BUNDLE_SHARE, 'opening the browser');

  t0 = now();
  const puppeteerInstance = await openBrowser('chrome', {
    browserExecutable,
    logLevel: 'error',
    chromiumOptions: {},
  });
  timing.browser_s = round(now() - t0);
  try {
    const composition = await selectComposition({
      ...common,
      serveUrl,
      id: COMPOSITION_ID,
      inputProps: spec.props,
      puppeteerInstance,
    });
    const meta = {
      width: composition.width,
      height: composition.height,
      fps: composition.fps,
      durationInFrames: composition.durationInFrames,
    };

    if (spec.mode === 'stills') {
      const files = [];
      const stillsStart = now();
      for (let i = 0; i < spec.times.length; i++) {
        const frame = Math.max(
          0,
          Math.min(composition.durationInFrames - 1, Math.round(spec.times[i] * composition.fps))
        );
        progress(BUNDLE_SHARE + ((1 - BUNDLE_SHARE) * i) / spec.times.length, `still ${i + 1} of ${spec.times.length}`);
        await renderStill({
          ...common,
          serveUrl,
          composition,
          inputProps: spec.props,
          frame,
          output: spec.outputs[i],
          imageFormat: 'jpeg',
          jpegQuality: spec.quality ?? 92,
          overwrite: true,
          puppeteerInstance,
        });
        files.push({time: spec.times[i], frame, file: spec.outputs[i]});
      }
      timing.stills_s = round(now() - stillsStart);
      emit({event: 'result', ...meta, files, timing});
    } else if (spec.mode === 'media') {
      progress(BUNDLE_SHARE, 'rendering frames');
      // renderMedia renders and encodes in one pass; `frames_encode_s` runs until the last frame is
      // encoded, and `mux_s` is what renderMedia does after that (audio mix and container).
      const mediaStart = now();
      let encodedAt = null;
      await renderMedia({
        ...common,
        serveUrl,
        composition,
        inputProps: spec.props,
        codec: 'h264',
        outputLocation: spec.output,
        crf: spec.crf,
        scale: spec.scale ?? 1,
        concurrency: spec.concurrency ?? null,
        overwrite: true,
        puppeteerInstance,
        onProgress: ({progress: p, renderedFrames, encodedFrames}) => {
          if (encodedAt === null && encodedFrames >= composition.durationInFrames) {
            encodedAt = now();
          }
          progress(
            BUNDLE_SHARE + (1 - BUNDLE_SHARE) * p,
            `rendered ${renderedFrames} / encoded ${encodedFrames} of ${composition.durationInFrames} frames`
          );
        },
      });
      const mediaEnd = now();
      timing.frames_encode_s = round((encodedAt ?? mediaEnd) - mediaStart);
      timing.mux_s = round(mediaEnd - (encodedAt ?? mediaEnd));
      emit({event: 'result', ...meta, file: spec.output, timing});
    } else {
      throw new Error(`unknown mode ${JSON.stringify(spec.mode)}`);
    }
  } finally {
    await puppeteerInstance.close({silent: true}).catch(() => undefined);
  }
}

main().then(
  () => process.exit(0),
  (err) => {
    emit({event: 'error', message: String((err && err.stack) || err)});
    process.exit(1);
  }
);
