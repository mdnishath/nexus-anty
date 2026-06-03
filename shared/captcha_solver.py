"""
shared/captcha_solver.py — CAPTCHA solving service integration.

Supports 2Captcha, Anti-Captcha, and CapSolver for reCAPTCHA v2/v3.

Public API
----------
CaptchaSolver(provider, api_key)
solve_recaptcha_v2(sitekey, page_url) -> str (token)
get_balance() -> float
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse

_LOG_PREFIX = '[CAPTCHA]'


class CaptchaSolver:
    """Unified CAPTCHA solver for reCAPTCHA v2/v3."""

    PROVIDERS = {
        '2captcha': {
            'create_url': 'https://2captcha.com/in.php',
            'result_url': 'https://2captcha.com/res.php',
            'balance_url': 'https://2captcha.com/res.php',
        },
        'anticaptcha': {
            'create_url': 'https://api.anti-captcha.com/createTask',
            'result_url': 'https://api.anti-captcha.com/getTaskResult',
            'balance_url': 'https://api.anti-captcha.com/getBalance',
        },
        'capsolver': {
            'create_url': 'https://api.capsolver.com/createTask',
            'result_url': 'https://api.capsolver.com/getTaskResult',
            'balance_url': 'https://api.capsolver.com/getBalance',
        },
    }

    def __init__(self, provider: str, api_key: str):
        self.provider = provider.lower().replace('-', '').replace('_', '')
        self.api_key = api_key
        if self.provider not in self.PROVIDERS:
            raise ValueError(f'Unknown provider: {provider}. '
                           f'Supported: {", ".join(self.PROVIDERS.keys())}')
        self.config = self.PROVIDERS[self.provider]

    def _post_json(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST',
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _get(self, url: str) -> str:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode('utf-8')

    # ── Balance ──────────────────────────────────────────────────────────

    def get_balance(self) -> float:
        try:
            if self.provider == '2captcha':
                url = f'{self.config["balance_url"]}?key={self.api_key}&action=getbalance&json=1'
                data = json.loads(self._get(url))
                return float(data.get('request', 0))

            else:  # anticaptcha, capsolver (same API format)
                data = self._post_json(self.config['balance_url'],
                                        {'clientKey': self.api_key})
                return float(data.get('balance', 0))
        except Exception as e:
            print(f'{_LOG_PREFIX} Balance check failed: {e}')
            return -1.0

    # ── Solve reCAPTCHA v2 ───────────────────────────────────────────────

    def solve_recaptcha_v2(self, sitekey: str, page_url: str,
                           timeout: int = 120) -> str:
        """Solve reCAPTCHA v2 challenge.

        Args:
            sitekey: Google reCAPTCHA site key
            page_url: URL of the page with the CAPTCHA
            timeout: Max wait seconds

        Returns:
            reCAPTCHA token string, or '' on failure
        """
        try:
            task_id = self._create_recaptcha_task(sitekey, page_url)
            if not task_id:
                return ''

            print(f'{_LOG_PREFIX} Task created: {task_id}, waiting for solution...')
            return self._poll_result(task_id, timeout)

        except Exception as e:
            print(f'{_LOG_PREFIX} Solve failed: {e}')
            return ''

    def _create_recaptcha_task(self, sitekey: str, page_url: str) -> str:
        if self.provider == '2captcha':
            url = (f'{self.config["create_url"]}?key={self.api_key}'
                   f'&method=userrecaptcha&googlekey={sitekey}'
                   f'&pageurl={urllib.parse.quote(page_url)}&json=1')
            data = json.loads(self._get(url))
            if data.get('status') == 1:
                return str(data['request'])
            return ''

        else:  # anticaptcha, capsolver
            payload = {
                'clientKey': self.api_key,
                'task': {
                    'type': 'RecaptchaV2TaskProxyless',
                    'websiteURL': page_url,
                    'websiteKey': sitekey,
                },
            }
            # CapSolver uses NoCaptchaTaskProxyless
            if self.provider == 'capsolver':
                payload['task']['type'] = 'ReCaptchaV2TaskProxyLess'

            data = self._post_json(self.config['create_url'], payload)
            return str(data.get('taskId', ''))

    def _poll_result(self, task_id: str, timeout: int) -> str:
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(5)
            try:
                if self.provider == '2captcha':
                    url = (f'{self.config["result_url"]}?key={self.api_key}'
                           f'&action=get&id={task_id}&json=1')
                    data = json.loads(self._get(url))
                    if data.get('status') == 1:
                        return data['request']
                    if 'ERROR' in str(data.get('request', '')):
                        print(f'{_LOG_PREFIX} Error: {data["request"]}')
                        return ''
                else:
                    data = self._post_json(self.config['result_url'], {
                        'clientKey': self.api_key,
                        'taskId': task_id,
                    })
                    status = data.get('status', '')
                    if status == 'ready':
                        solution = data.get('solution', {})
                        return solution.get('gRecaptchaResponse', '')
                    if status == 'failed':
                        return ''
            except Exception:
                continue

        print(f'{_LOG_PREFIX} Timeout waiting for CAPTCHA solution')
        return ''
