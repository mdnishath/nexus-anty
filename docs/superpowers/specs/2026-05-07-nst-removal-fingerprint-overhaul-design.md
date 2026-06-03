# Design Spec: NST Removal + Full Fingerprint Overhaul

**Date:** 2026-05-07  
**Scope:** 3 phases — NST API removal, fingerprint JS modules, profile UI update  
**Target:** Undetectable local browser profiles — 100% on whoer.net, Android support  

---

## Background

The current system uses NST Browser's cloud API (`localhost:8848/api/v2`) to manage browser profiles. This creates dependency on a paid subscription service. The user wants:

1. Full local operation — no external API
2. Comprehensive browser fingerprint spoofing native to every profile
3. Android/iOS mobile emulation
4. All settings configurable per-profile in the UI

The base binary stays **nstchrome.exe** (already installed, already a patched Chromium). NST API is completely removed. Additional fingerprinting is layered on top via Playwright `addInitScript`.

---

## Phase 1: NST API Removal

### Goal
Remove all NST API calls. Every profile uses local StealthChrome (`nstchrome.exe` or system Chrome fallback). No external API dependency.

### Files Changed

#### `config/browser.json`
```json
{
  "use_nexus": true,
  "use_nst": false,
  "chrome_version": 146
}
```

#### `shared/nexus_profile_manager.py`
- **Remove**: `_nst_post`, `_nst_get`, `_nst_delete`, `_nst_patch`, `_nst_api_key`, `_nst_base`
- **Remove**: `NST_API_KEY` and `NST_API_BASE` constants
- **Remove**: All NST API calls in `create_profile`, `update_profile`, `delete_profile`, `launch_and_connect`, `stop_nst_browser`
- **Keep**: Local JSON profile storage, `_read_profiles`, `_write_profiles`, `_profiles_file`
- **Keep**: `create_profile` — only local JSON + profile_dir creation
- **Keep**: `launch_and_connect` — always StealthChrome, never API
- **Keep**: `stop_nst_browser` → rename to `stop_profile_browser`, always kills StealthChrome process
- **Profile schema change**: Remove `nst_profile_id` field
- **Migration**: On startup, any profile with `engine='nst'` is auto-treated as `engine='nexus'`; `nst_profile_id` field ignored

#### `shared/profile_manager.py`
- Remove NST-specific `context.close()` skip logic (the fix applied today)
- Unified cleanup: always close context, always stop StealthChrome
- Remove `engine == 'nst'` branches; single path for all profiles

#### `electron-app/renderer/modules/profiles.js`
- `const engine = 'nst'` → `const engine = 'nexus'`
- Remove any NST-specific UI text ("NST Browser", "NST API", etc.)
- Profile summary: "Engine: NexusBrowser (Local)" instead of "NST"

#### `electron-app/backend/server.py`
- Remove NST-specific API routes if any
- `engine` parameter in batch-login route defaults to `'nexus'`

### Profile Schema (Post-Phase-1)
```json
{
  "id": "nexus-abc123",
  "engine": "nexus",
  "name": "john_doe",
  "email": "john@gmail.com",
  "group": "default",
  "status": "logged_in",
  "profile_dir": "C:/path/to/profiles/nexus-abc123",
  "proxy": {"type": "socks5", "host": "...", "port": "1080"},
  "fingerprint": { "...existing fields..." },
  "fingerprint_config": { "...new phase 2 fields..." },
  "password": "...",
  "totp_secret": "...",
  "backup_codes": []
}
```

### Success Criteria
- App starts without NST running
- Profiles create, open, login without NST API
- All existing profiles (engine=nst) work as engine=nexus

---

## Phase 2: Fingerprint JS Modules

### Goal
Per-profile deterministic fingerprint spoofing injected into every page via `addInitScript`. Seed-based: same profile always produces same fingerprint values (consistent identity).

### Architecture

```
Profile fingerprint_config JSON
        ↓
FingerprintInjector (Python)
  → loads JS templates
  → substitutes seed values
        ↓
stealth_chrome.py (launch)
  → context.add_init_script(combined_script)
        ↓
Every page (before any JS runs)
  → Canvas, WebGL, Audio, etc. all spoofed
```

### JS Module Files (`shared/fingerprints/`)

Each module is a self-contained JS file with `{{PLACEHOLDER}}` substitutions.

#### `canvas.js` — Canvas Noise
- Patches `HTMLCanvasElement.prototype.toDataURL` and `getContext('2d').getImageData`
- Seeds a deterministic PRNG from `{{CANVAS_SEED}}`
- Adds ±1-3 pixel noise per call — consistent per seed, different per profile
- Mode: `off` (no-op) | `noise` (inject) | `block` (return blank)

