"""
FingerprintInjector — builds a combined JS init script from per-profile
fingerprint_config and fingerprint dicts. Each JS module is a template file
in shared/fingerprints/ with {{PLACEHOLDER}} substitutions.
"""
from __future__ import annotations
from pathlib import Path

_MODULES_DIR = Path(__file__).parent / 'fingerprints'

WEBGL_PRESETS = [
    ('Intel Inc.',           'Intel(R) Iris(R) Xe Graphics'),
    ('Intel Inc.',           'Intel(R) UHD Graphics'),
    ('Google Inc. (NVIDIA)', 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)'),
    ('Google Inc. (AMD)',    'ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)'),
    ('Google Inc. (Intel)',  'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)'),
    ('Google Inc. (Intel)',  'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)'),
    ('Apple Inc.',           'Apple GPU'),
]

MOBILE_WEBGL_PRESETS = [
    ('Qualcomm', 'Adreno (TM) 740'),
    ('Qualcomm', 'Adreno (TM) 730'),
    ('ARM',      'Mali-G710 MC10'),
    ('ARM',      'Mali-G78 MP24'),
    ('Apple',    'Apple GPU'),
]

DEFAULT_FINGERPRINT_CONFIG: dict = {
    'canvas_mode':           'off',
    'client_rects_mode':     'off',
    'audio_mode':            'noise',
    'webgl_image_mode':      'noise',
    'webgl_meta_mode':       'custom',
    'webgl_vendor':          'Intel Inc.',
    'webgl_renderer':        'Intel(R) Iris(R) Xe Graphics',
    'media_devices_mask':    False,
    'video_inputs':          0,
    'audio_inputs':          0,
    'audio_outputs':         0,
    'fonts_mask':            True,
    'webgpu_mode':           'disabled',
    'speech_mask':           True,
    'dnt':                   True,
    'port_scan_protection':  True,
    # System hardware
    'screen_width':          1366,
    'screen_height':         768,
    'cpu_threads':           4,
    'ram_gb':                4,
    'locale':                'en-US',
    # Geolocation
    'geolocation_permission':'prompt',
    'geo_latitude':          None,
    'geo_longitude':         None,
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

        parts.append(self._tpl('canvas.js')
            .replace('{{CANVAS_MODE}}', fc['canvas_mode'])
            .replace('{{CANVAS_SEED}}', str(canvas_seed)))

        parts.append(self._tpl('client_rects.js')
            .replace('{{CLIENT_RECTS_MODE}}', fc['client_rects_mode'])
            .replace('{{NOISE_SEED}}', str(noise_seed)))

        parts.append(self._tpl('webgl_image.js')
            .replace('{{WEBGL_IMAGE_MODE}}', fc['webgl_image_mode'])
            .replace('{{NOISE_SEED}}', str(noise_seed)))

        parts.append(self._tpl('webgl_meta.js')
            .replace('{{WEBGL_META_MODE}}', fc['webgl_meta_mode'])
            .replace('{{WEBGL_VENDOR}}',   fc['webgl_vendor'])
            .replace('{{WEBGL_RENDERER}}', fc['webgl_renderer']))

        parts.append(self._tpl('audio.js')
            .replace('{{AUDIO_MODE}}', fc['audio_mode'])
            .replace('{{AUDIO_SEED}}', str(audio_seed)))

        parts.append(self._tpl('media_devices.js')
            .replace('{{MEDIA_DEVICES_MASK}}', _b(fc['media_devices_mask']))
            .replace('{{VIDEO_INPUTS}}',  str(fc['video_inputs']))
            .replace('{{AUDIO_INPUTS}}',  str(fc['audio_inputs']))
            .replace('{{AUDIO_OUTPUTS}}', str(fc['audio_outputs'])))

        parts.append(self._tpl('fonts.js')
            .replace('{{FONTS_MASK}}', _b(fc['fonts_mask']))
            .replace('{{OS_TYPE}}',    os_type)
            .replace('{{NOISE_SEED}}', str(noise_seed)))

        parts.append(self._tpl('webgpu.js')
            .replace('{{WEBGPU_MODE}}', fc['webgpu_mode']))

        parts.append(self._tpl('speech.js')
            .replace('{{SPEECH_MASK}}', _b(fc['speech_mask']))
            .replace('{{OS_TYPE}}',     os_type))

        parts.append(self._tpl('port_scan.js')
            .replace('{{PORT_SCAN_PROTECTION}}', _b(fc['port_scan_protection'])))

        parts.append(self._tpl('device_name.js')
            .replace('{{DNT}}', _b(fc['dnt'])))

        parts.append(self._tpl('hardware.js')
            .replace('{{SCREEN_WIDTH}}',  str(int(fc.get('screen_width',  1366) or 0)))
            .replace('{{SCREEN_HEIGHT}}', str(int(fc.get('screen_height', 768)  or 0)))
            .replace('{{CPU_THREADS}}',   str(int(fc.get('cpu_threads',   4)    or 0)))
            .replace('{{RAM_GB}}',        str(int(fc.get('ram_gb',        4)    or 0)))
            .replace('{{OS_TYPE}}',       os_type))

        # Navigator extras: connection API, maxTouchPoints, webdriver, chrome object
        parts.append(self._tpl('navigator_extra.js')
            .replace('{{OS_TYPE}}', os_type))

        return '\n;\n'.join(parts)
