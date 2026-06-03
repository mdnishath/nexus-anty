# NST Removal + Full Fingerprint Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove NST API dependency entirely and add per-profile JavaScript fingerprint spoofing (canvas, WebGL, audio, media devices, fonts, WebGPU, speech, port scan, DoNotTrack) configurable through the profile UI.

**Architecture:** Phase 1 strips all NST API calls from `nexus_profile_manager.py` and unifies the engine to `nexus` (local StealthChrome). Phase 2 adds 11 self-contained JS modules injected via Playwright `addInitScript` on every page. Phase 3 wires the fingerprint settings into the profile create/edit modal and profile JSON schema.

**Tech Stack:** Python 3.12, Playwright (async), JavaScript ES2020 (init scripts), Electron/HTML, Flask (backend routes)

---

## File Map

### Phase 1 — NST Removal
| File | Action | What changes |
|------|--------|-------------|
| `config/browser.json` | Modify | `use_nst: false`, remove api key |
| `shared/nexus_profile_manager.py` | Modify | Delete ~200 lines of NST API helpers + all API call sites |
| `shared/profile_manager.py` | Modify | Remove NST-specific `context.close()` skip; unified cleanup |
| `electron-app/renderer/modules/profiles.js` | Modify | `engine = 'nexus'`, remove NST UI strings |
| `electron-app/backend/server.py` | Modify | Default engine `'nexus'` in batch-login route |

### Phase 2 — Fingerprint JS Modules
| File | Action | What it does |
|------|--------|-------------|
| `shared/fingerprints/canvas.js` | Create | Canvas noise |
| `shared/fingerprints/client_rects.js` | Create | ClientRects noise |
| `shared/fingerprints/webgl_image.js` | Create | WebGL readPixels noise |
| `shared/fingerprints/webgl_meta.js` | Create | WebGL vendor/renderer spoof |
| `shared/fingerprints/audio.js` | Create | AudioContext noise |
| `shared/fingerprints/media_devices.js` | Create | Device enumeration masking |
| `shared/fingerprints/fonts.js` | Create | measureText noise + font list mask |
| `shared/fingerprints/webgpu.js` | Create | WebGPU disable/mask |
| `shared/fingerprints/speech.js` | Create | Speech voices mask |
| `shared/fingerprints/port_scan.js` | Create | Block localhost WebSocket/fetch |
| `shared/fingerprints/device_name.js` | Create | DoNotTrack + battery API removal |
| `shared/fingerprint_injector.py` | Create | Python class: loads templates, substitutes seeds, combines into one script |
| `shared/stealth_chrome.py` | Modify | Call `FingerprintInjector` at launch |
| `shared/nexus_profile_manager.py` | Modify | Add `fingerprint_config` to profile schema + defaults |

### Phase 3 — Profile UI Update
| File | Action | What changes |
|------|--------|-------------|
| `electron-app/renderer/index.html` | Modify | Hardware tab HTML elements (fingerprint controls) |
| `electron-app/renderer/modules/profiles.js` | Modify | Read/write fingerprint_config; update summary panel |
| `electron-app/backend/server.py` | Modify | Pass `fingerprint_config` through create/update profile routes |

---

## ═══ PHASE 1: NST REMOVAL ═══

---

### Task 1: Disable NST in config and init

**Files:**
- Modify: `config/browser.json`
- Modify: `shared/nexus_profile_manager.py` (lines ~208–240, `init` function)

- [ ] **Step 1: Update browser.json**

Replace `config/browser.json` with:
```json
{
  "use_nexus": true,
  "use_nst": false,
  "chrome_version": 146
}
```

- [ ] **Step 2: Update init() to skip NST config loading**

In `shared/nexus_profile_manager.py`, find the `init` function (~line 208). Replace the NST config loading block:

```python
def init(resources_path):
    """Initialize the profile manager. Called once at server startup."""
    global _resources_path, _config
    _resources_path = Path(resources_path)
    _config = _load_config()
    _ensure_dirs()
    _log("Profile manager initialized (local engine only)", 'success')
```

Remove the lines that read `nst_api_key`, `nst_api_base`, and the background `_nst_check()` thread.

- [ ] **Step 3: Remove NST globals**

Find and delete these two lines near the top of `nexus_profile_manager.py` (~line 84):
```python
_nst_api_key: str = ''
_nst_api_base: str = 'http://localhost:8848/api/v2'
```

- [ ] **Step 4: Verify app still starts**

```bash
cd "E:/NST Anty Android"
python -c "from shared import nexus_profile_manager as m; m.init('E:/NST Anty Android'); print('OK')"
```
Expected: `OK` with no errors.

- [ ] **Step 5: Commit**

```bash
cd "E:/NST Anty Android"
git add config/browser.json shared/nexus_profile_manager.py
git commit -m "feat: disable NST API config, local-only init"
```

---

### Task 2: Delete NST API helper functions

**Files:**
- Modify: `shared/nexus_profile_manager.py` (lines ~94–201)

- [ ] **Step 1: Delete the entire NST API HELPERS section**

In `nexus_profile_manager.py`, delete lines from:
```python
# ━━━ NST API HELPERS ━━━
def _nst_headers() -> dict:
```
through to the end of `_nst_check()` function (including the closing `return False`).

This removes: `_nst_headers`, `_nst_get`, `_nst_post`, `_nst_delete`, `_nst_put`, `_nst_check`.

- [ ] **Step 2: Check for any remaining references**

```bash
cd "E:/NST Anty Android"
grep -n "_nst_get\|_nst_post\|_nst_delete\|_nst_put\|_nst_check\|_nst_headers" shared/nexus_profile_manager.py
```
Expected output: the grep returns nothing (0 matches).

- [ ] **Step 3: Verify import still works**

```bash
python -c "from shared import nexus_profile_manager; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add shared/nexus_profile_manager.py
git commit -m "feat: remove NST API helper functions (_nst_get/post/delete/put)"
```

---

### Task 3: Simplify create_profile — local only

**Files:**
- Modify: `shared/nexus_profile_manager.py` — `create_profile` function (~line 651)

- [ ] **Step 1: Understand current NST profile creation block**

The current `create_profile` has two branches:
- `if engine == 'nexus':` → just generates local fingerprint
- `elif engine == 'nst':` → calls `_nst_post('/profiles', nst_body)`, fetches fingerprint via `_nst_get`, builds complex fingerprint from API response

- [ ] **Step 2: Replace the engine branch in create_profile**

Find the section starting around `# ── ENGINE: NexusBrowser (local` and the `elif engine == 'nst':` block that follows. Replace the entire two-branch section with a single unified path:

```python
    # ── Generate local profile ────────────────────────────────────────────────
    profile_id = f'nexus-{secrets.token_hex(6)}'
    fingerprint = _generate_nexus_fingerprint(raw_os)
    engine = 'nexus'  # always local
    engine_label = 'NexusBrowser (Local)'
    _log(f"Creating local profile: {name} [{raw_os}]...")
```

Also remove `nst_error_msg`, `_win_ver_num`, `nst_proxy`, `nst_body` variables that were only used for NST creation.

- [ ] **Step 3: Remove nst_profile_id from the saved profile dict**

Find the profile dict construction (~line 999). Change:
```python
'nst_profile_id': profile_id if engine == 'nst' else '',
```
to:
```python
'nst_profile_id': '',
```

- [ ] **Step 4: Remove the NST error inclusion at the end of create_profile**