#### `client_rects.js` — ClientRects Noise
- Patches `Element.prototype.getBoundingClientRect` and `getClientRects`
- Adds ±0.0001–0.0005 float noise seeded from `{{NOISE_SEED}}`
- Mode: `off` | `noise`

#### `webgl_image.js` — WebGL Pixel Noise
- Patches `WebGLRenderingContext.prototype.readPixels`
- Flips 1 bit per 1000 bytes seeded from `{{NOISE_SEED}}`
- Mode: `off` | `noise`

#### `webgl_meta.js` — WebGL Metadata Spoofing
- Patches `getParameter(VENDOR)` → `"{{WEBGL_VENDOR}}"`
- Patches `getParameter(RENDERER)` → `"{{WEBGL_RENDERER}}"`
- Patches `getExtension('WEBGL_debug_renderer_info')` unmasked strings
- Default: `"Intel Inc."` / `"Intel(R) Iris(R) Xe Graphics"`
- Mode: `off` | `custom` | `real`

#### `audio.js` — AudioContext Noise
- Patches `AnalyserNode.prototype.getFloatFrequencyData` and `getByteFrequencyData`
- Adds deterministic noise to float arrays seeded from `{{AUDIO_SEED}}`
- Mode: `off` | `noise`

#### `media_devices.js` — Device Masking
- Patches `navigator.mediaDevices.enumerateDevices`
- Returns controlled list: `{{VIDEO_INPUTS}}` video, `{{AUDIO_INPUTS}}` audioinput, `{{AUDIO_OUTPUTS}}` audiooutput
- When count is 0: returns empty array for that type
- Mode: `real` | `masked`

#### `fonts.js` — Font List Masking
- Patches `document.fonts` iteration
- Patches `CanvasRenderingContext2D.prototype.measureText` to add noise
- Returns only a curated OS-appropriate font list seeded from profile OS type
- Mode: `real` | `masked`

#### `webgpu.js` — WebGPU Masking
- Sets `navigator.gpu = undefined`
- Or returns a controlled `GPUAdapter` description
- Mode: `disabled` | `real`

#### `speech.js` — Speech Voices Masking
- Patches `speechSynthesis.getVoices`
- Returns OS-appropriate voice list (Windows: 3 voices, Mac: 5 voices)
- Mode: `real` | `masked`

#### `port_scan.js` — Port Scan Protection
- Patches `WebSocket` constructor — blocks connections to `localhost` / `127.0.0.1` / `::1`
- Patches `fetch` — blocks requests to local addresses
- Allowed: proxy WebSocket connections (non-local)
- Mode: `off` | `on`

#### `device_name.js` — Device Name / Navigator Patches
- `navigator.doNotTrack` → `"{{DNT}}"` (1 or unspecified)
- `navigator.userAgentData.getHighEntropyValues` → controlled response
- Removes battery API (`navigator.getBattery`)

### `FingerprintInjector` (Python — `shared/fingerprint_injector.py`)

```python
class FingerprintInjector:
    def build_script(self, fingerprint_config: dict, fingerprint: dict) -> str:
        """Combines all enabled modules into one <script> string."""
```

- Reads JS templates from `shared/fingerprints/`
- Substitutes `{{PLACEHOLDERS}}` with profile values
- Concatenates into single script (reduces round-trips)
- Called from `stealth_chrome.py → inject_scripts()`

### `fingerprint_config` Schema

```json
{
  "canvas_mode": "noise",
  "client_rects_mode": "noise",
  "audio_mode": "noise",
  "webgl_image_mode": "noise",
  "webgl_meta_mode": "custom",
  "webgl_vendor": "Intel Inc.",
  "webgl_renderer": "Intel(R) Iris(R) Xe Graphics",
  "media_devices_mask": true,
  "video_inputs": 0,
  "audio_inputs": 0,
  "audio_outputs": 0,
  "fonts_mask": true,
  "webgpu_mode": "disabled",
  "speech_mask": true,
  "dnt": true,
  "port_scan_protection": true
}
```

**Defaults** (applied to all new profiles and existing profiles missing this field):  
All modes enabled, Intel GPU, 0 media devices, all masks on.

### Seed Strategy
- `canvas_seed` = `fingerprint.noise_seed`
- `audio_seed` = `fingerprint.audio_seed` (or `noise_seed ^ 0xA0D10`)
- `webgl_seed` = `noise_seed ^ 0x7F5E`
- Same profile always gets identical fingerprint values → consistent identity across sessions