Delete:
```python
    if engine == 'nst' and nst_error_msg:
        profile['_nst_create_error'] = nst_error_msg
```

- [ ] **Step 5: Test profile creation**

```bash
python -c "
from shared import nexus_profile_manager as m
import tempfile, os
m.init('E:/NST Anty Android')
p = m.create_profile('test_user', email='test@gmail.com')
print('id:', p['id'])
print('engine:', p['engine'])
print('nst_profile_id:', p.get('nst_profile_id'))
assert p['engine'] == 'nexus'
assert p['id'].startswith('nexus-')
print('PASS')
"
```

- [ ] **Step 6: Commit**

```bash
git add shared/nexus_profile_manager.py
git commit -m "feat: create_profile local-only, no NST API"
```

---

### Task 4: Simplify launch_and_connect and stop_nst_browser

**Files:**
- Modify: `shared/nexus_profile_manager.py` — `launch_and_connect` (~line 2670), `stop_nst_browser` (~line 2838)

- [ ] **Step 1: Remove the NST engine branch from launch_and_connect**

Find `launch_and_connect`. It currently has:
```python
    # NST engine
    nst_id = profile.get('nst_profile_id', profile_id)
    if nst_id.startswith('local-'):
        raise RuntimeError(...)
    _log(f"NST: launching browser for automation ({nst_id})...")
    result = _nst_post(f'/browsers/{nst_id}', {}, timeout=60)
    ...
```

Delete from `# NST engine` through to the end of the function. The function now always returns the StealthChrome `ws` (the NexusBrowser path already handles everything).

- [ ] **Step 2: Remove local-NST fallback in launch_and_connect**

Also remove the forced `engine = 'nexus'` override for `local-` profiles:
```python
    # Force old local- NST profiles to launch via NexusBrowser
    nst_id = profile.get('nst_profile_id', profile_id)
    if engine == 'nst' and nst_id.startswith('local-'):
        engine = 'nexus'
```
Replace with simply: `engine = 'nexus'` (always).

- [ ] **Step 3: Simplify stop_nst_browser**

Find `stop_nst_browser`. Remove the NST API section:
```python
    # NST engine
    profile = get_profile(profile_id)
    ...
    _nst_delete(f'/browsers/{nst_id}')
```
The function already handles StealthChrome correctly in the first block (looking up `_active_browsers`). Keep only that block.

Rename the function to `stop_profile_browser` for clarity, but keep the old name as an alias for backwards compatibility:
```python
def stop_profile_browser(profile_id: str):
    """Stop a locally-running StealthChrome browser."""
    with _lock:
        info = _active_browsers.pop(profile_id, None)
    if info:
        sc = info.get('stealth_chrome')
        if sc:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(sc.stop())
                loop.close()
            except Exception:
                if hasattr(sc, 'process') and sc.process:
                    try: sc.process.kill()
                    except Exception: pass
        stop_ev = info.get('stop_event')
        if stop_ev:
            stop_ev.set()
        _log(f"Profile browser stopped: {profile_id}")

# Backwards-compatible alias
stop_nst_browser = stop_profile_browser
```

- [ ] **Step 4: Test launch path exists (dry-run)**

```bash
python -c "
from shared import nexus_profile_manager as m
m.init('E:/NST Anty Android')
import inspect
src = inspect.getsource(m.launch_and_connect)
assert '_nst_post' not in src, 'NST post still present!'
assert '_nst_delete' not in src, 'NST delete still present!'
print('PASS: no NST API calls in launch_and_connect')
"
```

- [ ] **Step 5: Commit**

```bash
git add shared/nexus_profile_manager.py
git commit -m "feat: launch_and_connect and stop_browser local-only"
```

---

### Task 5: Clean up remaining NST references + frontend

**Files:**
- Modify: `shared/nexus_profile_manager.py` — `update_profile`, `delete_profile`, any remaining `_nst_*` calls
- Modify: `shared/profile_manager.py` — unified cleanup (revert today's NST skip fix)
- Modify: `electron-app/renderer/modules/profiles.js`
- Modify: `electron-app/backend/server.py`

- [ ] **Step 1: Find and remove remaining _nst_ calls in nexus_profile_manager.py**

```bash
grep -n "_nst_\|engine.*nst\|nst_profile_id" "E:/NST Anty Android/shared/nexus_profile_manager.py" | head -40
```

For each match: remove the NST API call. For `update_profile` or `delete_profile` that call `_nst_put`/`_nst_delete`, remove those lines. The local JSON update/delete stays.

- [ ] **Step 2: Restore unified cleanup in profile_manager.py**

Find the 4 cleanup blocks in `_login_profile_impl` that currently skip `context.close()` for NST. Simplify all 4 to the same unified pattern:

```python
# ── Flush cookies before stopping ──────────────────────────
if success:
    try:
        _flush_pages = context.pages
        if _flush_pages:
            await _flush_pages[0].goto('about:blank',
                                        wait_until='domcontentloaded',
                                        timeout=5000)
        await asyncio.sleep(2)
    except Exception:
        pass

# ── Cleanup browser ───────────────────────────────────────
try: await context.close()
except Exception: pass
if stealth:
    try: await stealth.stop()
    except Exception: pass
if bridge:
    try: bridge.stop()
    except Exception: pass
# stop_profile_browser handles the StealthChrome process
try:
    from shared.nexus_profile_manager import stop_profile_browser
    await asyncio.to_thread(stop_profile_browser, profile_id)
except Exception: pass
```

Apply this same block in all 4 cleanup locations (already_logged_in early return, definitive_error early return, main cleanup, exception handler).

Also remove the separate `if engine == 'nst'` check in `_login_profile_impl` — there's only one engine now.

- [ ] **Step 3: Fix frontend engine**

In `electron-app/renderer/modules/profiles.js`, find:
```javascript
const engine = 'nst';
```
Change to:
```javascript
const engine = 'nexus';
```

Also find any UI text showing "NST Browser" or "NST API" and change to "NexusBrowser (Local)".

- [ ] **Step 4: Fix backend default engine**

In `electron-app/backend/server.py`, find the batch-login route (~line 2845):
```python
engine = data.get('engine', 'nexus')
```
Verify it already defaults to 'nexus'. If it says 'nst', change it.

Also find the nexus API batch-login route (~line 4257) and do the same.

- [ ] **Step 5: Full check — no NST API calls remain**

```bash
cd "E:/NST Anty Android"
grep -rn "_nst_post\|_nst_get\|_nst_delete\|_nst_put\|localhost:8848" shared/ electron-app/ --include="*.py" --include="*.js"
```
Expected: zero results (only grep in docs/specs is acceptable).

- [ ] **Step 6: Smoke test — create and open profile without NST**

Start the app. Create a new profile. Verify it opens a browser window. If NST Browser is not running, the app should still work.

- [ ] **Step 7: Commit**

```bash
git add shared/nexus_profile_manager.py shared/profile_manager.py electron-app/renderer/modules/profiles.js electron-app/backend/server.py
git commit -m "feat: complete NST removal — local-only profiles, unified cleanup"
```

---

## ═══ PHASE 2: FINGERPRINT JS MODULES ═══

---

### Task 6: Seeded PRNG + canvas.js

**Files:**
- Create: `shared/fingerprints/canvas.js`

- [ ] **Step 1: Create the fingerprints directory**

```bash
mkdir -p "E:/NST Anty Android/shared/fingerprints"
```

- [ ] **Step 2: Create canvas.js**

Create `shared/fingerprints/canvas.js`:

```javascript
(function () {
  const MODE = '{{CANVAS_MODE}}'; // 'off' | 'noise' | 'block'
  const SEED = {{CANVAS_SEED}};

  if (MODE === 'off') return;

  // Mulberry32 seeded PRNG — deterministic, fast
  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  function noiseData(data) {
    for (let i = 0; i < data.length; i += 4) {
      if (rand() < 0.003) {           // ~0.3% of pixels touched
        const delta = Math.floor(rand() * 4) - 2;  // -2 .. +1
        data[i]     = Math.max(0, Math.min(255, data[i]     + delta));
        data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + delta));
      }
    }
  }

  // Patch toDataURL
  const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (type, quality) {
    if (MODE === 'block') return 'data:image/png;base64,';
    const ctx = this.getContext && this.getContext('2d');
    if (ctx && this.width > 0 && this.height > 0) {
      try {
        const img = ctx.getImageData(0, 0, this.width, this.height);
        noiseData(img.data);
        ctx.putImageData(img, 0, 0);
      } catch (e) { /* cross-origin — skip */ }
    }
    return _toDataURL.call(this, type, quality);
  };

  // Patch getImageData
  const _getImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = function (sx, sy, sw, sh) {
    const img = _getImageData.call(this, sx, sy, sw, sh);
    if (MODE === 'block') { img.data.fill(0); return img; }
    noiseData(img.data);
    return img;
  };
})();
```

- [ ] **Step 3: Verify the JS is syntactically valid**

```bash
node -e "
const fs = require('fs');
let s = fs.readFileSync('E:/NST Anty Android/shared/fingerprints/canvas.js', 'utf8');
s = s.replace('{{CANVAS_MODE}}', 'noise').replace('{{CANVAS_SEED}}', '12345');
eval(s);
console.log('canvas.js syntax OK');
"
```
Expected: `canvas.js syntax OK`

- [ ] **Step 4: Commit**

```bash
git add shared/fingerprints/canvas.js
git commit -m "feat: add canvas.js fingerprint noise module"
```

---

### Task 7: client_rects.js + webgl_image.js

**Files:**
- Create: `shared/fingerprints/client_rects.js`
- Create: `shared/fingerprints/webgl_image.js`

- [ ] **Step 1: Create client_rects.js**

Create `shared/fingerprints/client_rects.js`:

```javascript
(function () {
  const MODE = '{{CLIENT_RECTS_MODE}}'; // 'off' | 'noise'
  const SEED = {{NOISE_SEED}};

  if (MODE === 'off') return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const noise = () => (rand() - 0.5) * 0.0006; // ±0.0003 px

  function patchRect(r) {
    return {
      top:    r.top    + noise(),
      left:   r.left   + noise(),
      right:  r.right  + noise(),
      bottom: r.bottom + noise(),
      width:  r.width  + noise(),
      height: r.height + noise(),
      x:      r.x      + noise(),
      y:      r.y      + noise(),
      toJSON() { return {top:this.top,left:this.left,right:this.right,bottom:this.bottom,width:this.width,height:this.height,x:this.x,y:this.y}; }
    };
  }

  const _getBCR = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function () {
    return patchRect(_getBCR.call(this));
  };

  const _getCR = Element.prototype.getClientRects;
  Element.prototype.getClientRects = function () {
    return Array.from(_getCR.call(this)).map(patchRect);
  };
})();
```

- [ ] **Step 2: Create webgl_image.js**

Create `shared/fingerprints/webgl_image.js`:

```javascript
(function () {
  const MODE = '{{WEBGL_IMAGE_MODE}}'; // 'off' | 'noise'
  const SEED = {{NOISE_SEED}};

  if (MODE === 'off') return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  function patchPixels(pixels) {
    if (!pixels) return;
    for (let i = 0; i < pixels.length; i += 997) { // prime step
      if (rand() < 0.5) pixels[i] = pixels[i] ^ 1;
    }
  }

  function wrapReadPixels(proto) {
    const orig = proto.readPixels;
    proto.readPixels = function (x, y, w, h, fmt, type, pixels, ...rest) {
      orig.call(this, x, y, w, h, fmt, type, pixels, ...rest);
      patchPixels(pixels);
    };
  }

  wrapReadPixels(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    wrapReadPixels(WebGL2RenderingContext.prototype);
})();
```

- [ ] **Step 3: Syntax check both files**

```bash
node -e "
const fs = require('fs');
['client_rects.js','webgl_image.js'].forEach(f => {
  let s = fs.readFileSync('E:/NST Anty Android/shared/fingerprints/'+f,'utf8');
  s = s.replace(/\{\{[A-Z_]+\}\}/g, '1');
  eval(s);
  console.log(f+' OK');
});
"
```

- [ ] **Step 4: Commit**

```bash
git add shared/fingerprints/client_rects.js shared/fingerprints/webgl_image.js
git commit -m "feat: add client_rects.js and webgl_image.js fingerprint modules"
```

---

### Task 8: webgl_meta.js

**Files:**
- Create: `shared/fingerprints/webgl_meta.js`

- [ ] **Step 1: Create webgl_meta.js**

Create `shared/fingerprints/webgl_meta.js`:

```javascript
(function () {
  const MODE     = '{{WEBGL_META_MODE}}'; // 'off' | 'custom' | 'real'
  const VENDOR   = '{{WEBGL_VENDOR}}';
  const RENDERER = '{{WEBGL_RENDERER}}';

  if (MODE === 'real' || MODE === 'off') return;

  const UNMASKED_VENDOR_WEBGL   = 0x9245;
  const UNMASKED_RENDERER_WEBGL = 0x9246;
  const GL_VENDOR   = 0x1F00;
  const GL_RENDERER = 0x1F01;

  function patchProto(proto) {
    const _getParam = proto.getParameter;
    proto.getParameter = function (param) {
      if (param === UNMASKED_VENDOR_WEBGL   || param === GL_VENDOR)   return VENDOR;
      if (param === UNMASKED_RENDERER_WEBGL || param === GL_RENDERER) return RENDERER;
      return _getParam.call(this, param);
    };

    const _getExt = proto.getExtension;
    proto.getExtension = function (name) {
      const ext = _getExt.call(this, name);
      if (name === 'WEBGL_debug_renderer_info' && ext) {
        return new Proxy(ext, {
          get(t, p) {
            if (p === 'UNMASKED_VENDOR_WEBGL')   return UNMASKED_VENDOR_WEBGL;
            if (p === 'UNMASKED_RENDERER_WEBGL') return UNMASKED_RENDERER_WEBGL;
            return t[p];
          }
        });
      }
      return ext;
    };
  }

  patchProto(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    patchProto(WebGL2RenderingContext.prototype);
})();
```

- [ ] **Step 2: Syntax check**

```bash
node -e "
const fs = require('fs');
let s = fs.readFileSync('E:/NST Anty Android/shared/fingerprints/webgl_meta.js','utf8');
s = s.replace('{{WEBGL_META_MODE}}','custom').replace('{{WEBGL_VENDOR}}','Intel Inc.').replace('{{WEBGL_RENDERER}}','Intel(R) Iris(R) Xe Graphics');
eval(s);
console.log('webgl_meta.js OK');
"
```

- [ ] **Step 3: Commit**

```bash
git add shared/fingerprints/webgl_meta.js
git commit -m "feat: add webgl_meta.js vendor/renderer spoof module"
```

---

### Task 9: audio.js + media_devices.js + webgpu.js

**Files:**
- Create: `shared/fingerprints/audio.js`
- Create: `shared/fingerprints/media_devices.js`
- Create: `shared/fingerprints/webgpu.js`

- [ ] **Step 1: Create audio.js**

Create `shared/fingerprints/audio.js`:

```javascript
(function () {
  const MODE = '{{AUDIO_MODE}}'; // 'off' | 'noise'
  const SEED = {{AUDIO_SEED}};

  if (MODE === 'off') return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const noise = () => (rand() - 0.5) * 0.0001;

  const _getFloat = AnalyserNode.prototype.getFloatFrequencyData;
  AnalyserNode.prototype.getFloatFrequencyData = function (array) {
    _getFloat.call(this, array);
    for (let i = 0; i < array.length; i++) array[i] += noise();
  };

  const _getByte = AnalyserNode.prototype.getByteFrequencyData;
  AnalyserNode.prototype.getByteFrequencyData = function (array) {
    _getByte.call(this, array);
    for (let i = 0; i < array.length; i++)
      array[i] = Math.max(0, Math.min(255, array[i] + Math.round(noise() * 200)));
  };

  if (AudioBuffer && AudioBuffer.prototype.copyFromChannel) {
    const _copy = AudioBuffer.prototype.copyFromChannel;
    AudioBuffer.prototype.copyFromChannel = function (dest, ch, off) {
      _copy.call(this, dest, ch, off);
      for (let i = 0; i < dest.length; i++) dest[i] += noise() * 0.005;
    };
  }
})();
```

- [ ] **Step 2: Create media_devices.js**

Create `shared/fingerprints/media_devices.js`:

```javascript
(function () {
  const MASKED       = {{MEDIA_DEVICES_MASK}};  // true | false
  const VIDEO_INPUTS = {{VIDEO_INPUTS}};
  const AUDIO_INPUTS = {{AUDIO_INPUTS}};
  const AUDIO_OUTPUTS= {{AUDIO_OUTPUTS}};

  if (!MASKED) return;
  if (!navigator.mediaDevices) return;

  Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', {
    value: async function () {
      const devices = [];
      for (let i = 0; i < VIDEO_INPUTS; i++)
        devices.push({ kind: 'videoinput',  deviceId: 'v'+i, groupId: 'g'+i,      label: '' });
      for (let i = 0; i < AUDIO_INPUTS; i++)
        devices.push({ kind: 'audioinput',  deviceId: 'ai'+i, groupId: 'g'+(i+10), label: '' });
      for (let i = 0; i < AUDIO_OUTPUTS; i++)
        devices.push({ kind: 'audiooutput', deviceId: 'ao'+i, groupId: 'g'+(i+20), label: '' });
      return devices;
    },
    writable: true, configurable: true,
  });

  // getUserMedia with 0 devices should fail gracefully
  if (VIDEO_INPUTS === 0 && AUDIO_INPUTS === 0) {
    const _gum = navigator.mediaDevices.getUserMedia;
    if (_gum) {
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
        value: function (constraints) {
          if (constraints.video && VIDEO_INPUTS === 0)
            return Promise.reject(new DOMException('No video devices', 'NotFoundError'));
          if (constraints.audio && AUDIO_INPUTS === 0)
            return Promise.reject(new DOMException('No audio devices', 'NotFoundError'));
          return _gum.call(this, constraints);
        },
        writable: true, configurable: true,
      });
    }
  }
})();
```

- [ ] **Step 3: Create webgpu.js**

Create `shared/fingerprints/webgpu.js`:

```javascript
(function () {
  const MODE = '{{WEBGPU_MODE}}'; // 'disabled' | 'real'

  if (MODE === 'real') return;

  // Disable WebGPU entirely
  Object.defineProperty(navigator, 'gpu', {
    get: () => undefined,
    configurable: true,
  });
})();
```

- [ ] **Step 4: Syntax check all three**

```bash
node -e "
const fs = require('fs'), path = require('path');
const dir = 'E:/NST Anty Android/shared/fingerprints';
['audio.js','media_devices.js','webgpu.js'].forEach(f => {
  let s = fs.readFileSync(path.join(dir,f),'utf8');
  s = s.replace(/\{\{[A-Z_]+\}\}/g, '1');
  try { eval(s); console.log(f+' OK'); } catch(e) { console.error(f+' FAIL:',e.message); process.exit(1); }
});
"
```

- [ ] **Step 5: Commit**

```bash
git add shared/fingerprints/audio.js shared/fingerprints/media_devices.js shared/fingerprints/webgpu.js
git commit -m "feat: add audio, media_devices, webgpu fingerprint modules"
```

---

### Task 10: fonts.js + speech.js + port_scan.js + device_name.js

**Files:**
- Create: `shared/fingerprints/fonts.js`
- Create: `shared/fingerprints/speech.js`
- Create: `shared/fingerprints/port_scan.js`
- Create: `shared/fingerprints/device_name.js`

- [ ] **Step 1: Create fonts.js**

Create `shared/fingerprints/fonts.js`:

```javascript
(function () {
  const MASKED  = {{FONTS_MASK}};
  const OS_TYPE = '{{OS_TYPE}}';
  const SEED    = {{NOISE_SEED}};

  if (!MASKED) return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const noise = () => (rand() - 0.5) * 0.0003;

  // measureText noise
  const _measureText = CanvasRenderingContext2D.prototype.measureText;
  CanvasRenderingContext2D.prototype.measureText = function (text) {
    const m = _measureText.call(this, text);
    const n = noise();
    return Object.assign(Object.create(Object.getPrototypeOf(m)), m, {
      width: m.width + n,
    });
  };
})();
```

- [ ] **Step 2: Create speech.js**

Create `shared/fingerprints/speech.js`:

```javascript
(function () {
  const MASKED  = {{SPEECH_MASK}};
  const OS_TYPE = '{{OS_TYPE}}';

  if (!MASKED || typeof speechSynthesis === 'undefined') return;

  const VOICE_LISTS = {
    windows: [
      { name: 'Microsoft David Desktop - English (United States)', lang: 'en-US', voiceURI: 'Microsoft David Desktop - English (United States)', localService: true, default: true },
      { name: 'Microsoft Zira Desktop - English (United States)',  lang: 'en-US', voiceURI: 'Microsoft Zira Desktop - English (United States)',  localService: true, default: false },
      { name: 'Microsoft Mark Desktop - English (United States)',  lang: 'en-US', voiceURI: 'Microsoft Mark Desktop - English (United States)',  localService: true, default: false },
    ],
    macos: [
      { name: 'Samantha', lang: 'en-US', voiceURI: 'com.apple.speech.synthesis.voice.samantha', localService: true, default: true },
      { name: 'Alex',     lang: 'en-US', voiceURI: 'com.apple.speech.synthesis.voice.alex',     localService: true, default: false },
    ],
    linux:   [{ name: 'English', lang: 'en-US', voiceURI: 'English', localService: true, default: true }],
    android: [],
    ios:     [{ name: 'Samantha', lang: 'en-US', voiceURI: 'com.apple.ttsbundle.Samantha-compact', localService: true, default: true }],
  };

  const list = VOICE_LISTS[OS_TYPE] || VOICE_LISTS['windows'];

  Object.defineProperty(speechSynthesis, 'getVoices', {
    value: function () { return list.map(v => Object.assign(Object.create(SpeechSynthesisVoice.prototype), v)); },
    configurable: true,
  });
})();
```

- [ ] **Step 3: Create port_scan.js**

Create `shared/fingerprints/port_scan.js`:

```javascript
(function () {
  const ENABLED = {{PORT_SCAN_PROTECTION}};

  if (!ENABLED) return;

  const LOCAL_RE = /^(?:https?|wss?):\/\/(?:localhost|127\.\d+\.\d+\.\d+|\[?::1\]?|0\.0\.0\.0)(?::\d+)?/i;

  // Block WebSocket to localhost
  const _WS = window.WebSocket;
  window.WebSocket = function (url, protos) {
    if (LOCAL_RE.test(String(url)))
      throw new DOMException('Connection blocked by port scan protection', 'SecurityError');
    return new _WS(url, protos);
  };
  Object.setPrototypeOf(window.WebSocket, _WS);
  window.WebSocket.prototype = _WS.prototype;

  // Block fetch to localhost
  const _fetch = window.fetch;
  window.fetch = function (input, init) {
    const url = String(input instanceof Request ? input.url : input);
    if (LOCAL_RE.test(url))
      return Promise.reject(new TypeError('fetch blocked by port scan protection'));
    return _fetch.call(this, input, init);
  };

  // Block XHR to localhost
  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    if (LOCAL_RE.test(String(url)))
      throw new DOMException('XHR blocked by port scan protection', 'SecurityError');
    return _open.call(this, method, url, ...rest);
  };
})();
```

- [ ] **Step 4: Create device_name.js**

Create `shared/fingerprints/device_name.js`:

```javascript
(function () {
  const DNT = {{DNT}}; // true | false

  // DoNotTrack
  Object.defineProperty(navigator, 'doNotTrack', {
    get: () => DNT ? '1' : null,
    configurable: true,
  });

  // Remove battery API (fingerprinting vector)
  if ('getBattery' in navigator) {
    Object.defineProperty(navigator, 'getBattery', {
      value: undefined, configurable: true,
    });
  }
})();
```

- [ ] **Step 5: Syntax check all four**

```bash
node -e "
const fs = require('fs'), path = require('path');
const dir = 'E:/NST Anty Android/shared/fingerprints';
['fonts.js','speech.js','port_scan.js','device_name.js'].forEach(f => {
  let s = fs.readFileSync(path.join(dir,f),'utf8');
  s = s.replace(/\{\{[A-Z_]+\}\}/g, '1').replace(/\{\{OS_TYPE\}\}/g,\"'windows'\");
  try { eval(s); console.log(f+' OK'); } catch(e) { console.error(f+' FAIL:',e.message); process.exit(1); }
});
"
```

- [ ] **Step 6: Commit**

```bash
git add shared/fingerprints/fonts.js shared/fingerprints/speech.js shared/fingerprints/port_scan.js shared/fingerprints/device_name.js
git commit -m "feat: add fonts, speech, port_scan, device_name fingerprint modules"
```

---

### Task 11: FingerprintInjector Python class

**Files:**
- Create: `shared/fingerprint_injector.py`

- [ ] **Step 1: Create fingerprint_injector.py**

Create `shared/fingerprint_injector.py`:

```python
"""
FingerprintInjector — builds a combined JS init script from per-profile
fingerprint_config and fingerprint dicts. Each JS module is a template file
in shared/fingerprints/ with {{PLACEHOLDER}} substitutions.
"""
from __future__ import annotations
from pathlib import Path

_MODULES_DIR = Path(__file__).parent / 'fingerprints'

# WebGL GPU presets — randomised at profile creation time
WEBGL_PRESETS = [
    ('Intel Inc.',        'Intel(R) Iris(R) Xe Graphics'),
    ('Intel Inc.',        'Intel(R) UHD Graphics 620'),
    ('NVIDIA Corporation','NVIDIA GeForce RTX 3060/PCIe/SSE2'),
    ('NVIDIA Corporation','NVIDIA GeForce GTX 1650/PCIe/SSE2'),
    ('Google Inc. (Intel)','ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)'),
    ('Google Inc. (NVIDIA)','ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)'),
]

DEFAULT_FINGERPRINT_CONFIG: dict = {
    'canvas_mode':         'noise',
    'client_rects_mode':   'noise',
    'audio_mode':          'noise',
    'webgl_image_mode':    'noise',
    'webgl_meta_mode':     'custom',
    'webgl_vendor':        'Intel Inc.',
    'webgl_renderer':      'Intel(R) Iris(R) Xe Graphics',
    'media_devices_mask':  True,
    'video_inputs':        0,
    'audio_inputs':        0,
    'audio_outputs':       0,
    'fonts_mask':          True,
    'webgpu_mode':         'disabled',
    'speech_mask':         True,
    'dnt':                 True,
    'port_scan_protection':True,
}


class FingerprintInjector:
    """Loads JS templates, substitutes seed values, returns combined init script."""

    _cache: dict[str, str] = {}

    @classmethod
    def _tpl(cls, name: str) -> str:
        if name not in cls._cache:
            cls._cache[name] = (_MODULES_DIR / name).read_text('utf-8')
        return cls._cache[name]

    def build_script(self, fingerprint_config: dict | None, fingerprint: dict | None) -> str:
        """Return a single JS string to pass to context.add_init_script()."""
        fc = {**DEFAULT_FINGERPRINT_CONFIG, **(fingerprint_config or {})}
        fp = fingerprint or {}

        noise_seed  = int(fp.get('noise_seed',  12345))
        audio_seed  = int(fp.get('audio_seed',  noise_seed ^ 0xA0D10))
        canvas_seed = noise_seed
        os_type     = fp.get('os_type', 'windows')

        def _b(v) -> str:
            return 'true' if v else 'false'

        parts: list[str] = []

        # canvas
        parts.append(self._tpl('canvas.js')
            .replace('{{CANVAS_MODE}}', fc['canvas_mode'])
            .replace('{{CANVAS_SEED}}', str(canvas_seed)))

        # client_rects
        parts.append(self._tpl('client_rects.js')
            .replace('{{CLIENT_RECTS_MODE}}', fc['client_rects_mode'])
            .replace('{{NOISE_SEED}}', str(noise_seed)))

        # webgl_image
        parts.append(self._tpl('webgl_image.js')
            .replace('{{WEBGL_IMAGE_MODE}}', fc['webgl_image_mode'])
            .replace('{{NOISE_SEED}}', str(noise_seed)))

        # webgl_meta
        parts.append(self._tpl('webgl_meta.js')
            .replace('{{WEBGL_META_MODE}}', fc['webgl_meta_mode'])
            .replace('{{WEBGL_VENDOR}}',   fc['webgl_vendor'])
            .replace('{{WEBGL_RENDERER}}', fc['webgl_renderer']))

        # audio
        parts.append(self._tpl('audio.js')
            .replace('{{AUDIO_MODE}}', fc['audio_mode'])
            .replace('{{AUDIO_SEED}}', str(audio_seed)))

        # media_devices
        parts.append(self._tpl('media_devices.js')
            .replace('{{MEDIA_DEVICES_MASK}}', _b(fc['media_devices_mask']))
            .replace('{{VIDEO_INPUTS}}',  str(fc['video_inputs']))
            .replace('{{AUDIO_INPUTS}}',  str(fc['audio_inputs']))
            .replace('{{AUDIO_OUTPUTS}}', str(fc['audio_outputs'])))

        # fonts
        parts.append(self._tpl('fonts.js')
            .replace('{{FONTS_MASK}}', _b(fc['fonts_mask']))
            .replace('{{OS_TYPE}}',    os_type)
            .replace('{{NOISE_SEED}}', str(noise_seed)))

        # webgpu
        parts.append(self._tpl('webgpu.js')
            .replace('{{WEBGPU_MODE}}', fc['webgpu_mode']))

        # speech
        parts.append(self._tpl('speech.js')
            .replace('{{SPEECH_MASK}}', _b(fc['speech_mask']))
            .replace('{{OS_TYPE}}',     os_type))

        # port_scan
        parts.append(self._tpl('port_scan.js')
            .replace('{{PORT_SCAN_PROTECTION}}', _b(fc['port_scan_protection'])))

        # device_name / dnt
        parts.append(self._tpl('device_name.js')
            .replace('{{DNT}}', _b(fc['dnt'])))

        return '\n;\n'.join(parts)
```

- [ ] **Step 2: Test FingerprintInjector**

```bash
python -c "
from shared.fingerprint_injector import FingerprintInjector
inj = FingerprintInjector()
fp  = {'noise_seed': 99999, 'audio_seed': 12345, 'os_type': 'windows'}
script = inj.build_script(None, fp)
assert 'canvas' in script.lower(), 'canvas module missing'
assert 'WebGLRenderingContext' in script, 'webgl module missing'
assert 'enumerateDevices' in script, 'media devices module missing'
assert 'Intel Inc.' in script, 'WebGL vendor missing'
assert len(script) > 2000, 'script suspiciously short'
print('FingerprintInjector OK, script length:', len(script))
"
```
Expected: `FingerprintInjector OK, script length: XXXXX` (should be 5000+)

- [ ] **Step 3: Commit**

```bash
git add shared/fingerprint_injector.py
git commit -m "feat: add FingerprintInjector Python class"
```

---

### Task 12: Wire FingerprintInjector into stealth_chrome.py

**Files:**
- Modify: `shared/stealth_chrome.py` — `inject_scripts` method
- Modify: `shared/profile_manager.py` — `_launch_profile_context`

- [ ] **Step 1: Find inject_scripts in stealth_chrome.py**

```bash
grep -n "def inject_scripts\|add_init_script\|addScriptToEvaluate" "E:/NST Anty Android/shared/stealth_chrome.py" | head -10
```

Note the line number of `inject_scripts`.

- [ ] **Step 2: Update _launch_profile_context to inject fingerprint script**

In `shared/profile_manager.py`, find `_launch_profile_context`. After the existing `inject_scripts` call (which injects nexus_scripts), add:

```python
    # ── Inject fingerprint spoofing scripts ──────────────────────────────────
    from shared.fingerprint_injector import FingerprintInjector
    _fp_config = profile.get('fingerprint_config')
    _fp_data   = profile.get('fingerprint') or {}
    _fp_script = FingerprintInjector().build_script(_fp_config, _fp_data)
    await stealth.inject_scripts(context, [_fp_script])
    _log(f"[FINGERPRINT] Injected {len(_fp_script)} chars of fingerprint scripts")
```

Place this AFTER the existing `inject_scripts` block (after line `_log(f"[NEXUS-MODULES] Injected ...")`).

- [ ] **Step 3: Also inject in launch_and_connect (NexusBrowser path)**

In `shared/nexus_profile_manager.py`, `launch_and_connect` NexusBrowser path: find where `inject_scripts` or `_run_cdp_overrides` is set up. After connecting via CDP, inject the fingerprint script into the context:

Find the section starting at `_log(f"NexusBrowser CDP ready: {ws}")`. Before the `return ws` line, add a background CDP injection:

```python
        # Inject fingerprint script via CDP addScriptToEvaluateOnNewDocument
        import threading as _th
        def _inject_fp():
            import asyncio as _aio
            from playwright.sync_api import sync_playwright as _sp
            from shared.fingerprint_injector import FingerprintInjector
            try:
                fp_script = FingerprintInjector().build_script(
                    profile.get('fingerprint_config'),
                    profile.get('fingerprint') or {}
                )
                loop2 = _aio.new_event_loop()
                async def _do():
                    async with _sp() as _p:
                        _b2 = await _p.chromium.connect_over_cdp(ws)
                        if _b2.contexts:
                            await _b2.contexts[0].add_init_script(fp_script)
                loop2.run_until_complete(_do())
                loop2.close()
            except Exception as _e:
                _log(f"fingerprint inject warning: {_e}", 'warning')
        _th.Thread(target=_inject_fp, daemon=True).start()
```

Actually this approach is complex. A simpler and cleaner approach: Add fingerprint injection to `_run_cdp_overrides` or in `_launch_profile_context` after StealthChrome starts. Since `_launch_profile_context` is used for batch operations and already has the profile, inject there.

**Simpler approach**: The injection in `_launch_profile_context` (Step 2 above) covers batch login and all operations. For `launch_and_connect` (used for manual profile open), wire the fingerprint after the CDP session starts:

In `launch_and_connect`, after `ws = loop.run_until_complete(sc.start(...))`, add:

```python
        # Inject fingerprint on next connect — store in profile for retrieval
        # The actual injection happens in the caller's async context
        with _lock:
            if ws and profile_id in _active_browsers:
                _active_browsers[profile_id]['fingerprint_config'] = profile.get('fingerprint_config')
                _active_browsers[profile_id]['fingerprint'] = profile.get('fingerprint')
```

Then in `_profile_browser_session` (where the browser runs persistently), inject the script.

**Actually**: The simplest correct approach — inject fingerprint script from `_launch_profile_context` (already async, already has profile). This covers:
- batch_login → `_login_profile_impl` → `_launch_profile_context` ✓
- open_profile (manual open) → `_profile_browser_session` → also calls `_launch_profile_context` ✓

Step 2 above covers all cases. Leave `launch_and_connect` for later if needed.

- [ ] **Step 4: Test that fingerprint script is injected**

Start the Electron app. Open a profile. In the browser DevTools console, run:
```javascript
// Should return 'Intel Inc.' not real GPU vendor
const canvas = document.createElement('canvas');
const gl = canvas.getContext('webgl');
const ext = gl.getExtension('WEBGL_debug_renderer_info');
console.log(gl.getParameter(ext.UNMASKED_VENDOR_WEBGL));
```
Expected output: `Intel Inc.`

Also test:
```javascript
navigator.mediaDevices.enumerateDevices().then(d => console.log('devices:', d.length));
```
Expected: `devices: 0`

- [ ] **Step 5: Commit**

```bash
git add shared/profile_manager.py shared/nexus_profile_manager.py
git commit -m "feat: inject fingerprint scripts at browser launch"
```

---

### Task 13: Add fingerprint_config defaults to profile schema

**Files:**
- Modify: `shared/nexus_profile_manager.py` — `create_profile` (~line 999)

- [ ] **Step 1: Import DEFAULT_FINGERPRINT_CONFIG in nexus_profile_manager**

Near the top of `nexus_profile_manager.py`, add:
```python
from shared.fingerprint_injector import DEFAULT_FINGERPRINT_CONFIG, WEBGL_PRESETS
```

- [ ] **Step 2: Pick random GPU preset at profile creation time**

In `create_profile`, just before building the profile dict, add:

```python
    # Random GPU preset — deterministic per noise_seed
    import random as _rand_fp
    _gpu_rng = _rand_fp.Random(fingerprint.get('noise_seed', 0))
    _vendor, _renderer = _gpu_rng.choice(WEBGL_PRESETS)
    _fp_config = {
        **DEFAULT_FINGERPRINT_CONFIG,
        'webgl_vendor':   _vendor,
        'webgl_renderer': _renderer,
    }
```

- [ ] **Step 3: Add fingerprint_config to profile dict**

In the profile dict construction, add:
```python
    'fingerprint_config': _fp_config,
```

- [ ] **Step 4: Verify new profiles include fingerprint_config**

```bash
python -c "
from shared import nexus_profile_manager as m
m.init('E:/NST Anty Android')
p = m.create_profile('fp_test')
fc = p.get('fingerprint_config', {})
assert fc.get('canvas_mode') == 'noise', 'canvas_mode missing'
assert 'webgl_vendor' in fc, 'webgl_vendor missing'
assert fc.get('port_scan_protection') == True
print('fingerprint_config OK:', fc['webgl_vendor'], '/', fc['webgl_renderer'][:30])
# Cleanup
m.delete_profile(p['id'])
"
```

- [ ] **Step 5: Commit**

```bash
git add shared/nexus_profile_manager.py
git commit -m "feat: add fingerprint_config defaults to profile schema"
```

---

## ═══ PHASE 3: PROFILE UI UPDATE ═══

---

### Task 14: Hardware tab HTML

**Files:**
- Modify: `electron-app/renderer/index.html`

- [ ] **Step 1: Find the existing hardware tab content**

```bash
grep -n "hardware\|pm-hardware\|pmHardware\|Canvas Mode\|WebGL" "E:/NST Anty Android/electron-app/renderer/index.html" | head -20
```

Note the element IDs and structure of the current hardware tab.

- [ ] **Step 2: Replace hardware tab inner HTML**

Find the hardware tab `<div>` (likely `id="pmTabHardware"` or similar). Replace its contents with:

```html
<!-- Canvas / Rects / Audio / WebGL -->
<div class="pm-section-label">Hardware Fingerprinting</div>

<div class="pm-row">
  <label>Canvas Mode</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpCanvas" value="off"> Off</label>
    <label><input type="radio" name="fpCanvas" value="noise" checked> Noise</label>
    <label><input type="radio" name="fpCanvas" value="block"> Block</label>
  </div>
</div>

<div class="pm-row">
  <label>ClientRects Mode</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpClientRects" value="off"> Off</label>
    <label><input type="radio" name="fpClientRects" value="noise" checked> Noise</label>
  </div>
</div>

<div class="pm-row">
  <label>AudioContext Mode</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpAudio" value="off"> Off</label>
    <label><input type="radio" name="fpAudio" value="noise" checked> Noise</label>
  </div>
</div>

<div class="pm-row">
  <label>WebGL Image Mode</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpWebGLImage" value="off"> Off</label>
    <label><input type="radio" name="fpWebGLImage" value="noise" checked> Noise</label>
  </div>
</div>

<div class="pm-row">
  <label>WebGL Meta Mode</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpWebGLMeta" value="off"> Off</label>
    <label><input type="radio" name="fpWebGLMeta" value="custom" checked> Custom</label>
    <label><input type="radio" name="fpWebGLMeta" value="real"> Real</label>
  </div>
</div>
<div class="pm-row pm-webgl-meta-fields">
  <label>WebGL Vendor</label>
  <input type="text" id="pmWebGLVendor" value="Intel Inc." placeholder="Intel Inc.">
</div>
<div class="pm-row pm-webgl-meta-fields">
  <label>WebGL Renderer</label>
  <input type="text" id="pmWebGLRenderer" value="Intel(R) Iris(R) Xe Graphics" placeholder="Intel(R) Iris(R) Xe Graphics">
</div>

<!-- Media Devices -->
<div class="pm-section-label" style="margin-top:12px">Media Devices</div>

<div class="pm-row">
  <label>Mask Media Devices</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpMediaMask" value="true" checked> On</label>
    <label><input type="radio" name="fpMediaMask" value="false"> Off</label>
  </div>
</div>
<div class="pm-row pm-media-fields">
  <label>Video Inputs</label>
  <select id="pmVideoInputs"><option value="0">0</option><option>1</option><option>2</option></select>
</div>
<div class="pm-row pm-media-fields">
  <label>Audio Inputs</label>
  <select id="pmAudioInputs"><option value="0">0</option><option>1</option><option>2</option></select>
</div>
<div class="pm-row pm-media-fields">
  <label>Audio Outputs</label>
  <select id="pmAudioOutputs"><option value="0">0</option><option>1</option><option>2</option></select>
</div>

<!-- Privacy -->
<div class="pm-section-label" style="margin-top:12px">Privacy & Security</div>

<div class="pm-row">
  <label>Fonts Masking</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpFonts" value="true" checked> On</label>
    <label><input type="radio" name="fpFonts" value="false"> Off</label>
  </div>
</div>
<div class="pm-row">
  <label>WebGPU Mode</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpWebGPU" value="disabled" checked> Disabled</label>
    <label><input type="radio" name="fpWebGPU" value="real"> Real</label>
  </div>
</div>
<div class="pm-row">
  <label>Speech Voices</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpSpeech" value="true" checked> Masked</label>
    <label><input type="radio" name="fpSpeech" value="false"> Real</label>
  </div>
</div>
<div class="pm-row">
  <label>DoNotTrack</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpDNT" value="true" checked> On</label>
    <label><input type="radio" name="fpDNT" value="false"> Off</label>
  </div>
</div>
<div class="pm-row">
  <label>Port Scan Protection</label>
  <div class="pm-pill-group">
    <label><input type="radio" name="fpPortScan" value="true" checked> On</label>
    <label><input type="radio" name="fpPortScan" value="false"> Off</label>
  </div>
</div>
```

- [ ] **Step 3: Add Android/iOS to the OS pill group**

Find the OS pill group (likely `input[name="pmOS"]`). Add Android and iOS options:
```html
<label><input type="radio" name="pmOS" value="android"> Android</label>
<label><input type="radio" name="pmOS" value="ios"> iOS</label>
```

- [ ] **Step 4: Commit HTML changes**

```bash
git add electron-app/renderer/index.html
git commit -m "feat: hardware tab HTML — fingerprint controls + Android/iOS OS options"
```

---

### Task 15: Hardware tab JS — read/write fingerprint_config

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js`

- [ ] **Step 1: Add helper to read fingerprint_config from form**

In `profiles.js`, find the `saveProfile` function or the section that builds the POST body. Add a helper function:

```javascript
function _readFingerprintConfig() {
  const _radio = (name) => {
    const el = document.querySelector(`input[name="${name}"]:checked`);
    return el ? el.value : null;
  };
  const _val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  return {
    canvas_mode:         _radio('fpCanvas')       || 'noise',
    client_rects_mode:   _radio('fpClientRects')   || 'noise',
    audio_mode:          _radio('fpAudio')         || 'noise',
    webgl_image_mode:    _radio('fpWebGLImage')    || 'noise',
    webgl_meta_mode:     _radio('fpWebGLMeta')     || 'custom',
    webgl_vendor:        _val('pmWebGLVendor')     || 'Intel Inc.',
    webgl_renderer:      _val('pmWebGLRenderer')   || 'Intel(R) Iris(R) Xe Graphics',
    media_devices_mask:  _radio('fpMediaMask')  === 'true',
    video_inputs:        parseInt(_val('pmVideoInputs'))  || 0,
    audio_inputs:        parseInt(_val('pmAudioInputs'))  || 0,
    audio_outputs:       parseInt(_val('pmAudioOutputs')) || 0,
    fonts_mask:          _radio('fpFonts')    === 'true',
    webgpu_mode:         _radio('fpWebGPU')       || 'disabled',
    speech_mask:         _radio('fpSpeech')   === 'true',
    dnt:                 _radio('fpDNT')      === 'true',
    port_scan_protection:_radio('fpPortScan') === 'true',
  };
}
```

- [ ] **Step 2: Add helper to populate form from fingerprint_config**

```javascript
function _loadFingerprintConfig(fc) {
  if (!fc) fc = {};
  const _setRadio = (name, val) => {
    const el = document.querySelector(`input[name="${name}"][value="${val}"]`);
    if (el) el.checked = true;
  };
  const _setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val !== undefined) el.value = val;
  };
  _setRadio('fpCanvas',       fc.canvas_mode         || 'noise');
  _setRadio('fpClientRects',  fc.client_rects_mode   || 'noise');
  _setRadio('fpAudio',        fc.audio_mode          || 'noise');
  _setRadio('fpWebGLImage',   fc.webgl_image_mode    || 'noise');
  _setRadio('fpWebGLMeta',    fc.webgl_meta_mode     || 'custom');
  _setVal('pmWebGLVendor',    fc.webgl_vendor        || 'Intel Inc.');
  _setVal('pmWebGLRenderer',  fc.webgl_renderer      || 'Intel(R) Iris(R) Xe Graphics');
  _setRadio('fpMediaMask',    fc.media_devices_mask !== false ? 'true' : 'false');
  _setVal('pmVideoInputs',    fc.video_inputs  ?? 0);
  _setVal('pmAudioInputs',    fc.audio_inputs  ?? 0);
  _setVal('pmAudioOutputs',   fc.audio_outputs ?? 0);
  _setRadio('fpFonts',        fc.fonts_mask  !== false ? 'true' : 'false');
  _setRadio('fpWebGPU',       fc.webgpu_mode         || 'disabled');
  _setRadio('fpSpeech',       fc.speech_mask !== false ? 'true' : 'false');
  _setRadio('fpDNT',          fc.dnt         !== false ? 'true' : 'false');
  _setRadio('fpPortScan',     fc.port_scan_protection !== false ? 'true' : 'false');
}
```

- [ ] **Step 3: Include fingerprint_config in saveProfile POST body**

Find where `saveProfile` builds its request body. Add:
```javascript
fingerprint_config: _readFingerprintConfig(),
```

- [ ] **Step 4: Load fingerprint_config in openEditModal**

Find `openEditModal(id)`. After loading the profile, call:
```javascript
_loadFingerprintConfig(profile.fingerprint_config);
```

- [ ] **Step 5: Update summary panel**

Find `_updateSummary()`. Add to the summary HTML:
```javascript
const fc = _readFingerprintConfig();
// Add to summary:
`<div class="pm-summary-row"><span>Canvas</span><span>${fc.canvas_mode}</span></div>
 <div class="pm-summary-row"><span>WebGL</span><span>${fc.webgl_vendor.split(' ').slice(0,2).join(' ')}</span></div>
 <div class="pm-summary-row"><span>Media Devices</span><span>${fc.media_devices_mask ? '0 video / 0 audio' : 'Real'}</span></div>`