### Success Criteria
- whoer.net shows no canvas/WebGL/audio fingerprint leaks
- Media devices show 0 inputs/outputs
- Port scan protection blocks local port checks
- Each profile has unique but consistent canvas/audio hash

---

## Phase 3: Profile UI Update

### Goal
Make all fingerprint settings configurable per-profile in the create/edit modal.

### Hardware Tab (Replace Existing)

```
┌─ Hardware ──────────────────────────────────────────────────┐
│                                                             │
│  Canvas Mode          [Off] [Noise ✓] [Block]              │
│  ClientRects Mode     [Off] [Noise ✓]                      │
│  AudioContext Mode    [Off] [Noise ✓]                      │
│  WebGL Image Mode     [Off] [Noise ✓]                      │
│  WebGL Meta Mode      [Off] [Custom ✓] [Real]              │
│    Vendor:    [Intel Inc.                    ▼]             │
│    Renderer:  [Intel(R) Iris(R) Xe Graphics  ▼]            │
│                                                             │
│  ── Media Devices ─────────────────────────────────────    │
│  Enable Masking       [On ✓] [Off]                         │
│    Video Inputs       [0 ▼]                                 │
│    Audio Inputs       [0 ▼]                                 │
│    Audio Outputs      [0 ▼]                                 │
│                                                             │
│  ── Privacy ───────────────────────────────────────────    │
│  Fonts Masking        [On ✓] [Off]                         │
│  WebGPU Mode          [Disabled ✓] [Real]                  │
│  Speech Voices        [Masked ✓] [Real]                     │
│  DoNotTrack           [On ✓] [Off]                         │
│  Port Scan Protection [On ✓] [Off]                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Advanced Tab — Storage Options
```
┌─ Advanced ──────────────────────────────────────────────────┐
│  Local Storage        [On ✓] [Off]                          │
│  Extension Storage    [On ✓] [Off]                          │
│  Bookmarks Saving     [On ✓] [Off]                          │
│  History Saving       [On ✓] [Off]                          │
│  Password Saving      [Off ✓] [On]                          │
│  Session Saving       [On ✓] [Off]                          │
└─────────────────────────────────────────────────────────────┘
```
Storage options map to Chrome flags (`--disable-local-storage`, etc.) applied at launch.

### OS Tab — Android/iOS Added
```
OS:  [Random] [Windows] [macOS] [Linux] [Android ✓] [iOS]
```
Android/iOS selection → mobile UA + 412×915 viewport + touch emulation via CDP.

### Profile Summary Panel
```
Engine:      NexusBrowser (Local)
OS:          Windows 10 / Android 14
Canvas:      Noise (seed: 4f2a1b)
WebGL:       Intel Inc. / Intel Iris Xe
Media:       0 video / 0 audio
Privacy:     DoNotTrack ON, Port Scan Protection ON
```

### Success Criteria
- All fingerprint settings save to profile JSON
- Edit modal loads existing settings correctly
- Batch login uses saved fingerprint_config per profile
- Summary panel shows key fingerprint values

---

## WebGL Vendor/Renderer Presets

Common values used by real users (to randomize from by default):

| Vendor | Renderer |
|--------|---------|
| Intel Inc. | Intel(R) Iris(R) Xe Graphics |
| Intel Inc. | Intel(R) UHD Graphics 620 |
| NVIDIA Corporation | NVIDIA GeForce RTX 3060 |
| NVIDIA Corporation | NVIDIA GeForce GTX 1650 |
| Google Inc. (Intel) | ANGLE (Intel, Intel(R) Iris(R) Xe Graphics) |
| Google Inc. (NVIDIA) | ANGLE (NVIDIA, GeForce RTX 3060) |

New profiles get a random preset. User can override in Hardware tab.

---

## Implementation Order

1. **Phase 1** — NST removal (2-3 days)
   - Config change, nexus_profile_manager.py cleanup, profile_manager.py unification, frontend engine fix
   - Test: create profile, open browser, batch login — all without NST running

2. **Phase 2** — Fingerprint JS modules (3-4 days)
   - Write 10 JS modules
   - Write FingerprintInjector Python class
   - Wire into stealth_chrome.py launch
   - Test: whoer.net, browserleaks.com, fingerprintjs.com

3. **Phase 3** — UI (2-3 days)
   - Hardware tab redesign
   - Advanced tab storage options
   - OS tab Android/iOS
   - Save/load fingerprint_config to/from profile JSON

---

## Non-Goals (Out of Scope)
- Building custom Chromium from source
- Real ADB Android device support
- TLS fingerprint randomization (requires binary patching)
- IPv6 leak protection beyond existing Chrome flags