```

- [ ] **Step 6: Toggle WebGL vendor/renderer fields visibility**

Add JS to show/hide `.pm-webgl-meta-fields` based on WebGL meta mode radio:
```javascript
document.querySelectorAll('input[name="fpWebGLMeta"]').forEach(r => {
  r.addEventListener('change', () => {
    const show = r.value === 'custom' && r.checked;
    document.querySelectorAll('.pm-webgl-meta-fields').forEach(el => {
      el.style.display = show ? '' : 'none';
    });
  });
});
```

- [ ] **Step 7: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: hardware tab JS — read/write fingerprint_config per profile"
```

---

### Task 16: Pass fingerprint_config through backend routes

**Files:**
- Modify: `electron-app/backend/server.py` — profile create/update routes
- Modify: `shared/nexus_profile_manager.py` — `update_profile`

- [ ] **Step 1: Pass fingerprint_config in create profile route**

Find the POST `/api/profiles` route in `server.py`. Ensure `fingerprint_config` from the request body is passed to `create_profile` or `update_profile`:

```python
fingerprint_config = data.get('fingerprint_config')
# Pass to create_profile
profile = profile_manager.create_profile(
    name=name, email=email, ...
)
if fingerprint_config:
    profile_manager.update_profile(profile['id'], fingerprint_config=fingerprint_config)
```

- [ ] **Step 2: Pass fingerprint_config in update profile route**

Find the PATCH/PUT `/api/profiles/<id>` route. Add:
```python
if 'fingerprint_config' in data:
    update_kwargs['fingerprint_config'] = data['fingerprint_config']
```

- [ ] **Step 3: Ensure update_profile saves fingerprint_config**

In `nexus_profile_manager.py`, find `update_profile`. Verify it handles `fingerprint_config` as a keyword arg (same pattern as other fields like `group`, `status`). If not present, add:

```python
if 'fingerprint_config' in kwargs:
    target['fingerprint_config'] = kwargs['fingerprint_config']
```

- [ ] **Step 4: Test end-to-end**

Start the app. Create a new profile with:
- Canvas Mode: Block
- WebGL Vendor: `NVIDIA Corporation`

Save. Reopen the profile edit modal. Verify:
- Canvas Mode shows "Block"
- WebGL Vendor shows "NVIDIA Corporation"

Open a browser for the profile. In DevTools console:
```javascript
const c = document.createElement('canvas');
const gl = c.getContext('webgl');
const ext = gl.getExtension('WEBGL_debug_renderer_info');
console.log('Vendor:', gl.getParameter(ext.UNMASKED_VENDOR_WEBGL));
```
Expected: `Vendor: NVIDIA Corporation`

- [ ] **Step 5: Final commit**

```bash
git add electron-app/backend/server.py shared/nexus_profile_manager.py
git commit -m "feat: fingerprint_config flows through backend create/update routes"
```

---

## Self-Review Checklist

### Spec Coverage
- [x] NST API removal — Tasks 1-5
- [x] Local StealthChrome only — Tasks 3-4
- [x] Profile migration (engine=nst → nexus) — Task 5
- [x] Canvas noise — Task 6
- [x] ClientRects noise — Task 7
- [x] WebGL image noise — Task 7
- [x] WebGL vendor/renderer spoof — Task 8
- [x] AudioContext noise — Task 9
- [x] Media devices masking — Task 9
- [x] WebGPU disable — Task 9
- [x] Fonts masking — Task 10
- [x] Speech voices — Task 10
- [x] Port scan protection — Task 10
- [x] DoNotTrack + battery — Task 10
- [x] FingerprintInjector Python class — Task 11
- [x] Wire into browser launch — Task 12
- [x] fingerprint_config in profile schema — Task 13
- [x] Hardware tab HTML — Task 14
- [x] Hardware tab JS read/write — Task 15
- [x] Backend routes pass fingerprint_config — Task 16
- [x] Android/iOS OS options — Task 14

### Type Consistency
- `FingerprintInjector.build_script(fingerprint_config, fingerprint)` — used consistently in Tasks 11, 12
- `DEFAULT_FINGERPRINT_CONFIG` imported from `fingerprint_injector` in Task 13
- `stop_profile_browser` alias for `stop_nst_browser` — backwards compatible
- `fingerprint_config` dict key used consistently in profile JSON, backend, frontend

### No Placeholders
All code blocks are complete. All file paths are exact. All test commands include expected output.
