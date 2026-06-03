/**
 * profiles.js — NST-Style Profile Manager (Complete Rebuild)
 *
 * Features:
 *   - NST-style table with columns (Profile, Proxy, Status, Group, Updated, Actions)
 *   - Filter bar (All, Logged In, Not Logged In, Failed, Running)
 *   - 4-tab Create/Edit modal (Overview, Proxy, Hardware, Advanced, Credentials)
 *   - Summary panel (right side)
 *   - Context menu (right-click)
 *   - Batch operations (Login, Ops, Appeal, Health)
 *   - Pagination with page size selector
 */
(function (App) {
    'use strict';

    let _searchDebounce = null;
    let _statusPoll = null;
    // While > Date.now(), the status-polling loop won't auto-stop even
    // if no browsers appear open. Used by Re-Login so the final
    // `status: login_failed → logged_in` flip (which the backend writes
    // a moment AFTER closing the browser) actually reaches the UI.
    let _statusPollHoldUntil = 0;
    let _currentFilter = 'all';
    let _currentGroup = '';   // '' = all groups
    let _editingId = null;
    let _allProfiles = [];  // cached for filter counts
    let _reviewStats = {};  // { profileId: {total, live, pending, not_posted, last_scanned, scan_status, scan_error} }
    let _contextProfileId = null;
    let _selectedIds = new Set();
    let _pmGroupsState = ['default'];  // groups for profile create/edit modal

    function _renderPmGroupTags() {
        const container = document.getElementById('pmGroupTags');
        if (!container) return;
        container.innerHTML = _pmGroupsState.map((g, i) => `
            <span class="pm-group-pill" style="display:inline-flex;align-items:center;gap:4px;cursor:default;">
                ${_esc(g)}
                <i class="fas fa-times" data-idx="${i}" style="font-size:9px;cursor:pointer;opacity:0.7;" title="Remove"></i>
            </span>`).join('');
        container.querySelectorAll('.fa-times').forEach(icon => icon.addEventListener('click', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            _pmGroupsState.splice(idx, 1);
            if (!_pmGroupsState.length) _pmGroupsState = ['default'];
            _renderPmGroupTags();
        }));
    }

    // OS labels for display
    const _OS_LABELS = {
        random: 'Random',
        windows: 'Windows',
        macos: 'macOS',
        linux: 'Linux',
    };

    // Engine labels
    const _ENGINE_LABELS = {
        nexus: { name: 'NexusBrowser (Local)', badge: 'Nexus', color: 'var(--primary)', tagClass: 'pm-engine-tag-nexus' },
    };
    function _engineInfo(p) { return _ENGINE_LABELS.nexus; }

    // ── Helpers ──────────────────────────────────────────────────────────

    function _esc(s) { return App.escapeHtml ? App.escapeHtml(String(s || '')) : String(s || ''); }

    // Compact relative time: "just now" / "5m ago" / "3h ago" / "2d ago" / "Jan 5"
    function _relTime(iso) {
        if (!iso) return '';
        const t = Date.parse(iso);
        if (isNaN(t)) return '';
        const diff = Math.max(0, Math.floor((Date.now() - t) / 1000));
        if (diff < 45) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        if (diff < 86400 * 30) return Math.floor(diff / 86400) + 'd ago';
        // Older than 30 days → show date
        const d = new Date(t);
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }

    // Full timestamp for tooltips: "2026-06-01 11:36"
    function _fmtFull(iso) {
        if (!iso) return '';
        return String(iso).replace('T', ' ').slice(0, 16);
    }

    // === Review-stats badge helpers (Task 9) ===

    async function _fetchReviewStats() {
        // Only swap cache on success — a failed fetch (auth not ready,
        // backend down, transient 5xx) keeps the last-known stats so badges
        // don't briefly flash to "never scanned".
        try {
            const resp = await App.apiFetch('/api/profiles/review-stats');
            if (!resp.ok) {
                console.warn(`[review-stats] fetch HTTP ${resp.status}`);
                return;
            }
            const data = await resp.json();
            if (data && data.success) {
                _reviewStats = data.stats || {};
            } else {
                console.warn('[review-stats] backend reply:', (data && data.message) || 'success=false');
            }
        } catch (e) {
            console.warn('[review-stats] fetch failed', e);
        }
    }

    function _relativeTime(iso) {
        if (!iso) return 'never';
        try {
            const d = new Date(iso);
            const diff = (Date.now() - d.getTime()) / 1000;
            if (diff < 60) return 'just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
            return `${Math.floor(diff / 86400)}d ago`;
        } catch (e) { return iso; }
    }

    // Compact, human-friendly label for an error message stored in
    // `scan_error`. Long Playwright tracebacks become "Timeout" / "Network
    // error" / "Page didn't load" — full message is still in the tooltip.
    function _reviewStatsErrorLabel(scanError) {
        const e = String(scanError || '').toLowerCase();
        if (!e) return 'Error';
        if (e.includes('not_logged_in')) return 'Not logged in';
        if (e.includes('navigation') && e.includes('timeout')) return 'Network timeout';
        if (e.includes('launch')) return 'Browser launch failed';
        if (e.includes('tablist')) return "Page didn't load";
        if (e.includes('timeout')) return 'Timeout';
        if (e.includes('err_proxy') || e.includes('proxy')) return 'Proxy error';
        if (e.includes('err_internet') || e.includes('err_name')) return 'Network error';
        return 'Error';
    }

    function _reviewStatsBadgeHtml(profileId) {
        const s = _reviewStats[profileId];
        if (!s || s.scan_status === undefined) {
            return `<span class="pm-rs-badge pm-rs-never" title="Click Sync Review Stats to scan">— never scanned</span>`;
        }
        if (s.scan_status === 'error' && (s.scan_error || '').toLowerCase().includes('not_logged_in')) {
            return `<span class="pm-rs-badge pm-rs-login" title="Profile is not signed in to Google. Re-login first, then re-scan.">⚠ Not logged in</span>`;
        }
        if (s.scan_status === 'error') {
            const label = _reviewStatsErrorLabel(s.scan_error);
            return `<span class="pm-rs-badge pm-rs-error" title="${_esc(s.scan_error || 'error')}">⚠ ${_esc(label)}</span>`;
        }
        if (s.scan_status === 'skipped') {
            return `<span class="pm-rs-badge pm-rs-skipped" title="${_esc(s.scan_error || 'skipped')}">↻ skipped</span>`;
        }
        const total = s.total || 0;
        const live = s.live || 0;
        const notPosted = (s.pending || 0) + (s.not_posted || 0);
        const tip = `Last scanned: ${_relativeTime(s.last_scanned)}`;
        return `<span class="pm-rs-badge" data-profile-id="${_esc(profileId)}" title="${_esc(tip)}">
            <span class="pm-rs-chip pm-rs-total">Σ ${total}</span>
            <span class="pm-rs-chip pm-rs-live">● ${live}</span>
            <span class="pm-rs-chip pm-rs-notposted">✕ ${notPosted}</span>
        </span>`;
    }

    function _refreshAllBadges() {
        // Scope to actual profile rows — `data-profile-id` also appears on
        // dup-modal checkboxes and the badge itself.
        document.querySelectorAll('.pm-row[data-profile-id]').forEach(row => {
            const pid = row.getAttribute('data-profile-id');
            const slot = row.querySelector('.pm-rs-slot');
            if (slot) slot.innerHTML = _reviewStatsBadgeHtml(pid);
        });
    }

    // === Review-stats Sync button + scope dropdown (Task 11) ===

    function _initReviewStatsSync() {
        const btn = document.getElementById('pmRsSyncBtn');
        const menu = document.getElementById('pmRsSyncMenu');
        if (!btn || !menu) return;

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const showing = menu.style.display !== 'none';
            menu.style.display = showing ? 'none' : 'block';
            if (!showing) {
                const cntEl = document.getElementById('pmRsSelectedCount');
                if (cntEl) cntEl.textContent = String(_selectedIds.size);
            }
        });
        document.addEventListener('click', () => { menu.style.display = 'none'; });
        // Clicks INSIDE the menu (workers input, label, padding) shouldn't
        // close it — only scope buttons should trigger close-on-click.
        menu.addEventListener('click', (e) => e.stopPropagation());

        menu.querySelectorAll('button[data-rs-scope]').forEach(b => {
            b.addEventListener('click', async (e) => {
                e.stopPropagation();
                menu.style.display = 'none';
                const scope = b.getAttribute('data-rs-scope');
                await _startReviewStatsScan(scope);
            });
        });
    }

    // Fetch every profile ID matching the active filter/search/group — the
    // list view is paginated so the DOM only shows the current page; the
    // scan scope ("all") refers to the whole filtered set, not one page.
    async function _fetchFilteredProfileIds() {
        const search = _val('profileSearch');
        const searchBy = _val('profileSearchBy') || 'name';
        const filterParam = _currentFilter !== 'all' ? `&filter=${_currentFilter}` : '';
        const groupParam = _currentGroup ? `&group=${encodeURIComponent(_currentGroup)}` : '';
        const searchByParam = searchBy !== 'name' ? `&search_by=${searchBy}` : '';
        const url = `/api/profiles?search=${encodeURIComponent(search)}&page=1&per_page=10000${filterParam}${groupParam}${searchByParam}`;
        try {
            const resp = await App.apiFetch(url);
            const data = await resp.json();
            if (!data.success) return [];
            return (data.profiles || []).map(p => p.id);
        } catch (e) {
            return [];
        }
    }

    async function _startReviewStatsScan(scope) {
        let profile_ids = null;
        if (scope === 'selected') {
            if (_selectedIds.size === 0) {
                App.toast && App.toast('No profiles selected', 'error');
                return;
            }
            profile_ids = [..._selectedIds];
        } else if (scope === 'never') {
            const all = await _fetchFilteredProfileIds();
            profile_ids = all.filter(id => !_reviewStats[id]);
            if (profile_ids.length === 0) {
                App.toast && App.toast('All matching profiles already scanned', 'info');
                return;
            }
        } else if (scope === 'all') {
            // "All" = every profile in the current filter+search+group result
            // set (across all pages), NOT the entire DB. Sending null would
            // scan thousands the user didn't intend.
            profile_ids = await _fetchFilteredProfileIds();
            if (profile_ids.length === 0) {
                App.toast && App.toast('No profiles match the current filter', 'error');
                return;
            }
        }
        const workersEl = document.getElementById('pmRsWorkers');
        let num_workers = parseInt((workersEl && workersEl.value) || '5', 10);
        if (!Number.isFinite(num_workers) || num_workers < 1) num_workers = 1;
        if (num_workers > 20) num_workers = 20;
        try {
            const resp = await App.apiFetch('/api/profiles/review-stats/scan', {
                method: 'POST',
                body: JSON.stringify({ profile_ids, num_workers }),
            });
            const data = await resp.json();
            if (!data.success) {
                App.toast && App.toast(data.message || 'Scan failed', 'error');
                return;
            }
            App.toast && App.toast(`Scanning ${data.queued} profile${data.queued === 1 ? '' : 's'}…`, 'success');
            _startReviewStatsPoll();  // implemented in Task 12
        } catch (e) {
            App.toast && App.toast('Backend unreachable', 'error');
        }
    }

    // === Task 12: real progress strip polling ===
    let _rsPollTimer = null;
    let _rsHideTimer = null;

    function _startReviewStatsPoll() {
        if (_rsPollTimer) return;  // already polling
        if (_rsHideTimer) { clearTimeout(_rsHideTimer); _rsHideTimer = null; }

        const strip = document.getElementById('pmRsProgress');
        if (!strip) return;
        strip.style.display = '';

        const cancelBtn = document.getElementById('pmRsCancelBtn');
        if (cancelBtn) {
            cancelBtn.onclick = async () => {
                try { await App.apiFetch('/api/profiles/review-stats/cancel', { method: 'POST' }); } catch (e) {}
            };
        }

        const tick = async () => {
            try {
                const resp = await App.apiFetch('/api/profiles/review-stats/status');
                const s = await resp.json();
                _renderRsProgress(s);
                if (!s.running) {
                    clearInterval(_rsPollTimer); _rsPollTimer = null;
                    await _fetchReviewStats();
                    _refreshAllBadges();
                    _rsHideTimer = setTimeout(() => {
                        strip.style.display = 'none';
                    }, 3000);
                }
            } catch (e) { /* keep polling */ }
        };
        tick();
        _rsPollTimer = setInterval(tick, 2000);
    }

    function _renderRsProgress(s) {
        const strip = document.getElementById('pmRsProgress');
        if (!strip) return;
        const text = strip.querySelector('.pm-rs-progress-text');
        const fill = strip.querySelector('.pm-rs-progress-fill');
        const cur  = strip.querySelector('.pm-rs-progress-current');
        const done = s.done || 0, total = s.total || 0;
        const pct = total ? Math.round((done / total) * 100) : 0;
        if (text) text.textContent =
            `${s.running ? '⟳ Scanning…' : '✓ Done.'} ${done}/${total} done · ${s.skipped||0} skipped · ${s.errors||0} error${(s.errors||0) === 1 ? '' : 's'}`;
        if (fill) fill.style.width = pct + '%';
        if (cur) cur.textContent = (s.current && s.current.length)
            ? `Current: ${s.current.join(', ')}` : '';
    }

    async function _resumeRsPollIfRunning() {
        try {
            const resp = await App.apiFetch('/api/profiles/review-stats/status');
            const s = await resp.json();
            if (s.running) _startReviewStatsPoll();
        } catch (e) {}
    }

    // === Profile row redesign helpers (2026-05-23) ===

    // Convert ISO-2 country code (e.g. "US") to flag emoji (🇺🇸)
    function _flagFromCC(cc) {
        if (!cc || cc.length !== 2) return '';
        const A = 0x1F1E6, ASCII_A = 65;
        return String.fromCodePoint(A + (cc.charCodeAt(0) - ASCII_A)) +
               String.fromCodePoint(A + (cc.charCodeAt(1) - ASCII_A));
    }

    // Format a 6-digit TOTP code as "123 456"
    function _formatTotp(code) {
        if (!code || code.length !== 6) return '------';
        return code.substring(0, 3) + ' ' + code.substring(3);
    }

    // Copy text to clipboard, flash the button green, show a toast
    function _copyWithToast(text, el, label) {
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            if (el) {
                // Text span (.pm-copyable) — flash background only, don't touch innerHTML
                if (el.classList && el.classList.contains('pm-copyable')) {
                    el.classList.add('pm-copied');
                    setTimeout(() => el.classList.remove('pm-copied'), 350);
                } else {
                    // Icon button — swap to check glyph briefly
                    const prev = el.innerHTML;
                    el.classList.add('copied');
                    el.innerHTML = '<i class="fas fa-check"></i>';
                    setTimeout(() => {
                        el.classList.remove('copied');
                        el.innerHTML = prev;
                    }, 1200);
                }
            }
            if (App.toast) App.toast((label || 'Copied') + ' ✓', 'success');
        }).catch(() => {
            if (App.toast) App.toast('Copy failed', 'error');
        });
    }

    // === Country lookup queue (1500ms throttle, FIFO) ===
    const _countryQueue = [];
    const _countryInflight = new Set();
    let _countryWorking = false;

    function _enqueueCountry(profileId) {
        if (!profileId) return;
        if (_countryInflight.has(profileId)) return;
        if (_countryQueue.includes(profileId)) return;
        _countryQueue.push(profileId);
        _countryWorkerKick();
    }

    async function _countryWorkerKick() {
        if (_countryWorking) return;
        _countryWorking = true;
        while (_countryQueue.length > 0) {
            const id = _countryQueue.shift();
            _countryInflight.add(id);
            try {
                const data = await _api('/api/profiles/' + id + '/proxy-country');
                if (data && data.success) {
                    const p = _allProfiles.find(x => x.id === id);
                    if (p) {
                        p.proxy = p.proxy || {};
                        p.proxy.country = data.country;
                        p.proxy.country_code = data.country_code;
                        if (data.current_ip) p.proxy.current_ip = data.current_ip;
                    }
                    const cc = data.country_code || '';
                    const flag = cc ? `<span class="pm-country-flag">${_flagFromCC(cc)}</span> ` : '';
                    document.querySelectorAll(`[data-country-for="${id}"]`).forEach(el => {
                        el.innerHTML = flag + `<span>${_esc(data.country || 'Unknown')}</span>`;
                    });
                    if (data.current_ip) {
                        document.querySelectorAll(`[data-current-ip-for="${id}"]`).forEach(el => {
                            el.textContent = data.current_ip;
                            el.title = 'Current session IP (rotates per session)';
                        });
                    }
                }
            } catch (e) {
                // Swallow — row will retry on next render that sees no cache.
            } finally {
                _countryInflight.delete(id);
            }
            if (_countryQueue.length > 0) {
                await new Promise(r => setTimeout(r, 1500));
            }
        }
        _countryWorking = false;
    }

    // === Group dropdown ===
    let _groupOptionsCache = null;

    async function _loadGroupOptions(force) {
        if (_groupOptionsCache && !force) return _groupOptionsCache;
        try {
            const data = await _api('/api/profiles/groups');
            _groupOptionsCache = (data && data.groups) ? data.groups.slice() : [];
        } catch {
            _groupOptionsCache = [];
        }
        return _groupOptionsCache;
    }

    async function _onGroupChange(selectEl) {
        const id = selectEl.dataset.id;
        const prev = selectEl.dataset.prevValue || '';
        let newGroup = selectEl.value;

        if (newGroup === '__NEW__') {
            const name = (prompt('New group name:') || '').trim();
            if (!name) {
                selectEl.value = prev;
                return;
            }
            // Insert the new option above the __NEW__ entry and select it
            const newOpt = document.createElement('option');
            newOpt.value = name;
            newOpt.textContent = name;
            const newMarker = selectEl.querySelector('option[value="__NEW__"]');
            selectEl.insertBefore(newOpt, newMarker);
            selectEl.value = name;
            newGroup = name;
        }

        await _commitGroupChange(id, newGroup, selectEl, prev);
    }

    async function _commitGroupChange(id, newGroup, selectEl, prev) {
        // Optimistic local update — no row re-render, no blink
        const p = _allProfiles.find(x => x.id === id);
        if (p) {
            p.group = newGroup;
            p.groups = [newGroup];
        }
        selectEl.dataset.prevValue = newGroup;

        try {
            const res = await _api('/api/profiles/' + id, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ group: newGroup }),
            });
            if (!res || res.success === false) {
                throw new Error((res && res.message) || 'Update failed');
            }
            // Invalidate cache so any new group surfaces in other rows next render
            _groupOptionsCache = null;
        } catch (e) {
            // Revert
            if (p) {
                p.group = prev;
                p.groups = prev ? [prev] : [];
            }
            selectEl.value = prev;
            selectEl.dataset.prevValue = prev;
            if (App.toast) App.toast('Group change failed: ' + (e.message || e), 'error');
        }
    }

    // === Cell builders for the new row layout ===

    function _credentialsCellHTML(p) {
        const email = p.email || '';
        const hasPass = !!p.password;
        const emailLine = email ? `<div class="pm-cred-line">
            <span class="pm-cred-text pm-copyable" data-copy-value="${_esc(email)}" data-copy-label="Email" title="Click to copy email">${_esc(email)}</span>
        </div>` : `<div class="pm-cred-line"><span class="pm-cred-text" style="color:var(--text-muted);">—</span></div>`;
        const passLine = hasPass ? `<div class="pm-cred-line">
            <span class="pm-cred-text pm-copyable" data-copy-value="${_esc(p.password)}" data-copy-label="Password" title="Click to copy password" style="letter-spacing:2px;">••••••••</span>
        </div>` : '';
        return `<div class="pm-col-creds">${emailLine}${passLine}</div>`;
    }

    function _proxyTotpCellHTML(p) {
        const proxy = p.proxy || {};
        const hasProxy = !!(proxy.host || proxy.server);
        const cc = proxy.country_code || '';
        const country = proxy.country || '';
        const currentIp = proxy.current_ip || '';
        const totp = p.totp_secret || '';

        let countryHTML;
        if (!hasProxy) {
            countryHTML = `<div class="pm-country-line" style="color:var(--text-muted);">No proxy</div>`;
        } else if (country && country.toLowerCase() !== 'unknown') {
            const flag = cc ? `<span class="pm-country-flag">${_flagFromCC(cc)}</span>` : '';
            const ipLine = currentIp
                ? `<div class="pm-current-ip" data-current-ip-for="${p.id}" title="Current session IP (rotates per session) — click refresh to update">${_esc(currentIp)}</div>`
                : `<div class="pm-current-ip" data-current-ip-for="${p.id}"></div>`;
            countryHTML = `<div class="pm-country-line" data-country-for="${p.id}">${flag}<span>${_esc(country)}</span>
                <button class="pm-country-refresh" data-country-refresh="${p.id}" title="Re-check IP/country through proxy"><i class="fas fa-sync-alt"></i></button>
            </div>${ipLine}`;
        } else {
            // No cached country yet — don't auto-fetch (burns proxy bandwidth on every render).
            // Show a clickable button so the user can do it on demand.
            countryHTML = `<div class="pm-country-line" data-country-for="${p.id}">
                <button class="pm-country-check-btn" data-country-refresh="${p.id}" title="Check country + IP through proxy">
                    <i class="fas fa-search-location"></i> Check IP
                </button>
            </div><div class="pm-current-ip" data-current-ip-for="${p.id}"></div>`;
        }

        // Pre-fill code from the in-memory cache so re-renders during the
        // status poll (every 2s while any browser is open) don't flash the
        // "------" placeholder before the next 1s ticker fires.
        const cachedCode = _cachedTotpCode(totp);
        const initialCode = cachedCode ? _formatTotp(cachedCode) : '------';
        const epochNow = Math.floor(Date.now() / 1000);
        const initialRemaining = 30 - (epochNow % 30);
        const totpHTML = totp ? `<div class="pm-totp-line" data-totp-row="${p.id}">
            <span class="pm-totp-code pm-copyable" data-totp-code="${_esc(cachedCode)}" data-totp-secret="${_esc(totp)}" data-copy-from-totp="${p.id}" data-copy-label="2FA" title="Click to copy 2FA code">${initialCode}</span>
            <span class="pm-totp-countdown" data-totp-countdown>${initialRemaining}s</span>
        </div>` : '';

        return `<div class="pm-col-proxy">${countryHTML}${totpHTML}</div>`;
    }

    function _groupSelectHTML(p, groupOptions) {
        const cur = (p.groups && p.groups.length) ? p.groups[0] : (p.group || 'default');
        const options = groupOptions || [];
        const inCache = options.includes(cur);
        const curOpt = inCache ? '' : `<option value="${_esc(cur)}" selected>${_esc(cur)}</option>`;
        const opts = options.map(g => `<option value="${_esc(g)}"${g === cur ? ' selected' : ''}>${_esc(g)}</option>`).join('');
        return `<div class="pm-col-group">
            <select class="pm-group-select" data-id="${p.id}" data-prev-value="${_esc(cur)}">
                ${curOpt}${opts}
                <option disabled>──────────</option>
                <option value="__NEW__">+ New group…</option>
            </select>
            <button class="btn btn-outline btn-sm pm-appeal-btn" data-id="${p.id}" title="Do Appeal for this profile" style="color:#f59e0b;border-color:rgba(245,158,11,0.5);padding:4px 8px;font-size:11px;"><i class="fas fa-gavel"></i> Do Appeal</button>
        </div>`;
    }

    // === Shared TOTP timer (one interval drives every visible code) ===
    let _totpTickerHandle = null;
    let _totpLastBoundary = -1;
    let _totpEmptyTicks = 0;

    // Global cache: secret -> { code, boundary }. Lets row re-renders
    // paint the current code instantly instead of flashing "------" until
    // the next 1s tick fires (which was the visible OTP "blink" while a
    // browser is open and the status poll re-renders rows every 2s).
    const _totpCodeCache = new Map();

    function _cachedTotpCode(secret) {
        if (!secret) return '';
        const entry = _totpCodeCache.get(secret);
        if (!entry) return '';
        const boundary = Math.floor(Date.now() / 30000);
        return entry.boundary === boundary ? (entry.code || '') : '';
    }

    function _totpTickerStart() {
        if (_totpTickerHandle) {
            // Re-render: force a re-compute and paint immediately so newly
            // rendered rows don't sit on "------" for up to a second.
            _totpLastBoundary = -1;
            _totpTick();
            return;
        }
        _totpTick();
        _totpTickerHandle = setInterval(_totpTick, 1000);
    }

    async function _totpTick() {
        const epoch = Math.floor(Date.now() / 1000);
        const boundary = Math.floor(epoch / 30);
        const remaining = 30 - (epoch % 30);

        const countdownEls = document.querySelectorAll('[data-totp-countdown]');
        if (countdownEls.length === 0) {
            _totpEmptyTicks++;
            if (_totpEmptyTicks >= 2 && _totpTickerHandle) {
                clearInterval(_totpTickerHandle);
                _totpTickerHandle = null;
                _totpLastBoundary = -1;
            }
            return;
        }
        _totpEmptyTicks = 0;

        countdownEls.forEach(el => {
            el.textContent = remaining + 's';
        });

        // Pass 1 — paint from cache instantly. Covers freshly re-rendered
        // rows mid-window (status poll re-renders every 2s while a browser
        // is open and was leaving cells on "------" until the next tick).
        const codeEls = document.querySelectorAll('[data-totp-code]');
        const stale = [];
        for (const el of codeEls) {
            const secret = el.dataset.totpSecret;
            if (!secret) continue;
            const cached = _cachedTotpCode(secret);
            if (cached) {
                if (el.dataset.totpCode !== cached) {
                    el.textContent = _formatTotp(cached);
                    el.dataset.totpCode = cached;
                }
            } else {
                stale.push({ el, secret });
            }
        }

        // Pass 2 — compute fresh codes only for cells the cache couldn't
        // serve (new boundary, or secret seen for the first time).
        if (stale.length) {
            _totpLastBoundary = boundary;
            const computed = new Map();
            for (const { el, secret } of stale) {
                if (!computed.has(secret)) {
                    try {
                        const code = await App._generateTOTP(secret);
                        computed.set(secret, code || '');
                        _totpCodeCache.set(secret, { code: code || '', boundary });
                    } catch {
                        computed.set(secret, '');
                    }
                }
                const code = computed.get(secret);
                el.textContent = _formatTotp(code);
                el.dataset.totpCode = code || '';
            }
        } else {
            _totpLastBoundary = boundary;
        }
    }

    function _timeAgo(iso) {
        if (!iso) return 'Never';
        const diff = (Date.now() - new Date(iso).getTime()) / 1000;
        if (diff < 60) return 'Just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    async function _api(url, opts) {
        const res = await App.apiFetch(url, opts);
        const ct = res.headers.get('content-type') || '';
        if (!ct.includes('application/json')) throw new Error('Non-JSON response. Restart backend.');
        return res.json();
    }

    function _$(id) { return document.getElementById(id); }
    function _btn(id, fn) { const el = _$(id); if (el) el.addEventListener('click', fn); }
    function _val(id) { return (_$(id) || {}).value || ''; }
    function _setVal(id, v) { const el = _$(id); if (el) el.value = v; }
    function _radio(name) { const el = document.querySelector(`input[name="${name}"]:checked`); return el ? el.value : ''; }
    function _setRadio(name, value) {
        const el = document.querySelector(`input[name="${name}"][value="${value}"]`);
        if (el) {
            el.checked = true;
            // Sync active class on pill/tab containers
            const pill = el.closest('.pm-os-pill, .pm-engine-tab');
            if (pill) {
                const container = pill.parentElement;
                container.querySelectorAll('.pm-os-pill, .pm-engine-tab').forEach(s => s.classList.remove('active'));
                pill.classList.add('active');
            }
        }
    }
    function _checked(id) { const el = _$(id); return el ? el.checked : false; }
    function _setChecked(id, v) { const el = _$(id); if (el) el.checked = !!v; }

    // Refocus webview after native confirm() steals focus (Electron bug)
    function _refocusAfterDialog() {
        window.focus();
        document.body.focus();
        setTimeout(() => {
            window.focus();
            document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
            document.body.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        }, 50);
        setTimeout(() => { window.focus(); }, 200);
    }

    // Non-blocking confirm dialog
    function _asyncConfirm(message) {
        return App.confirm(message, 'Delete', 'btn-danger');
    }

    // ══════════════════════════════════════════════════════════════════════
    // LOAD PROFILES (paginated + search + filter)
    // ══════════════════════════════════════════════════════════════════════

    let _loadRetryTimer = null;
    let _currentSort = { column: null, dir: 'asc' };
    // Pagination — defaults match the per-page selector in index.html.
    // _currentPage is reset to 1 on filter/search/group/sort change to avoid
    // landing on an out-of-range page after the result set shrinks.
    let _currentPage = 1;
    let _perPage = 50;
    let _lastTotalPages = 1;

    // Refresh the pagination footer (page X of Y, prev/next disabled state,
    // showing-N-of-M range) using the most recent fetch's totals.
    function _updatePaginationUI(totalRows, totalPages, currentPageSize) {
        const pageInfo = _$('pmPageInfo');
        const rangeEl  = _$('pmPageRange');
        const prevBtn  = _$('pmPagePrevBtn');
        const nextBtn  = _$('pmPageNextBtn');
        if (pageInfo) pageInfo.textContent = `Page ${_currentPage} of ${totalPages}`;
        if (rangeEl) {
            if (totalRows === 0) {
                rangeEl.textContent = '0 profiles';
            } else {
                const start = (_currentPage - 1) * _perPage + 1;
                const end   = start + (currentPageSize || 0) - 1;
                rangeEl.textContent = `Showing ${start}-${end} of ${totalRows}`;
            }
        }
        if (prevBtn) prevBtn.disabled = (_currentPage <= 1);
        if (nextBtn) nextBtn.disabled = (_currentPage >= totalPages);
    }

    // Single helper used by filter chips, search input, group dropdown and
    // sort headers — anything that changes the result set should reset to
    // page 1 so the user doesn't land on a now-out-of-range page.
    function _resetPageAndReload() {
        _currentPage = 1;
        loadProfiles();
    }

    async function loadProfiles() {
        const search = _val('profileSearch');
        const searchBy = _val('profileSearchBy') || 'name';
        const listEl = _$('profileList');
        const countEl = _$('profileCount');
        if (!listEl) return;

        try {
            const filterParam = _currentFilter !== 'all' ? `&filter=${_currentFilter}` : '';
            const groupParam = _currentGroup ? `&group=${encodeURIComponent(_currentGroup)}` : '';
            const searchByParam = searchBy !== 'name' ? `&search_by=${searchBy}` : '';
            const pageParam = `&page=${_currentPage}&per_page=${_perPage}`;

            // counts endpoint = lightweight summary (no per-profile data).
            // list endpoint   = paginated slice (50/100/… per page).
            // Running them in parallel keeps perceived load fast and avoids
            // the old per_page=9999 fetch that was hanging the UI at scale.
            const [countsData, data] = await Promise.all([
                _api('/api/profiles/counts'),
                _api(`/api/profiles?search=${encodeURIComponent(search)}${pageParam}${filterParam}${groupParam}${searchByParam}`),
            ]);

            if (countsData && countsData.success) {
                _updateFilterCounts(countsData.by_filter || {});
                _refreshGroupsFromProfiles(countsData.groups || []);
            }

            if (!data.success) { listEl.innerHTML = '<div class="tools-empty">Failed to load profiles</div>'; return; }

            let profiles = data.profiles || [];
            const total = data.total != null ? data.total : profiles.length;
            _lastTotalPages = data.total_pages || 1;
            // Backend clamps page to [1, total_pages] — sync our local var so
            // the UI reflects the actual page rendered (e.g. after filter
            // shrank the result set and we were past the last page).
            if (data.page && data.page !== _currentPage) {
                _currentPage = data.page;
            }
            _updatePaginationUI(total, _lastTotalPages, profiles.length);
            
            // Apply sorting if set
            if (_currentSort.column === 'updated') {
                // Activity column was removed in the 2026-05-23 redesign — fall back to default order
                _currentSort.column = null;
            }
            if (_currentSort.column) {
                profiles.sort((a, b) => {
                    let valA = a[_currentSort.column] || '';
                    let valB = b[_currentSort.column] || '';
                    if (_currentSort.column === 'group') {
                        valA = (a.groups && a.groups.length ? a.groups[0] : (a.group || ''));
                        valB = (b.groups && b.groups.length ? b.groups[0] : (b.group || ''));
                    } else if (_currentSort.column === 'updated') {
                        const tA = Math.max(a.last_health_at ? new Date(a.last_health_at).getTime() : 0, a.last_appeal_at ? new Date(a.last_appeal_at).getTime() : 0);
                        const tB = Math.max(b.last_health_at ? new Date(b.last_health_at).getTime() : 0, b.last_appeal_at ? new Date(b.last_appeal_at).getTime() : 0);
                        valA = tA; valB = tB;
                    } else if (_currentSort.column === 'status') {
                        valA = a.status || ''; valB = b.status || '';
                    } else if (_currentSort.column === 'name') {
                        valA = a.name ? a.name.toLowerCase() : '';
                        valB = b.name ? b.name.toLowerCase() : '';
                    }
                    if (valA < valB) return _currentSort.dir === 'asc' ? -1 : 1;
                    if (valA > valB) return _currentSort.dir === 'asc' ? 1 : -1;
                    return 0;
                });
            }

            _allProfiles = profiles;

            // Fire-and-forget; UI updates in-place when stats arrive
            _fetchReviewStats().then(() => { _refreshAllBadges(); _resumeRsPollIfRunning(); });

            if (countEl) countEl.textContent = `${total} profile${total !== 1 ? 's' : ''}`;

            if (profiles.length === 0) {
                // If counts endpoint reported total=0 in the fully-unfiltered
                // view, the backend may still be starting — retry once.
                const globalTotal = (countsData && countsData.total) || 0;
                if (globalTotal === 0 && !search && _currentFilter === 'all' && !_currentGroup) {
                    if (_loadRetryTimer) clearTimeout(_loadRetryTimer);
                    _loadRetryTimer = setTimeout(() => { _loadRetryTimer = null; loadProfiles(); }, 1500);
                }
                listEl.innerHTML = '<div class="tools-empty" style="padding:40px;"><i class="fas fa-user-circle"></i> No profiles match the current filter.</div>';
                return;
            }
            if (_loadRetryTimer) { clearTimeout(_loadRetryTimer); _loadRetryTimer = null; }

            // No pagination — render all profiles in current filter/group
            const groupOptions = await _loadGroupOptions();
            listEl.innerHTML = profiles.map(p => {
                const dotCls = p.status === 'logged_in' ? 'pm-dot-ok' :
                               p.status === 'login_failed' ? 'pm-dot-fail' : 'pm-dot-none';
                const dotTitle = p.status === 'logged_in' ? 'Logged In' :
                                 p.status === 'login_failed' ? 'Failed' : 'Not Logged In';
                const isOpen = p.browser_open === 'running';
                const isStarting = p.browser_open === 'starting';
                const ov = p.overview || {};
                const fp = p.fingerprint || {};
                const osBase = (ov.os || fp.os_type || 'win').substring(0, 3).toUpperCase();
                const osVerRaw = ov.os_version || '';
                const osVerNum = osVerRaw.replace(/^Windows\s*/i, '').replace(/\.\d+\.\d+$/, '').trim();
                const os = osBase + (osVerNum ? ' ' + osVerNum : '');
                const engInfo = _engineInfo(p);
                const checked = _selectedIds.has(p.id) ? 'checked' : '';

                // NOTE: country lookup is NOT auto-triggered on render anymore.
                // It used to fire on every page load → wasted proxy bandwidth.
                // Now it only runs after: profile create / launch / login / relogin,
                // OR manually via the refresh icon shown when country is missing.

                const createdRel = _relTime(p.created_at);
                const createdFull = _fmtFull(p.created_at);
                const usedRel = _relTime(p.last_used);
                const usedFull = _fmtFull(p.last_used);
                const metaParts = [];
                if (createdRel) metaParts.push(`<span title="Created ${_esc(createdFull)}"><i class="far fa-clock" style="opacity:0.6;"></i> ${_esc(createdRel)}</span>`);
                if (usedRel) metaParts.push(`<span title="Last used ${_esc(usedFull)}" style="color:#94a3b8;"><i class="fas fa-play-circle" style="opacity:0.6;"></i> ${_esc(usedRel)}</span>`);
                const metaLine = metaParts.length
                    ? `<div class="pm-row-meta">${metaParts.join('<span class="pm-meta-sep">·</span>')}</div>`
                    : '';

                return `<div class="pm-row ${isOpen ? 'pm-browser-open' : ''} ${isStarting ? 'pm-browser-starting' : ''} ${_selectedIds.has(p.id) ? 'pm-selected' : ''}" data-profile-id="${p.id}">
                    <div class="pm-col-check"><input type="checkbox" class="pm-row-check" data-id="${p.id}" ${checked}></div>
                    <div class="pm-col-profile">
                        <div class="pm-name"><span class="pm-os-badge" style="margin-right:6px;">${os}</span><span class="pm-engine-tag ${engInfo.tagClass}">${engInfo.badge}</span>${_esc(p.name || 'Unnamed')}</div>
                        ${metaLine}
                    </div>
                    ${_credentialsCellHTML(p)}
                    <div class="pm-col-reviews"><span class="pm-rs-slot">${_reviewStatsBadgeHtml(p.id)}</span></div>
                    ${_proxyTotpCellHTML(p)}
                    <div class="pm-col-status">
                        <span class="pm-dot ${dotCls}" title="${dotTitle}"></span>
                        ${isOpen ? '<span class="pm-dot pm-dot-open" title="Browser open"></span>'
                            : isStarting ? '<span class="pm-dot pm-dot-starting" title="Launching"></span>' : ''}
                    </div>
                    ${_groupSelectHTML(p, groupOptions)}
                    <div class="pm-col-actions">
                        ${isOpen
                            ? `<button class="btn btn-danger btn-sm pm-close-btn" data-id="${p.id}" title="Close"><i class="fas fa-stop"></i></button>`
                            : isStarting
                            ? `<button class="btn btn-sm pm-launching-btn" disabled title="Launching..."><i class="fas fa-spinner fa-spin"></i></button>`
                            : `<button class="btn btn-primary btn-sm pm-launch-btn" data-id="${p.id}" title="Launch"><i class="fas fa-play"></i></button>`
                        }
                        <button class="btn btn-outline btn-sm pm-relogin-btn" data-id="${p.id}" title="Re-Login" style="color:#22c55e;border-color:rgba(34,197,94,0.4);"><i class="fas fa-sign-in-alt"></i></button>
                        <button class="btn btn-outline btn-sm pm-edit-btn" data-id="${p.id}" title="Edit"><i class="fas fa-pen"></i></button>
                        ${(() => {
                            const has = !!(_reviewStats[p.id] && _reviewStats[p.id].scan_status !== undefined);
                            return `<button class="btn btn-outline btn-sm pm-scan-btn" data-id="${p.id}" title="${has ? 'Rescan' : 'Scan'} reviews" style="color:#60a5fa;border-color:rgba(96,165,250,0.4);"><i class="fas fa-sync-alt"></i></button>`;
                        })()}
                        <button class="btn btn-danger-outline btn-sm pm-delete-btn" data-id="${p.id}" title="Delete"><i class="fas fa-trash"></i></button>
                        <button class="btn btn-outline btn-sm pm-ctx-btn" data-id="${p.id}" title="More"><i class="fas fa-ellipsis-v"></i></button>
                    </div>
                </div>`;
            }).join('');

            // Attach events
            _attachRowEvents(listEl);
            _totpTickerStart();

            // Auto-start polling if any browsers are open or starting
            const hasActive = profiles.some(p => p.browser_open === 'running' || p.browser_open === 'starting');
            if (hasActive && !_statusPoll) _startStatusPolling();

        } catch (e) {
            listEl.innerHTML = `<div class="tools-empty">Error: ${_esc(e.message)}</div>`;
        }
    }

    function _attachRowEvents(listEl) {
        listEl.querySelectorAll('.pm-launch-btn').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); launchProfile(b.dataset.id); }));
        // Manual country/IP refresh button (only one network call per click).
        listEl.querySelectorAll('[data-country-refresh]').forEach(b => b.addEventListener('click', async (e) => {
            e.stopPropagation();
            const id = b.dataset.countryRefresh;
            const origHTML = b.innerHTML;
            b.disabled = true;
            b.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            try {
                const data = await _api('/api/profiles/' + id + '/proxy-country?refresh=1');
                if (data && data.success) {
                    const p = _allProfiles.find(x => x.id === id);
                    if (p) {
                        p.proxy = p.proxy || {};
                        p.proxy.country = data.country;
                        p.proxy.country_code = data.country_code;
                        if (data.current_ip) p.proxy.current_ip = data.current_ip;
                    }
                    // Re-render only this row's proxy cell
                    const row = b.closest('.pm-row');
                    if (row && p) {
                        const cell = row.querySelector('.pm-col-proxy');
                        if (cell) cell.outerHTML = _proxyTotpCellHTML(p).replace(/^<div class="pm-col-proxy">/, '<div class="pm-col-proxy">');
                    }
                    if (data.country && data.country.toLowerCase() === 'unknown') {
                        App.toast && App.toast('Proxy check returned no country — proxy may be down', 'warn');
                    }
                } else {
                    App.toast && App.toast('Country check failed', 'error');
                    b.innerHTML = origHTML;
                    b.disabled = false;
                }
            } catch (err) {
                App.toast && App.toast('Country check failed: ' + err.message, 'error');
                b.innerHTML = origHTML;
                b.disabled = false;
            }
        }));

        listEl.querySelectorAll('.pm-close-btn').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); closeProfile(b.dataset.id); }));
        listEl.querySelectorAll('.pm-relogin-btn').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); reloginProfile(b.dataset.id); }));
        listEl.querySelectorAll('.pm-edit-btn').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); openEditModal(b.dataset.id); }));
        listEl.querySelectorAll('.pm-delete-btn').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); deleteProfile(b.dataset.id); }));
        listEl.querySelectorAll('.pm-appeal-btn').forEach(b => b.addEventListener('click', async (e) => {
            e.stopPropagation();
            const pid = b.dataset.id;
            const p = _allProfiles.find(x => x.id === pid);
            const email = (p && p.email) || pid;
            const orig = b.innerHTML;
            b.disabled = true;
            b.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            try {
                const data = await _api('/api/profiles/do-all-appeal', {
                    method: 'POST',
                    // num_workers grows the shared appeal pool: clicking "Do Appeal"
                    // on several profiles runs them concurrently (up to 5), instead
                    // of one-at-a-time. Each profile is isolated so this is safe.
                    body: JSON.stringify({ profile_ids: [pid], num_workers: 5 }),
                });
                if (data && data.success) {
                    App.toast && App.toast(`Appeal queued for ${email}`, 'success');
                    // Reuse the bulk-appeal status poller so the user sees progress
                    if (typeof _startAppealStatusPolling === 'function') _startAppealStatusPolling();
                    _startStatusPolling();
                } else {
                    App.toast && App.toast((data && (data.error || data.message)) || 'Appeal failed to start', 'error');
                }
            } catch (err) {
                App.toast && App.toast('Backend unreachable', 'error');
            } finally {
                b.disabled = false;
                b.innerHTML = orig;
            }
        }));
        listEl.querySelectorAll('.pm-scan-btn').forEach(b => b.addEventListener('click', async (e) => {
            e.stopPropagation();
            const pid = b.dataset.id;
            const workersEl = document.getElementById('pmRsWorkers');
            let num_workers = parseInt((workersEl && workersEl.value) || '1', 10);
            if (!Number.isFinite(num_workers) || num_workers < 1) num_workers = 1;
            if (num_workers > 20) num_workers = 20;
            try {
                const resp = await App.apiFetch('/api/profiles/review-stats/scan', {
                    method: 'POST',
                    body: JSON.stringify({ profile_ids: [pid], num_workers }),
                });
                const data = await resp.json();
                if (data.success) {
                    App.toast && App.toast(`Scanning…`, 'success');
                    _startReviewStatsPoll();
                } else {
                    App.toast && App.toast(data.message || 'Scan failed', 'error');
                }
            } catch (err) {
                App.toast && App.toast('Backend unreachable', 'error');
            }
        }));
        listEl.querySelectorAll('.pm-ctx-btn').forEach(b => b.addEventListener('click', (e) => {
            e.stopPropagation();
            _contextProfileId = b.dataset.id;
            _showContextMenu(e.clientX, e.clientY);
        }));
        listEl.querySelectorAll('.pm-row-check').forEach(cb => cb.addEventListener('change', (e) => {
            const id = cb.dataset.id;
            if (cb.checked) _selectedIds.add(id); else _selectedIds.delete(id);
            cb.closest('.pm-row').classList.toggle('pm-selected', cb.checked);
            _updateBulkBar();
        }));
        // Unified click-to-copy on .pm-copyable spans (email, password, TOTP code)
        listEl.querySelectorAll('.pm-copyable').forEach(el => el.addEventListener('click', (e) => {
            e.stopPropagation();
            const label = el.dataset.copyLabel || 'Value';
            let val = el.dataset.copyValue || '';
            // TOTP case: value is dynamic, read live from the row's ticker output
            const totpRowId = el.dataset.copyFromTotp;
            if (totpRowId) {
                const codeEl = listEl.querySelector(`[data-totp-row="${totpRowId}"] [data-totp-code]`);
                val = codeEl ? (codeEl.dataset.totpCode || '') : '';
                if (!val || val === '------') {
                    if (App.toast) App.toast('2FA code not ready yet', 'warn');
                    return;
                }
            }
            if (val) _copyWithToast(val, el, `${label} copied`);
        }));

        // Inline group dropdown
        listEl.querySelectorAll('.pm-group-select').forEach(sel => {
            sel.addEventListener('change', (e) => { e.stopPropagation(); _onGroupChange(sel); });
            sel.addEventListener('click', (e) => e.stopPropagation());
            sel.addEventListener('mousedown', (e) => e.stopPropagation());
        });
        // Right-click context menu on rows
        listEl.querySelectorAll('.pm-row').forEach(row => {
            row.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                _contextProfileId = row.dataset.profileId;
                _showContextMenu(e.clientX, e.clientY);
            });
        });
    }

    // ── Bulk selection bar ────────────────────────────────────────────────────

    function _updateBulkBar() {
        const bar = _$('pmBulkBar');
        const countEl = _$('pmBulkCount');
        if (!bar) return;
        const n = _selectedIds.size;
        const totalVisible = document.querySelectorAll('.pm-row-check').length;
        if (n > 0) {
            bar.style.display = 'flex';
            const allSelected = n === totalVisible && totalVisible > 0;
            if (countEl) countEl.textContent = allSelected
                ? `All ${n} profiles selected`
                : `${n} of ${totalVisible} profiles selected`;
        } else {
            bar.style.display = 'none';
        }
    }

    function _bulkGroupInput() {
        return (_$('pmBulkGroupInput') ? _$('pmBulkGroupInput').value : '').trim();
    }
    function _bulkNoteInput() {
        return (_$('pmBulkNoteInput') ? _$('pmBulkNoteInput').value : '').trim();
    }

    // ── Bookmark modal ──────────────────────────────────────────────────────
    function _openBookmarkModal() {
        const overlay = _$('bookmarkModalOverlay');
        if (!overlay) return;
        const label = _$('bookmarkScopeLabel');
        if (label) {
            label.textContent = _selectedIds.size
                ? `Will apply to ${_selectedIds.size} selected profile(s).`
                : 'No profiles selected — will apply to ALL profiles.';
        }
        overlay.classList.add('active');
    }

    function _closeBookmarkModal() {
        const overlay = _$('bookmarkModalOverlay');
        if (overlay) overlay.classList.remove('active');
    }

    function _parseBookmarkLines(text) {
        const bookmarks = [];
        for (const rawLine of (text || '').split('\n')) {
            const line = rawLine.trim();
            if (!line) continue;
            let path = [], name, url;
            if (line.startsWith('bookmark::')) {
                const parts = line.split('::').map(p => p.trim());
                // parts[0]='bookmark', parts[-1]=url, parts[-2]=name, rest=folders
                if (parts.length < 3) continue;
                url = parts[parts.length - 1];
                name = parts[parts.length - 2];
                path = parts.slice(1, parts.length - 2);
            } else if (line.includes('|')) {
                const sep = line.indexOf('|');
                name = line.slice(0, sep).trim();
                url = line.slice(sep + 1).trim();
            } else {
                url = line; name = line;
            }
            bookmarks.push({ path, name, url });
        }
        return bookmarks;
    }

    async function _applyBookmarks() {
        const raw = (_$('bookmarkListInput') ? _$('bookmarkListInput').value : '').trim();
        if (!raw) { App.toast('Enter at least one bookmark', 'warn'); return; }

        const bookmarks = _parseBookmarkLines(raw);
        if (!bookmarks.length) { App.toast('No valid bookmarks found', 'warn'); return; }

        // Workers — default 5, max 20. File writes parallelize cleanly.
        const workers = Math.max(1, Math.min(parseInt(_val('bookmarkWorkers')) || 5, 20));

        // Optimistic UX — close + spawn card immediately, validate response later.
        _closeBookmarkModal();
        _startOpProgress('bookmarks');
        App.toast(`Applying ${bookmarks.length} bookmark(s)…`, 'info');

        try {
            const data = await _api('/api/profiles/add-bookmarks', {
                method: 'POST',
                body: JSON.stringify({ ids: [..._selectedIds], bookmarks, bookmarks_text: raw, workers }),
            });
            if (!data || !data.success) {
                _stopOpProgress('bookmarks', false);
                App.toast((data && data.error) || 'Failed to apply bookmarks', 'error');
            }
        } catch(e) {
            _stopOpProgress('bookmarks', false);
            App.toast('Bookmark error: ' + e.message, 'error');
        }
    }

    async function _bulkAddToGroup() {
        const group = _bulkGroupInput();
        if (!group) { App.toast('Enter a group name', 'warn'); return; }
        if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
        const note = _bulkNoteInput();
        try {
            const data = await _api('/api/profiles/bulk-assign-group', {
                method: 'POST',
                body: JSON.stringify({ ids: [..._selectedIds], group, mode: 'add', note })
            });
            if (data.success) {
                let msg = `${data.updated} profile${data.updated !== 1 ? 's' : ''} added to "${group}"`;
                if (note && data.notes_updated) msg += ` · note saved`;
                App.toast(msg, 'success');
                loadProfiles(); _loadGroups();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    async function _bulkMoveToGroup() {
        const group = _bulkGroupInput();
        if (!group) { App.toast('Enter a group name', 'warn'); return; }
        if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
        const note = _bulkNoteInput();
        try {
            const data = await _api('/api/profiles/bulk-assign-group', {
                method: 'POST',
                body: JSON.stringify({ ids: [..._selectedIds], group, mode: 'set', note })
            });
            if (data.success) {
                let msg = `${data.updated} profile${data.updated !== 1 ? 's' : ''} moved to "${group}"`;
                if (note && data.notes_updated) msg += ` · note saved`;
                App.toast(msg, 'success');
                loadProfiles(); _loadGroups();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    async function _bulkRemoveFromGroup() {
        const group = _bulkGroupInput();
        if (!group) { App.toast('Enter a group name to remove from', 'warn'); return; }
        if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
        const note = _bulkNoteInput();
        try {
            const data = await _api('/api/profiles/bulk-remove-group', {
                method: 'POST',
                body: JSON.stringify({ ids: [..._selectedIds], group, note })
            });
            if (data.success) {
                let msg = `${data.updated} profile${data.updated !== 1 ? 's' : ''} removed from "${group}"`;
                if (note && data.notes_updated) msg += ` · note saved`;
                App.toast(msg, 'success');
                loadProfiles(); _loadGroups();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    // ── Bulk Fast Mode (per-profile performance settings) ─────────────
    function _openBulkFastModeModal() {
        const m = _$('bulkFastModeModal');
        if (!m) return;
        // Reset checkboxes & scope selection
        document.querySelectorAll('.bfm-perf-toggle').forEach(cb => { cb.checked = false; });
        document.querySelectorAll('.bfm-scope-btn').forEach(b => {
            const isSelected = b.dataset.scope === 'selected';
            b.classList.toggle('active', isSelected);
            b.style.background = isSelected ? 'rgba(99,102,241,0.20)' : 'transparent';
            b.style.color = isSelected ? '#a5b4fc' : '#94a3b8';
        });
        const cnt = _$('bfmSelectedCount'); if (cnt) cnt.textContent = `(${_selectedIds.size})`;
        const grow = _$('bfmGroupRow'); if (grow) grow.style.display = 'none';
        const dirOn = document.querySelector('input[name="bfmDirection"][value="on"]');
        if (dirOn) dirOn.checked = true;
        m.style.display = 'flex';
    }
    function _closeBulkFastModeModal() {
        const m = _$('bulkFastModeModal');
        if (m) m.style.display = 'none';
    }
    async function _applyBulkFastMode() {
        const scopeBtn = document.querySelector('.bfm-scope-btn.active');
        const scope = scopeBtn ? scopeBtn.dataset.scope : 'selected';
        const dir = (document.querySelector('input[name="bfmDirection"]:checked') || {}).value || 'on';
        const enable = dir === 'on';

        // Collect checked perf keys
        const perf = {};
        document.querySelectorAll('.bfm-perf-toggle').forEach(cb => {
            if (cb.checked && cb.dataset.perfKey) perf[cb.dataset.perfKey] = enable;
        });
        if (Object.keys(perf).length === 0) {
            App.toast('Tick at least one setting to apply', 'warn');
            return;
        }

        // Workers — file-system writes are cheap, default 5, max 20
        const workers = Math.max(1, Math.min(parseInt(_val('bfmWorkers')) || 5, 20));

        const body = { perf, scope, workers };
        if (scope === 'selected') {
            if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
            body.ids = [..._selectedIds];
        } else if (scope === 'group') {
            const g = (_val('bfmGroupName') || '').trim();
            if (!g) { App.toast('Enter a group name', 'warn'); return; }
            body.group = g;
        }

        // Optimistic UX: close modal + spawn progress card immediately so the
        // user gets instant feedback. The HTTP call runs in the background;
        // if it actually fails, we tear the card down and toast the error.
        _closeBulkFastModeModal();
        _startOpProgress('fast-mode');
        const action = enable ? 'enabled' : 'disabled';
        App.toast(`Fast Mode ${action} — starting…`, 'info');

        try {
            const d = await _api('/api/profiles/bulk-perf', { method: 'POST', body: JSON.stringify(body) });
            if (!d || !d.success) {
                // Backend rejected — kill the optimistic card.
                _stopOpProgress('fast-mode', false);
                App.toast((d && (d.message || d.error)) || 'Bulk apply failed', 'error');
                return;
            }
            // Refresh the row list once the backend has had a moment to flush
            setTimeout(() => loadProfiles(), 1500);
        } catch (e) {
            _stopOpProgress('fast-mode', false);
            App.toast('Error: ' + e.message, 'error');
        }
    }

    async function _bulkUpdateProxy() {
        const user = (_$('pmBulkProxyUser') ? _$('pmBulkProxyUser').value : '').trim();
        const pass = (_$('pmBulkProxyPass') ? _$('pmBulkProxyPass').value : '').trim();
        if (!user && !pass) { App.toast('Enter proxy user or password', 'warn'); return; }
        if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
        try {
            const data = await _api('/api/profiles/bulk-update-proxy', {
                method: 'POST',
                body: JSON.stringify({ ids: [..._selectedIds], proxy_user: user, proxy_pass: pass })
            });
            if (data.success) {
                App.toast(`Proxy updated for ${data.updated} profile${data.updated !== 1 ? 's' : ''}`, 'success');
                if (_$('pmBulkProxyUser')) _$('pmBulkProxyUser').value = '';
                if (_$('pmBulkProxyPass')) _$('pmBulkProxyPass').value = '';
                loadProfiles();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    async function _bulkSaveNoteOnly() {
        const note = _bulkNoteInput();
        if (!note) { App.toast('Type a note first', 'warn'); return; }
        if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
        try {
            const data = await _api('/api/profiles/bulk-update-notes', {
                method: 'POST',
                body: JSON.stringify({ ids: [..._selectedIds], note })
            });
            if (data.success) {
                App.toast(`Note saved to ${data.updated} profile${data.updated !== 1 ? 's' : ''}`, 'success');
                loadProfiles();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    // ── Group Manager ────────────────────────────────────────────────────────

    let _groupManagerRenameTarget = '';
    let _groupManagerDeleteTarget = '';

    async function _openGroupManager() {
        _$('groupManagerOverlay').style.display = 'flex';
        await _renderGroupManager();
    }
    function _closeGroupManager() { _$('groupManagerOverlay').style.display = 'none'; }

    async function _renderGroupManager() {
        const listEl = _$('groupManagerList');
        if (!listEl) return;
        listEl.innerHTML = '<div style="color:#64748b;text-align:center;padding:20px;">Loading...</div>';
        try {
            const data = await _api('/api/profiles/groups');
            const groups = data.groups || [];
            const counts = data.counts || {};
            if (!groups.length) {
                listEl.innerHTML = '<div style="color:#64748b;text-align:center;padding:20px;">No groups yet</div>';
                return;
            }
            listEl.innerHTML = groups.map(g => `
                <div class="gm-row" data-group="${_esc(g)}">
                    <div style="display:flex;align-items:center;gap:10px;flex:1;">
                        <span class="pm-group-pill" style="pointer-events:none;">${_esc(g)}</span>
                        <span style="font-size:12px;color:#64748b;">${counts[g] || 0} profiles</span>
                    </div>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-sm gm-rename-btn" data-group="${_esc(g)}" style="background:rgba(99,102,241,0.15);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);padding:3px 10px;"><i class="fas fa-edit"></i> Rename</button>
                        <button class="btn btn-sm gm-move-btn" data-group="${_esc(g)}" style="background:rgba(34,197,94,0.12);color:#4ade80;border:1px solid rgba(34,197,94,0.25);padding:3px 10px;"><i class="fas fa-arrows-alt"></i> Move</button>
                        ${g !== 'default' ? `<button class="btn btn-sm gm-delete-btn" data-group="${_esc(g)}" style="background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.25);padding:3px 10px;"><i class="fas fa-trash"></i></button>` : ''}
                    </div>
                </div>
            `).join('');

            listEl.querySelectorAll('.gm-rename-btn').forEach(btn => btn.addEventListener('click', () => _openRenameGroup(btn.dataset.group)));
            listEl.querySelectorAll('.gm-move-btn').forEach(btn => btn.addEventListener('click', () => _openMoveGroup(btn.dataset.group)));
            listEl.querySelectorAll('.gm-delete-btn').forEach(btn => btn.addEventListener('click', () => _openDeleteGroup(btn.dataset.group)));
        } catch(e) {
            listEl.innerHTML = `<div style="color:#f87171;text-align:center;padding:20px;">Error: ${e.message}</div>`;
        }
    }

    function _openRenameGroup(group) {
        _groupManagerRenameTarget = group;
        const el = _$('renameGroupOldName'); if (el) el.textContent = group;
        const inp = _$('renameGroupNewInput'); if (inp) { inp.value = group; inp.focus(); inp.select(); }
        _$('renameGroupOverlay').style.display = 'flex';
    }
    function _closeRenameGroup() { _$('renameGroupOverlay').style.display = 'none'; }

    async function _confirmRenameGroup() {
        const newName = (_$('renameGroupNewInput') ? _$('renameGroupNewInput').value : '').trim();
        if (!newName) { App.toast('Enter new group name', 'warn'); return; }
        if (newName === _groupManagerRenameTarget) { _closeRenameGroup(); return; }
        try {
            const data = await _api('/api/profiles/groups/rename', {
                method: 'POST',
                body: JSON.stringify({ old_name: _groupManagerRenameTarget, new_name: newName })
            });
            if (data.success) {
                App.toast(`Renamed "${_groupManagerRenameTarget}" → "${newName}" (${data.updated} profiles)`, 'success');
                _closeRenameGroup(); _renderGroupManager(); loadProfiles(); _loadGroups();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    // Move all profiles from one group to another
    function _openMoveGroup(group) {
        _groupManagerDeleteTarget = group;
        const nameEl = _$('deleteGroupName'); if (nameEl) nameEl.textContent = group;
        const inp = _$('deleteGroupReassignInput'); if (inp) inp.value = 'default';
        // Reuse delete modal but with "Move" intent
        const confirmBtn = _$('deleteGroupConfirmBtn');
        if (confirmBtn) { confirmBtn.textContent = ''; confirmBtn.innerHTML = '<i class="fas fa-arrows-alt"></i> Move Profiles'; confirmBtn.className = 'btn btn-primary'; }
        const info = _$('deleteGroupOverlay').querySelector('[class*="info-circle"]');
        _$('deleteGroupOverlay').style.display = 'flex';
        _$('deleteGroupOverlay').dataset.mode = 'move';
    }

    function _openDeleteGroup(group) {
        _groupManagerDeleteTarget = group;
        const nameEl = _$('deleteGroupName'); if (nameEl) nameEl.textContent = group;
        const inp = _$('deleteGroupReassignInput'); if (inp) inp.value = 'default';
        const confirmBtn = _$('deleteGroupConfirmBtn');
        if (confirmBtn) { confirmBtn.innerHTML = '<i class="fas fa-trash"></i> Delete Group'; confirmBtn.className = 'btn btn-danger'; }
        _$('deleteGroupOverlay').style.display = 'flex';
        _$('deleteGroupOverlay').dataset.mode = 'delete';
    }
    function _closeDeleteGroup() { _$('deleteGroupOverlay').style.display = 'none'; }

    async function _confirmDeleteGroup() {
        const reassignTo = (_$('deleteGroupReassignInput') ? _$('deleteGroupReassignInput').value : 'default').trim() || 'default';
        const mode = _$('deleteGroupOverlay') ? _$('deleteGroupOverlay').dataset.mode : 'delete';
        try {
            const data = await _api(`/api/profiles/groups/${encodeURIComponent(_groupManagerDeleteTarget)}`, {
                method: 'DELETE',
                body: JSON.stringify({ reassign_to: reassignTo })
            });
            if (data.success) {
                App.toast(mode === 'move'
                    ? `Moved ${data.updated} profiles from "${_groupManagerDeleteTarget}" → "${reassignTo}"`
                    : `Deleted group "${_groupManagerDeleteTarget}", ${data.updated} profiles moved to "${reassignTo}"`, 'success');
                _closeDeleteGroup(); _renderGroupManager(); loadProfiles(); _loadGroups();
            } else App.toast(data.message || 'Failed', 'error');
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
    }

    async function _createGroup() {
        const name = (_$('newGroupNameInput') ? _$('newGroupNameInput').value : '').trim();
        if (!name) { App.toast('Enter group name', 'warn'); return; }
        // Groups exist implicitly when profiles are assigned — just refresh and show success
        App.toast(`Group "${name}" ready — assign profiles to it using the bulk toolbar`, 'success');
        if (_$('newGroupNameInput')) _$('newGroupNameInput').value = '';
        _loadGroups();
    }

    function _updateFilterCounts(counts) {
        // Accepts the server-side counts object from /api/profiles/counts:
        //   {all, logged_in, not_logged_in, login_failed, running, nst, nexus}
        // (Previously iterated the full profile array — too expensive at scale.)
        if (!counts || typeof counts !== 'object') return;
        const set = (id, n) => {
            const el = _$(id);
            if (el) el.textContent = (n == null ? 0 : n);
        };
        set('pmFilterAll', counts.all);
        set('pmFilterLoggedIn', counts.logged_in);
        set('pmFilterNotLoggedIn', counts.not_logged_in);
        set('pmFilterFailed', counts.login_failed);
        set('pmFilterRunning', counts.running);
        set('pmFilterNst', counts.nst);
    }

    // ══════════════════════════════════════════════════════════════════════
    // CONTEXT MENU
    // ══════════════════════════════════════════════════════════════════════

    function _showContextMenu(x, y) {
        const menu = _$('pmContextMenu');
        if (!menu) return;
        // Dynamic label for the Toggle Images quick-action — flips based on current state
        try {
            const p = _allProfiles.find(x => x.id === _contextProfileId);
            const blocked = !!(p && p.perf && p.perf.block_images);
            const lbl = menu.querySelector('[data-toggle-images-label]');
            if (lbl) lbl.textContent = blocked ? 'Turn Images ON' : 'Turn Images OFF (fast mode)';
        } catch (e) { /* ignore */ }
        menu.style.display = 'block';
        menu.style.left = Math.min(x, window.innerWidth - 220) + 'px';

        // Get actual menu height after rendering
        const menuHeight = menu.offsetHeight;
        const spaceBelow = window.innerHeight - y;

        // If not enough space below (< 40px padding), show above
        if (spaceBelow < menuHeight + 40) {
            menu.style.top = Math.max(10, y - menuHeight - 8) + 'px';
        } else {
            menu.style.top = y + 'px';
        }
    }

    function _hideContextMenu() {
        const menu = _$('pmContextMenu');
        if (menu) menu.style.display = 'none';
    }

    function _handleContextAction(action) {
        _hideContextMenu();
        if (!_contextProfileId) return;
        const id = _contextProfileId;
        switch (action) {
            case 'launch': launchProfile(id); break;
            case 'relogin': reloginProfile(id); break;
            case 'edit': openEditModal(id); break;
            case 'close': closeProfile(id); break;
            case 'delete': deleteProfile(id); break;
            case 'toggle-images': _toggleProfileImages(id); break;
            case 'clear-cache': clearProfileCache(id); break;
            case 'clear-cookies': clearProfileCookies(id); break;
            case 'change-device': changeDeviceType(id); break;
            case 'export': exportProfile(id); break;
            // Modify-* options just open the edit modal — the user picks
            // the tab they care about from there. Cheap and consistent.
            case 'modify-proxy':
            case 'modify-tag':
            case 'modify-note':
                openEditModal(id);
                break;
            default: App.toast('Action: ' + action, 'info');
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // CREATE / EDIT MODAL (4 Tabs)
    // ══════════════════════════════════════════════════════════════════════

    function openCreateModal() {
        _editingId = null;
        _$('profileModalTitle').textContent = 'Create Profile';
        _$('profileModalSaveText').textContent = 'Create Profile';
        _resetModal();
        _updateSummary();
        _$('profileModalOverlay').classList.add('active');
        // Fix: native confirm() dialog (from delete) can leave webview blurred.
        // Must refocus window first, then the input with a delay for Electron.
        window.focus();
        setTimeout(() => { window.focus(); const el = _$('pmName'); if (el) el.focus(); }, 150);
    }

    async function openEditModal(id) {
        try {
            const data = await _api(`/api/profiles/${id}`);
            if (!data.success) { App.toast('Failed to load profile', 'error'); return; }

            const p = data.profile;
            _editingId = id;
            _$('profileModalTitle').textContent = 'Edit Profile';
            _$('profileModalSaveText').textContent = 'Save Changes';

            // Overview tab
            _setVal('pmName', p.name || '');
            const profileGroups = (p.groups && p.groups.length) ? p.groups : [(p.group || 'default')];
            _pmGroupsState = [...profileGroups];
            _renderPmGroupTags();
            // Engine — always NST
            _setRadio('pmEngine', 'nst');
            const ov = p.overview || {};
            _setRadio('pmOS', ov.os || 'random');
            _setVal('pmStartupUrls', (ov.startup_urls || []).join(', '));
            const adv = p.advanced || {};
            const cbSaveTabs = _$('pmSaveTabs');
            if (cbSaveTabs) cbSaveTabs.checked = adv.save_tabs !== false; // default ON

            // Proxy tab
            const proxy = p.proxy || {};
            if (proxy.host) {
                const _ptype = (proxy.type === 'https') ? 'http' : (proxy.type || 'http');
                _setVal('pmProxyType', _ptype);
                _setVal('pmProxyHost', proxy.host || '');
                _setVal('pmProxyPort', proxy.port || '');
                _setVal('pmProxyUser', proxy.username || '');
                _setVal('pmProxyPass', proxy.password || '');
            } else if (proxy.server) {
                _setVal('pmProxyType', proxy.server.includes('socks5') ? 'socks5' : 'http');
                const cleaned = proxy.server.replace(/^(socks5|https?):\/\//, '');
                const parts = cleaned.split(':');
                _setVal('pmProxyHost', parts[0] || '');
                _setVal('pmProxyPort', parts[1] || '');
                _setVal('pmProxyUser', proxy.username || '');
                _setVal('pmProxyPass', proxy.password || '');
            } else {
                _setVal('pmProxyType', 'none');
            }
            _toggleProxyFields();

            // Credentials tab
            _setVal('pmEmail', p.email || '');
            _setVal('pmPassword', p.password || '');
            _setVal('pmTotp', p.totp_secret || '');
            _startPmTotp();
            _setVal('pmNotes', p.notes || '');
            _setVal('pmAddress', p.address || '');
            _setVal('pmRecoveryEmail', p.recovery_email || '');
            _setVal('pmRecoveryPhone', p.recovery_phone || '');
            _setVal('pmFirstName', p.first_name || '');
            _setVal('pmLastName', p.last_name || '');
            const codes = p.backup_codes || [];
            for (let i = 1; i <= 10; i++) _setVal('pmBC' + i, codes[i - 1] || '');

            // Bookmarks tab
            _setVal('pmBookmarksText', p.bookmarks_text || '');

            // Hardware (fingerprint) tab
            _loadFingerprintConfig(p.fingerprint_config);

            // Performance tab — load current perf flags (default all false except popups)
            const _perfDefaults = { block_images:false, block_autoplay:false, disable_hw_accel:false, block_notifications:false, block_popups:true };
            const _perfCur = Object.assign({}, _perfDefaults, p.perf || {});
            document.querySelectorAll('.pm-perf-toggle').forEach(cb => {
                const k = cb.dataset.perfKey;
                if (k in _perfCur) cb.checked = !!_perfCur[k];
            });

            _updateSummary();
            _$('profileModalOverlay').classList.add('active');
            setTimeout(() => { const el = _$('pmName'); if (el) { el.focus(); el.blur(); el.focus(); } }, 50);
        } catch (e) {
            App.toast('Error loading profile: ' + e.message, 'error');
        }
    }

    function _resetModal() {
        _setVal('pmName', '');
        _pmGroupsState = ['default'];
        _renderPmGroupTags();
        _setRadio('pmEngine', 'nst');
        _setRadio('pmOS', 'random');
        _setVal('pmStartupUrls', '');
        const cbST = _$('pmSaveTabs'); if (cbST) cbST.checked = true; // default ON
        _setVal('pmProxyType', 'none');
        _setVal('pmProxyHost', ''); _setVal('pmProxyPort', ''); _setVal('pmProxyUser', ''); _setVal('pmProxyPass', '');
        _setVal('pmProxyPaste', '');
        _toggleProxyFields();
        _setVal('pmEmail', ''); _setVal('pmPassword', ''); _setVal('pmTotp', ''); _setVal('pmNotes', ''); _setVal('pmAddress', '');
        _setVal('pmRecoveryEmail', ''); _setVal('pmRecoveryPhone', '');
        _setVal('pmFirstName', ''); _setVal('pmLastName', '');
        _setVal('pmBookmarksText', '');
        _stopPmTotp();
        for (let i = 1; i <= 10; i++) _setVal('pmBC' + i, '');
        _setVal('pmBCParser', '');
        // Performance tab — reset to defaults
        document.querySelectorAll('.pm-perf-toggle').forEach(cb => {
            const k = cb.dataset.perfKey;
            cb.checked = (k === 'block_popups');  // popups blocked by default
        });
        _switchTab('overview');
    }

    function _updateSummary() {
        const el = _$('pmSummary');
        if (!el) return;

        const os = _radio('pmOS') || 'random';
        const osLabel = _OS_LABELS[os] || os;
        const engine = 'nexus';
        const engInfo = _ENGINE_LABELS.nexus;
        const proxyType = _val('pmProxyType');
        const proxyHost = _val('pmProxyHost');
        const name = _val('pmName') || 'Auto';
        const email = _val('pmEmail');

        el.innerHTML = `
            <div class="pm-sum-section">
                <div class="pm-sum-title">Profile</div>
                <div class="pm-sum-row"><span class="pm-sum-key">Name</span><span class="pm-sum-val">${_esc(name)}</span></div>
                ${email ? `<div class="pm-sum-row"><span class="pm-sum-key">Email</span><span class="pm-sum-val">${_esc(email)}</span></div>` : ''}
                <div class="pm-sum-row"><span class="pm-sum-key">OS</span><span class="pm-sum-val">${_esc(osLabel)}</span></div>
                <div class="pm-sum-row"><span class="pm-sum-key">Engine</span><span class="pm-sum-val" style="color:${engInfo.color};">${engInfo.name}</span></div>
            </div>
            <div class="pm-sum-section">
                <div class="pm-sum-title">Proxy</div>
                <div class="pm-sum-row"><span class="pm-sum-key">Type</span><span class="pm-sum-val">${_esc(proxyType)}</span></div>
                ${proxyHost ? `<div class="pm-sum-row"><span class="pm-sum-key">Host</span><span class="pm-sum-val">${_esc(proxyHost)}</span></div>` : ''}
            </div>
            <div class="pm-sum-section">
                <div class="pm-sum-title">Fingerprint</div>
                <div class="pm-sum-row"><span class="pm-sum-key" style="color:${engInfo.color};">Auto</span><span class="pm-sum-val">Managed by ${engInfo.name}</span></div>
            </div>
        `;

        // Update engine info box
        const infoName = _$('pmEngineInfoName');
        if (infoName) infoName.textContent = engInfo.name;
    }

    function _switchTab(tabName) {
        document.querySelectorAll('.pm-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
        document.querySelectorAll('.pm-tab-content').forEach(c => c.classList.toggle('active', c.dataset.tabContent === tabName));
    }

    function _toggleProxyFields() {
        const type = _val('pmProxyType');
        const fields = _$('pmProxyFields');
        if (fields) fields.style.display = type === 'none' ? 'none' : 'block';
    }

    // ── Inline TOTP widget (credentials tab) ──────────────────────────────
    let _pmTotpInterval = null;

    async function _updatePmTotp() {
        const codeEl = _$('pmTotpCode');
        const barEl  = _$('pmTotpTimerBar');
        if (!codeEl) return;
        const secret = _val('pmTotp').trim();
        if (!secret || secret.length < 16) {
            codeEl.innerText = '------';
            if (barEl) barEl.style.width = '0%';
            return;
        }
        try {
            const code = await App._generateTOTP(secret);
            codeEl.innerText = code || 'INVALID';
        } catch { codeEl.innerText = 'ERROR'; }
        const remaining = 30 - (Math.floor(Date.now() / 1000) % 30);
        if (barEl) {
            barEl.style.width = ((remaining / 30) * 100) + '%';
            if (remaining <= 5) {
                barEl.style.background = '#ef4444';
                codeEl.style.color = '#ef4444';
            } else {
                barEl.style.background = 'var(--primary)';
                codeEl.style.color = 'var(--primary)';
            }
        }
    }

    function _startPmTotp() {
        _stopPmTotp();
        const secret = _val('pmTotp').trim();
        const widget = _$('pmTotpWidget');
        if (!widget) return;
        if (secret && secret.length >= 16) {
            widget.style.display = 'block';
            _updatePmTotp();
            _pmTotpInterval = setInterval(_updatePmTotp, 1000);
        } else {
            widget.style.display = 'none';
        }
    }

    function _stopPmTotp() {
        if (_pmTotpInterval) { clearInterval(_pmTotpInterval); _pmTotpInterval = null; }
        const widget = _$('pmTotpWidget');
        if (widget) widget.style.display = 'none';
        const codeEl = _$('pmTotpCode');
        if (codeEl) codeEl.innerText = '------';
        const barEl = _$('pmTotpTimerBar');
        if (barEl) barEl.style.width = '0%';
    }

    // ══════════════════════════════════════════════════════════════════════
    // FINGERPRINT CONFIG HELPERS
    // ══════════════════════════════════════════════════════════════════════

    function _readFingerprintConfig() {
        const _r = (name) => { const el = document.querySelector(`input[name="${name}"]:checked`); return el ? el.value : null; };
        const _v = (id) => { const el = document.getElementById(id); return el ? el.value : ''; };
        return {
            canvas_mode:           _r('fpCanvas')       || 'off',
            client_rects_mode:     _r('fpClientRects')  || 'off',
            audio_mode:            _r('fpAudio')        || 'noise',
            webgl_image_mode:      _r('fpWebGLImage')   || 'noise',
            webgl_meta_mode:       _r('fpWebGLMeta')    || 'custom',
            webgl_vendor:          _v('pmWebGLVendor')  || 'Intel Inc.',
            webgl_renderer:        _v('pmWebGLRenderer') || 'Intel(R) Iris(R) Xe Graphics',
            media_devices_mask:    _r('fpMediaMask') === 'true',
            video_inputs:          parseInt(_v('pmVideoInputs'))  || 0,
            audio_inputs:          parseInt(_v('pmAudioInputs'))  || 0,
            audio_outputs:         parseInt(_v('pmAudioOutputs')) || 0,
            fonts_mask:            _r('fpFonts')    === 'true',
            webgpu_mode:           _r('fpWebGPU')       || 'disabled',
            speech_mask:           _r('fpSpeech')   === 'true',
            dnt:                   _r('fpDNT')      === 'true',
            port_scan_protection:  _r('fpPortScan') === 'true',
            // System hardware
            screen_width:          parseInt((_v('pmScreenResolution') || '1366x768').split('x')[0]) || 1366,
            screen_height:         parseInt((_v('pmScreenResolution') || '1366x768').split('x')[1]) || 768,
            cpu_threads:           parseInt(_v('pmCpuThreads'))  || 4,
            ram_gb:                parseInt(_v('pmRamGb'))       || 4,
            locale:                _v('pmLocale') || 'en-US',
            // Location
            timezone:              _v('pmTimezone') || '',
            geolocation_permission:_r('fpGeoPermission') || 'prompt',
            geo_latitude:          parseFloat(_v('pmGeoLatitude'))  || null,
            geo_longitude:         parseFloat(_v('pmGeoLongitude')) || null,
        };
    }

    function _loadFingerprintConfig(fc) {
        if (!fc) fc = {};
        const _sr = (name, val) => {
            const el = document.querySelector(`input[name="${name}"][value="${val}"]`);
            if (el) el.checked = true;
        };
        const _sv = (id, val) => {
            const el = document.getElementById(id);
            if (el && val !== undefined && val !== null) el.value = val;
        };
        _sr('fpCanvas',      fc.canvas_mode        || 'off');
        _sr('fpClientRects', fc.client_rects_mode  || 'off');
        _sr('fpAudio',       fc.audio_mode         || 'noise');
        _sr('fpWebGLImage',  fc.webgl_image_mode   || 'noise');
        _sr('fpWebGLMeta',   fc.webgl_meta_mode    || 'custom');
        _sv('pmWebGLVendor',   fc.webgl_vendor     || 'Intel Inc.');
        _sv('pmWebGLRenderer', fc.webgl_renderer   || 'Intel(R) Iris(R) Xe Graphics');
        _sr('fpMediaMask',   fc.media_devices_mask === true ? 'true' : 'false');
        _sv('pmVideoInputs',  fc.video_inputs  ?? 0);
        _sv('pmAudioInputs',  fc.audio_inputs  ?? 0);
        _sv('pmAudioOutputs', fc.audio_outputs ?? 0);
        _sr('fpFonts',       fc.fonts_mask    !== false ? 'true' : 'false');
        _sr('fpWebGPU',      fc.webgpu_mode        || 'disabled');
        _sr('fpSpeech',      fc.speech_mask   !== false ? 'true' : 'false');
        _sr('fpDNT',         fc.dnt           !== false ? 'true' : 'false');
        _sr('fpPortScan',    fc.port_scan_protection !== false ? 'true' : 'false');
        // System hardware
        const sw = fc.screen_width  || 1366;
        const sh = fc.screen_height || 768;
        _sv('pmScreenResolution', `${sw}x${sh}`);
        _sv('pmCpuThreads', fc.cpu_threads || 4);
        _sv('pmRamGb',      fc.ram_gb      || 4);
        _sv('pmLocale',     fc.locale      || 'en-US');
        _sv('pmTimezone',   fc.timezone    || '');
        // Geolocation
        _sr('fpGeoPermission', fc.geolocation_permission || 'prompt');
        _sv('pmGeoLatitude',   fc.geo_latitude  ?? '');
        _sv('pmGeoLongitude',  fc.geo_longitude ?? '');
        const showGeo = (fc.geolocation_permission || 'prompt') === 'allow';
        document.querySelectorAll('.pm-geo-coords').forEach(el => {
            el.style.display = showGeo ? '' : 'none';
        });
        // Sync visibility of WebGL meta fields
        const show = (fc.webgl_meta_mode || 'custom') === 'custom';
        document.querySelectorAll('.pm-webgl-meta-fields').forEach(el => {
            el.style.display = show ? '' : 'none';
        });
    }

    // ══════════════════════════════════════════════════════════════════════
    // SAVE PROFILE
    // ══════════════════════════════════════════════════════════════════════

    async function saveProfile() {
        const btn = document.getElementById('profileModalSaveBtn');
        const origText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            btn.disabled = true;
        }

        const name = _val('pmName').trim() || `Profile ${Date.now().toString(36)}`;
        const email = _val('pmEmail').trim();

        // Build proxy
        const proxyType = _val('pmProxyType');
        let proxy = null;
        if (proxyType !== 'none') {
            const host = _val('pmProxyHost').trim();
            const port = _val('pmProxyPort').trim();
            if (host) {
                proxy = {
                    type: proxyType,
                    host: host,
                    port: parseInt(port) || 0,
                    username: _val('pmProxyUser').trim(),
                    password: _val('pmProxyPass').trim(),
                };
            }
        }

        // Backup codes
        const backup_codes = [];
        for (let i = 1; i <= 10; i++) {
            const v = _val('pmBC' + i).trim();
            if (v) backup_codes.push(v);
        }

        // Send OS + credentials with selected engine
        const os = _radio('pmOS') || 'random';
        const engine = 'nexus';
        const body = {
            name,
            email,
            proxy,
            engine,
            notes: _val('pmNotes').trim(),
            address: _val('pmAddress').trim(),
            password: _val('pmPassword').trim(),
            totp_secret: _val('pmTotp').trim(),
            backup_codes,
            recovery_email: _val('pmRecoveryEmail').trim(),
            recovery_phone: _val('pmRecoveryPhone').trim(),
            first_name: _val('pmFirstName').trim(),
            last_name: _val('pmLastName').trim(),
            fingerprint_prefs: { os_type: os },
            fingerprint_config: _readFingerprintConfig(),
            groups: _pmGroupsState.length ? _pmGroupsState : ['default'],
            group: _pmGroupsState[0] || 'default',
            overview: {
                os: os,
                browser_kernel: 'nstbrowser',
                startup_urls: _val('pmStartupUrls').split(',').map(s => s.trim()).filter(Boolean),
            },
            advanced: {
                save_tabs: _$('pmSaveTabs') ? _$('pmSaveTabs').checked : true,
            },
            bookmarks_text: (_val('pmBookmarksText') || '').trim(),
            perf: (() => {
                const p = {};
                document.querySelectorAll('.pm-perf-toggle').forEach(cb => {
                    if (cb.dataset.perfKey) p[cb.dataset.perfKey] = !!cb.checked;
                });
                return p;
            })(),
        };

        try {
            let data;
            if (_editingId) {
                data = await _api(`/api/profiles/${_editingId}`, { method: 'PUT', body: JSON.stringify(body) });
            } else {
                data = await _api('/api/profiles', { method: 'POST', body: JSON.stringify(body) });
            }
            if (data.success) {
                if (data.warning) {
                    App.toast('Profile created locally (NST limit reached)', 'info');
                } else {
                    App.toast(_editingId ? 'Profile updated' : 'Profile created', 'success');
                }
                closeModal();
                loadProfiles();
                _loadGroups();
            } else {
                App.toast(data.message || 'Save failed', 'error');
            }
        } catch (e) {
            App.toast('Error saving: ' + e.message, 'error');
        } finally {
            if (btn) {
                btn.innerHTML = origText;
                btn.disabled = false;
            }
        }
    }

    function closeModal() {
        _$('profileModalOverlay').classList.remove('active');
        _editingId = null;
        _stopPmTotp();
    }

    // ══════════════════════════════════════════════════════════════════════
    // DELETE / LAUNCH / CLOSE
    // ══════════════════════════════════════════════════════════════════════

    async function deleteProfile(id) {
        const ok = await _asyncConfirm('Delete this profile? This cannot be undone.');
        if (!ok) return;
        try {
            const data = await _api(`/api/profiles/${id}`, { method: 'DELETE' });
            if (data.success) { App.toast('Profile deleted', 'success'); loadProfiles(); }
            else App.toast('Delete failed', 'error');
        } catch (e) { App.toast('Delete error', 'error'); }
    }

    async function deleteSelectedProfiles() {
        if (!_selectedIds.size) { App.toast('No profiles selected', 'warn'); return; }
        const count = _selectedIds.size;
        const ok = await _asyncConfirm(`DELETE ${count} SELECTED PROFILE${count > 1 ? 'S' : ''}? This cannot be undone!`);
        if (!ok) return;
        try {
            const data = await _api('/api/profiles/delete-bulk', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: [..._selectedIds] })
            });
            if (data.success) {
                _selectedIds.clear();
                _updateBulkBar();
                _startOpProgress('delete');
            } else App.toast(data.message || 'Delete failed', 'error');
        } catch (e) { App.toast('Delete error', 'error'); }
    }

    async function reloginProfile(id) {
        const profile = _allProfiles.find(p => p.id === id);
        const email = profile?.email || 'this profile';
        if (!profile?.password) {
            App.toast('No saved password for this profile. Edit profile to add credentials.', 'error');
            return;
        }
        App.toast(`Re-login started for ${email}...`, 'info');
        try {
            const data = await _api(`/api/profiles/${id}/relogin`, { method: 'POST' });
            if (data.success) {
                App.toast(data.message || 'Re-login running...', 'success');
                // Keep polling for at least 90s so we catch the final
                // status flip even after the launch browser closes.
                _statusPollHoldUntil = Math.max(_statusPollHoldUntil, Date.now() + 90000);
                _startStatusPolling();
            } else {
                App.toast(data.error || 'Re-login failed', 'error');
            }
        } catch (e) { App.toast('Re-login error', 'error'); }
    }

    async function launchProfile(id) {
        try {
            App.toast('Launching browser...', 'info');
            _startStatusPolling();  // start polling immediately for launch state
            const data = await _api(`/api/profiles/${id}/launch`, { method: 'POST' });
            if (data.success) {
                App.toast('Browser launched', 'success');
            }
            else App.toast(data.error || 'Launch failed', 'error');
            await loadProfiles();
        } catch (e) { App.toast('Launch error', 'error'); }
    }

    async function closeProfile(id) {
        try {
            App.toast('Closing browser...', 'info');
            const data = await _api(`/api/profiles/${id}/close`, { method: 'POST' });
            App.toast('Browser closed', 'success');
            await loadProfiles();
            // Polling will auto-stop when no browsers are open
        } catch (e) { App.toast('Close error', 'error'); }
    }

    async function _toggleProfileImages(id) {
        try {
            const p = _allProfiles.find(x => x.id === id);
            const currentlyBlocked = !!(p && p.perf && p.perf.block_images);
            const next = !currentlyBlocked;
            const d = await _api(`/api/profiles/${id}/perf`, {
                method: 'POST',  // route also accepts PATCH but POST is universally proxied
                body: JSON.stringify({ perf: { block_images: next } }),
            });
            if (d && d.success) {
                // Update local cache so re-render reflects new state
                if (p) { p.perf = Object.assign({}, p.perf || {}, { block_images: next }); }
                App.toast(`Images ${next ? 'BLOCKED' : 'ALLOWED'} for this profile — applies on next launch`, 'success');
            } else {
                App.toast((d && d.message) || 'Toggle failed', 'error');
            }
        } catch (e) {
            App.toast('Error: ' + e.message, 'error');
        }
    }

    async function closeAllProfiles() {
        try {
            await _api('/api/profiles/close-all', { method: 'POST' });
            App.toast('All browsers closed', 'success');
            loadProfiles();
        } catch (e) { App.toast('Close all error', 'error'); }
    }

    async function clearProfileCache(id) {
        if (!confirm('Clear browser cache for this profile?\n\nThis removes Chrome\'s Cache / Code Cache / GPU cache folders. Cookies and login stay intact.')) return;
        try {
            const data = await _api(`/api/profiles/${encodeURIComponent(id)}/clear-cache`, { method: 'POST' });
            if (data.success) {
                App.toast(`Cache cleared — freed ${data.freed_mb || 0} MB`, 'success');
            } else {
                App.toast(data.message || 'Failed to clear cache', 'error');
            }
        } catch (e) {
            App.toast('Backend unreachable', 'error');
        }
    }

    async function clearProfileCookies(id) {
        if (!confirm('Clear cookies for this profile?\n\nProfile will be logged OUT of every site. You\'ll need to re-login.')) return;
        try {
            const data = await _api(`/api/profiles/${encodeURIComponent(id)}/clear-cookies`, { method: 'POST' });
            if (data.success) {
                App.toast(`Cookies cleared (${data.cleared} file${data.cleared === 1 ? '' : 's'})`, 'success');
                loadProfiles();
            } else {
                App.toast(data.message || 'Failed to clear cookies', 'error');
            }
        } catch (e) {
            App.toast('Backend unreachable', 'error');
        }
    }

    async function exportProfile(id) {
        try {
            const resp = await App.apiFetch('/api/profiles/export-excel', {
                method: 'POST',
                body: JSON.stringify({ ids: [id] }),
            });
            if (!resp.ok) {
                App.toast('Export failed: HTTP ' + resp.status, 'error');
                return;
            }
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const p = _allProfiles.find(x => x.id === id);
            const safe = ((p && (p.email || p.name)) || id).replace(/[^A-Za-z0-9._-]/g, '_');
            a.download = `profile_${safe}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            App.toast('Profile exported', 'success');
        } catch (e) {
            App.toast('Export error: ' + e.message, 'error');
        }
    }

    async function changeDeviceType(id) {
        const profiles = _allProfiles || await _api('/api/profiles');
        const profile = (profiles.profiles || profiles).find(p => p.id === id);
        if (!profile) { App.toast('Profile not found', 'error'); return; }

        const fp = profile.fingerprint || {};
        const currentOS = fp.os_type || 'windows';
        const choices = ['Windows', 'macOS', 'Linux', 'Android', 'iOS'];
        const values = ['windows', 'macos', 'linux', 'android', 'ios'];
        const osLabels = { windows: 'Desktop (Windows)', macos: 'Desktop (macOS)', linux: 'Desktop (Linux)', android: 'Mobile (Android)', ios: 'Mobile (iOS)' };

        const msg = `Current: ${osLabels[currentOS]}\n\nSelect new device type:`;
        const selected = await App.choose(msg, choices);
        if (!selected) return;

        const newOS = values[choices.indexOf(selected)];
        if (newOS === currentOS) { App.toast('Already ' + osLabels[currentOS], 'info'); return; }

        const btn = document.querySelector('[data-action="change-device"]');
        const orig = btn ? btn.innerHTML : '';
        if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true; }

        try {
            const result = await _api(`/api/profiles/${id}/change-device-type`, {
                method: 'POST',
                body: JSON.stringify({ os_type: newOS })
            });
            if (result.success) {
                const msg = result.browser_closed
                    ? `✓ Device type changed to ${osLabels[newOS]} (browser closed - reopen to apply)`
                    : `✓ Device type changed to ${osLabels[newOS]}`;
                App.toast(msg, 'success');
                closeModal();  // Close edit dialog to prevent overwrite with cached data
                await loadProfiles();  // Reload profiles to show updated data
            } else {
                App.toast(`Error: ${result.error || 'Failed to change device type'}`, 'error');
            }
        } catch (e) {
            App.toast('Error: ' + e.message, 'error');
        } finally {
            if (btn) { btn.innerHTML = orig; btn.disabled = false; }
        }
    }

    // ══════════════════════════════════════════════════════════════════════
    // BATCH OPERATIONS
    // ══════════════════════════════════════════════════════════════════════

    function openBatchLoginModal() {
        _$('batchLoginModalOverlay').classList.add('active');
        _loadGroups();
        // Clear any previous preview
        _setBatchPreview(null);
    }

    function closeBatchLoginModal() {
        _$('batchLoginModalOverlay').classList.remove('active');
    }

    // ── Live Status Check ─────────────────────────────────────────────────
    let _liveCheckSource = 'excel';   // 'excel' | 'sheet'
    let _selectedSheetId = '';
    let _selectedSheetName = '';

    function openLiveCheckModal() {
        const ov = _$('liveCheckModalOverlay');
        if (ov) ov.classList.add('active');
        _switchLiveCheckSource(_liveCheckSource);
        const fp = _val('liveCheckFilePath');
        if (fp && _liveCheckSource === 'excel') _previewLiveCheckFile();
    }

    function closeLiveCheckModal() {
        const ov = _$('liveCheckModalOverlay');
        if (ov) ov.classList.remove('active');
    }

    function _switchLiveCheckSource(src) {
        _liveCheckSource = src;
        const excel = _$('liveCheckSrcExcel'), sheet = _$('liveCheckSrcSheet');
        const eg = _$('liveCheckExcelGroup'), sg = _$('liveCheckSheetGroup');
        if (src === 'sheet') {
            if (excel) excel.style = 'flex:1;background:transparent;color:#94a3b8;';
            if (sheet) sheet.style = 'flex:1;background:rgba(99,102,241,0.25);';
            if (eg) eg.style.display = 'none';
            if (sg) sg.style.display = 'block';
            _refreshSheetAuth();
        } else {
            if (excel) excel.style = 'flex:1;background:rgba(99,102,241,0.25);';
            if (sheet) sheet.style = 'flex:1;background:transparent;color:#94a3b8;';
            if (eg) eg.style.display = 'block';
            if (sg) sg.style.display = 'none';
            const prev = _$('liveCheckPreview');
            if (prev) prev.style.display = 'none';
        }
    }

    async function _refreshSheetAuth() {
        try {
            const r = await App.apiFetch('/api/sheets/status');
            const s = await r.json();
            const auth = _$('liveCheckSheetAuth');
            const picker = _$('liveCheckSheetPicker');
            if (s.configured) {
                if (auth) auth.style.display = 'none';
                if (picker) picker.style.display = 'block';
                _loadSheetList();
            } else {
                if (auth) auth.style.display = 'block';
                if (picker) picker.style.display = 'none';
            }
        } catch (e) { /* ignore */ }
    }

    async function _doSheetAuthorize() {
        const btn = _$('liveCheckSheetAuthBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting for browser…'; }
        App.toast('A browser tab will open — log in and grant access', 'info');
        try {
            const r = await App.apiFetch('/api/sheets/authorize', { method: 'POST' });
            const d = await r.json();
            if (d.success) {
                App.toast('Google Sheets connected ✓', 'success');
                await _refreshSheetAuth();
            } else {
                App.toast(d.message || 'Authorization failed', 'error');
            }
        } catch (e) {
            App.toast('Auth error: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-key"></i> Connect Google Sheets'; }
        }
    }

    let _sheetSearchTimer = null;
    async function _loadSheetList() {
        const list = _$('liveCheckSheetList');
        if (!list) return;
        const q = (_val('liveCheckSheetSearch') || '').trim();
        list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';
        try {
            const url = '/api/sheets/list' + (q ? `?q=${encodeURIComponent(q)}` : '');
            const r = await App.apiFetch(url);
            const d = await r.json();
            if (!d.success) {
                list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${d.message}</div>`;
                return;
            }
            const sheets = d.sheets || [];
            if (!sheets.length) {
                list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;">No spreadsheets found.</div>';
                return;
            }
            list.innerHTML = sheets.map(s => {
                const mod = s.modified ? new Date(s.modified).toLocaleDateString() : '';
                const isSel = s.id === _selectedSheetId ? 'background:rgba(99,102,241,0.18);' : '';
                return `<div class="sheet-row" data-id="${s.id}" data-name="${(s.name||'').replace(/"/g,'&quot;')}"
                            style="padding:8px 10px;border-bottom:1px solid #1e293b;cursor:pointer;${isSel}">
                    <div style="font-size:13px;color:#e2e8f0;">${s.name || '(unnamed)'}</div>
                    <div style="font-size:11px;color:#64748b;">Modified ${mod} · ${s.owner || ''}</div>
                </div>`;
            }).join('');
            list.querySelectorAll('.sheet-row').forEach(el => {
                el.addEventListener('click', () => _onSheetPicked(
                    el.getAttribute('data-id'),
                    el.getAttribute('data-name'),
                ));
            });
        } catch (e) {
            list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${e.message}</div>`;
        }
    }

    // ── Live Check: selected tabs (checkbox-based) ────────────────────
    let _liveCheckSelectedTabs = new Set();

    function _updateLiveCheckTabCount() {
        const el = _$('liveCheckTabCount');
        if (el) el.textContent = `${_liveCheckSelectedTabs.size} selected`;
    }

    async function _onSheetPicked(id, name) {
        _selectedSheetId = id;
        _selectedSheetName = name || '';
        _liveCheckSelectedTabs.clear();
        // Highlight in list
        document.querySelectorAll('#liveCheckSheetList .sheet-row').forEach(el => {
            el.style.background = el.getAttribute('data-id') === id
                ? 'rgba(99,102,241,0.18)' : 'transparent';
        });
        // Load tabs
        const tabGroup = _$('liveCheckTabGroup');
        const tabList = _$('liveCheckTabList');
        const prev = _$('liveCheckPreview');
        if (tabGroup) tabGroup.style.display = 'block';
        if (tabList) {
            tabList.innerHTML = '<div style="padding:10px 14px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading tabs…</div>';
        }
        _updateLiveCheckTabCount();
        try {
            const r = await App.apiFetch(`/api/sheets/${encodeURIComponent(id)}/tabs`);
            const d = await r.json();
            if (!d.success) {
                if (tabList) {
                    tabList.innerHTML = '<div style="padding:10px 14px;color:#fca5a5;font-size:12px;"><i class="fas fa-times-circle"></i> ' +
                        `Could not list tabs: ${d.message || 'unknown error'}</div>`;
                }
                if (prev) {
                    prev.style.display = 'block';
                    prev.innerHTML = `<i class="fas fa-times-circle" style="color:#ef4444;"></i> ` +
                        `Could not list tabs: ${d.message || 'unknown error'}`;
                }
                return;
            }
            const tabs = d.tabs || [];
            if (tabList) {
                if (tabs.length === 0) {
                    tabList.innerHTML = '<div style="padding:10px 14px;text-align:center;color:#64748b;font-size:12px;">No tabs found.</div>';
                } else {
                    tabList.innerHTML = tabs.map(t => {
                        const eName = (t.title || '').replace(/"/g, '&quot;');
                        return `<label class="lc-tab-row" style="display:flex;align-items:center;gap:8px;padding:6px 10px;cursor:pointer;border-bottom:1px solid #1e293b;font-size:12px;color:#e2e8f0;" data-tab="${eName}">
                            <input type="checkbox" class="lc-tab-cb" value="${eName}" style="accent-color:#6366f1;">
                            <span style="flex:1;">${t.title || '(unnamed)'}</span>
                            <span class="lc-tab-count" style="font-size:11px;color:#64748b;"></span>
                        </label>`;
                    }).join('');

                    // Bind checkbox events
                    tabList.querySelectorAll('.lc-tab-cb').forEach(cb => {
                        cb.addEventListener('change', () => {
                            if (cb.checked) _liveCheckSelectedTabs.add(cb.value);
                            else _liveCheckSelectedTabs.delete(cb.value);
                            _updateLiveCheckTabCount();
                            _previewLiveCheckSheetBatch();
                        });
                    });

                    // Auto-select all tabs and preview
                    tabList.querySelectorAll('.lc-tab-cb').forEach(cb => {
                        cb.checked = true;
                        _liveCheckSelectedTabs.add(cb.value);
                    });
                    _updateLiveCheckTabCount();
                    _previewLiveCheckSheetBatch();
                }
            }
        } catch (e) {
            App.toast('Could not load tabs: ' + e.message, 'error');
            if (tabList) {
                tabList.innerHTML = `<div style="padding:10px 14px;color:#fca5a5;font-size:12px;"><i class="fas fa-times-circle"></i> ${e.message}</div>`;
            }
            if (prev) {
                prev.style.display = 'block';
                prev.innerHTML = `<i class="fas fa-times-circle" style="color:#ef4444;"></i> ${e.message}`;
            }
        }
    }

    function _liveCheckToggleAllTabs(selectAll) {
        const tabList = _$('liveCheckTabList');
        if (!tabList) return;
        _liveCheckSelectedTabs.clear();
        tabList.querySelectorAll('.lc-tab-cb').forEach(cb => {
            cb.checked = selectAll;
            if (selectAll) _liveCheckSelectedTabs.add(cb.value);
        });
        _updateLiveCheckTabCount();
        _previewLiveCheckSheetBatch();
    }

    // Cache of the most recent /preview-batch response so the status
    // filter chips can recompute "matching rows" locally without firing
    // another Sheets API round-trip on every chip toggle.
    let _liveCheckPreviewCache = null;   // { tabs: [...], totalLinks, selectedTabs }

    async function _previewLiveCheckSheetBatch() {
        const id = _selectedSheetId;
        const selectedTabs = [..._liveCheckSelectedTabs];
        const prev = _$('liveCheckPreview');
        if (!prev) return;
        if (!id || selectedTabs.length === 0) {
            prev.style.display = 'none';
            _liveCheckPreviewCache = null;
            return;
        }
        prev.style.display = 'block';
        prev.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Reading selected tabs…';
        try {
            const r = await App.apiFetch(`/api/sheets/${encodeURIComponent(id)}/preview-batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tabs: selectedTabs }),
            });
            const d = await r.json();
            if (d.success) {
                // Build per-tab lookup from the array response
                const tabsArr = d.tabs || [];
                const perTab = {};
                let totalLinks = 0;
                for (const t of tabsArr) {
                    if (t.success) {
                        perTab[t.tab] = t.link_count || 0;
                        totalLinks += t.link_count || 0;
                    }
                }
                // Update per-tab counts in the checkbox list
                document.querySelectorAll('#liveCheckTabList .lc-tab-row').forEach(row => {
                    const tabName = row.getAttribute('data-tab');
                    const countEl = row.querySelector('.lc-tab-count');
                    if (countEl && perTab[tabName] != null) {
                        countEl.textContent = `${perTab[tabName]} links`;
                        countEl.style.color = perTab[tabName] > 0 ? '#22c55e' : '#64748b';
                    }
                });
                _liveCheckPreviewCache = {
                    tabs: tabsArr,
                    totalLinks,
                    selectedTabs,
                };
                _renderLiveCheckPreviewText();
            } else {
                _liveCheckPreviewCache = null;
                prev.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:#f59e0b;"></i> ${d.message || 'Could not read sheet'}`;
            }
        } catch (e) {
            _liveCheckPreviewCache = null;
            prev.innerHTML = `<i class="fas fa-times-circle" style="color:#ef4444;"></i> ${e.message}`;
        }
    }

    // Status filter synonym map — MUST stay in sync with the backend
    // _STATUS_SYNONYMS in shared/live_status_check.py so the preview
    // count never disagrees with the actual run count.
    const _LC_STATUS_SYNONYMS = {
        live:     ['live'],
        appealed: ['appeal', 'appealed', 'applead', 'applied'],
        done:     ['done'],
        missing:  ['missing'],
        disabled: ['disabled', 'disable'],
    };

    // Compute the "filtered row count" from the cached preview using
    // the status chips the user currently has active. No API call — pure
    // arithmetic on the per-tab status_counts dict the backend returned.
    function _renderLiveCheckPreviewText() {
        const prev = _$('liveCheckPreview');
        const cache = _liveCheckPreviewCache;
        if (!prev || !cache) return;
        const selectedFilter = _getLiveCheckStatusFilter();  // [] = All
        const tabCount = cache.selectedTabs.length;
        const tabLabel = `<b>${tabCount}</b> tab${tabCount === 1 ? '' : 's'}`;

        if (selectedFilter.length === 0) {
            // No filter → original "X unique Review Live Links" text.
            prev.innerHTML =
                `<i class="fas fa-check-circle" style="color:#22c55e;"></i> ` +
                `<b>${_selectedSheetName}</b> — ` +
                `<b style="color:#22c55e;">${cache.totalLinks}</b> unique Review Live Link${cache.totalLinks === 1 ? '' : 's'} across ${tabLabel}`;
            return;
        }

        // Filter active — sum up rows matching the chosen statuses across
        // tabs. Uses the same synonym map as the backend so e.g. Appealed
        // also matches Applead/Applied legacy spellings.
        const allow = new Set();
        for (const s of selectedFilter) {
            (_LC_STATUS_SYNONYMS[s] || [s]).forEach(v => allow.add(v));
        }
        let matched = 0;
        let tabsMissingStatusCol = 0;
        let tabsWithStatusCol = 0;
        for (const t of cache.tabs) {
            if (!t.success) continue;
            if (t.status_col_found) {
                tabsWithStatusCol += 1;
                const sc = t.status_counts || {};
                for (const k of Object.keys(sc)) {
                    if (allow.has(k)) matched += sc[k];
                }
            } else {
                tabsMissingStatusCol += 1;
            }
        }

        const labels = selectedFilter.map(s => s.charAt(0).toUpperCase() + s.slice(1)).join(' + ');
        let html =
            `<i class="fas fa-filter" style="color:#a5b4fc;"></i> ` +
            `<b>${_selectedSheetName}</b> — filtering by <b style="color:#a5b4fc;">${labels}</b>: ` +
            `<b style="color:#22c55e;">${matched}</b> row${matched === 1 ? '' : 's'} across ${tabLabel}`;
        if (tabsMissingStatusCol > 0) {
            html += `<div style="margin-top:6px;color:#f59e0b;font-size:11px;">` +
                    `<i class="fas fa-exclamation-triangle"></i> ` +
                    `${tabsMissingStatusCol} of ${tabsMissingStatusCol + tabsWithStatusCol} tab(s) ` +
                    `don't have a "Status" column — those rows can't be filtered and won't be checked.` +
                    `</div>`;
        }
        prev.innerHTML = html;
    }

    async function _previewLiveCheckFile() {
        const filePath = (_val('liveCheckFilePath') || '').trim();
        const prev = _$('liveCheckPreview');
        if (!prev) return;
        if (!filePath) { prev.style.display = 'none'; return; }
        prev.style.display = 'block';
        prev.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Reading file…';
        try {
            const r = await App.apiFetch('/api/profiles/live-check/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath }),
            });
            const d = await r.json();
            if (d.success) {
                const uniq = d.unique_links != null ? d.unique_links : d.total_links;
                prev.innerHTML =
                    `<i class="fas fa-check-circle" style="color:#22c55e;"></i> ` +
                    `<b>${d.file_name}</b> — ` +
                    `<b style="color:#22c55e;">${uniq}</b> Review Live Link${uniq===1?'':'s'} to check`;
            } else {
                prev.innerHTML =
                    `<i class="fas fa-exclamation-triangle" style="color:#f59e0b;"></i> ` +
                    `${d.message || 'Could not read file'}`;
            }
        } catch (e) {
            prev.innerHTML = `<i class="fas fa-times-circle" style="color:#ef4444;"></i> ${e.message}`;
        }
    }

    // Status filter chips — read which Status values the user wants to
    // re-check. Empty list (or 'all' active) means "every row". Specific
    // chips like 'live' / 'appealed' / 'done' / 'missing' / 'disabled'
    // narrow the run to rows whose Status column already holds that value.
    function _getLiveCheckStatusFilter() {
        const box = _$('liveCheckStatusChips');
        if (!box) return [];
        const active = Array.from(box.querySelectorAll('.lc-status-chip.active'))
            .map(b => b.dataset.status);
        if (active.length === 0 || active.includes('all')) return [];
        return active;
    }

    async function startLiveCheck() {
        const workers  = parseInt(_val('liveCheckWorkers'))  || 5;
        const timeout  = parseInt(_val('liveCheckTimeout'))  || 20;
        const showBrowser = !!(document.getElementById('liveCheckShowBrowser') && document.getElementById('liveCheckShowBrowser').checked);
        const startBtn = _$('liveCheckStartBtn');

        // Build payload based on selected source
        const statusFilter = _getLiveCheckStatusFilter();
        let payload = {
            workers,
            timeout_sec: timeout,
            show_browser: showBrowser,
            status_filter: statusFilter,
        };
        if (_liveCheckSource === 'sheet') {
            const selectedTabs = [..._liveCheckSelectedTabs];
            if (!_selectedSheetId || selectedTabs.length === 0) {
                App.toast('Pick a Google Sheet and select at least one tab', 'error');
                return;
            }
            payload.sheet_id = _selectedSheetId;
            payload.tabs = selectedTabs;
        } else {
            const filePath = (_val('liveCheckFilePath') || '').trim();
            if (!filePath) { App.toast('Pick an Excel file first', 'error'); return; }
            payload.file_path = filePath;
        }

        if (startBtn) { startBtn.disabled = true; startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting…'; }
        try {
            const r = await App.apiFetch('/api/profiles/live-check/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            if (!d.success) {
                App.toast(d.message || 'Could not start', 'error');
                return;
            }
            App.toast('Live status check started', 'success');
            // Close modal + show the SAME bottom-left progress panel that
            // every other op uses (Run Ops, Appeal, Health, etc.).
            closeLiveCheckModal();
            _startOpProgress('live-check');
        } catch (e) {
            App.toast('Error: ' + e.message, 'error');
        } finally {
            if (startBtn) { startBtn.disabled = false; startBtn.innerHTML = '<i class="fas fa-play"></i> Start'; }
        }
    }

    function _setBatchPreview(info) {
        const el = _$('batchLoginPreview');
        if (!el) return;
        if (!info) { el.style.display = 'none'; return; }
        if (!info.success) {
            el.style.display = 'flex';
            el.innerHTML = `<span style="color:#f87171;"><i class="fas fa-exclamation-circle"></i> ${_esc(info.message || 'Could not read file')}</span>`;
            return;
        }
        el.style.display = 'flex';
        el.innerHTML = `
            <span style="color:#4ade80;"><i class="fas fa-file-excel"></i> <strong>${info.valid}</strong> valid accounts</span>
            ${(info.skipped > 0) ? `<span style="color:#f59e0b;font-size:11px;">· ${info.skipped} already exist (will be skipped) · <strong>${info.valid - info.skipped}</strong> new</span>` : ''}
            ${info.valid !== info.total ? `<span style="color:#64748b;font-size:11px;">(${info.total} total rows, ${info.total - info.valid} invalid)</span>` : ''}
            <span style="color:#64748b;font-size:11px;">${info.columns && info.columns.includes('Proxy') ? '· Proxy column detected' : ''}</span>
        `;
    }

    let _batchPreviewTimer = null;
    async function _previewBatchFile() {
        const filePath = _val('batchLoginFilePath').trim();
        if (!filePath) { _setBatchPreview(null); return; }
        if (_batchPreviewTimer) clearTimeout(_batchPreviewTimer);
        _batchPreviewTimer = setTimeout(async () => {
            try {
                const data = await _api('/api/profiles/batch-login-preview', {
                    method: 'POST', body: JSON.stringify({ file_path: filePath })
                });
                _setBatchPreview(data);
            } catch(e) { _setBatchPreview({ success: false, message: e.message }); }
        }, 400);
    }

    async function startBatchLogin() {
        const filePath = _val('batchLoginFilePath').trim();
        const workers = parseInt(_val('batchLoginWorkers')) || 3;
        const staggerDelay = parseInt(_val('batchLoginStagger')) || 3;
        const engine = 'nexus';
        const osRadio = document.querySelector('input[name="batchOs"]:checked');
        const osType = osRadio ? osRadio.value : 'random';
        const group = (_val('batchLoginGroup') || 'default').trim() || 'default';
        if (!filePath) { App.toast('Select an Excel file first', 'error'); return; }

        // Collect Fast Mode perf toggles — only checked keys are sent, so unchecked
        // keys stay at their per-profile defaults (block_popups defaults to true).
        const perf = {};
        document.querySelectorAll('.bl-perf-toggle:checked').forEach(cb => {
            if (cb.dataset.perfKey) perf[cb.dataset.perfKey] = true;
        });

        try {
            const data = await _api('/api/profiles/batch-login', {
                method: 'POST',
                body: JSON.stringify({
                    file_path: filePath, workers, engine, os_type: osType, group,
                    stagger_delay: staggerDelay,
                    perf: Object.keys(perf).length ? perf : undefined,
                })
            });
            if (data.success) {
                const perfNote = Object.keys(perf).length ? ` · Fast Mode: ${Object.keys(perf).length} setting(s)` : '';
                App.toast(`Batch login started: ${data.total} accounts — group: ${group}${perfNote}`, 'success');
                closeBatchLoginModal();
                _startOpProgress('batch-login');
                _startStatusPolling();
                _loadGroups();
            } else App.toast(data.message || 'Batch login failed', 'error');
        } catch (e) { App.toast('Batch login error: ' + e.message, 'error'); }
    }

    // ══════════════════════════════════════════════════════════════════════
    // RUN OPS MODAL
    // ══════════════════════════════════════════════════════════════════════
    let _runOpsProfiles = [];
    const _runOpsChecked = new Set();
    let _runOpsSearch = '';
    let _runOpsPage = 1;
    let _runOpsGroupFilter = '';
    const _RUNOPS_PAGE_SIZE = 15;

    function openRunOpsModal() {
        const modal = document.getElementById('runOpsModal');
        if (!modal) return;
        // Pre-select from bulk selection
        _runOpsChecked.clear();
        _selectedIds.forEach(id => _runOpsChecked.add(id));
        // Load profiles
        _api('/api/profiles?per_page=10000&slim=1').then(data => {
            _runOpsProfiles = data.profiles || [];
            // If no bulk selection, select all
            if (!_runOpsChecked.size) _runOpsProfiles.forEach(p => _runOpsChecked.add(p.id));
            _runOpsPage = 1;
            const totalEl = document.getElementById('runOpsTotalCount');
            if (totalEl) totalEl.textContent = String(_runOpsProfiles.length);
            _renderRunOpsProfiles();
            _updateRunOpsCount();
            // Populate group filter
            const gf = document.getElementById('runOpsGroupFilter');
            if (gf) {
                const groups = [...new Set(_runOpsProfiles.flatMap(p => (p.groups && p.groups.length) ? p.groups : [p.group || 'default']))].sort();
                gf.innerHTML = '<option value="">All Groups</option>' + groups.map(g => `<option value="${g}">${g}</option>`).join('');
            }
        });
        // Reset ops checkboxes
        modal.querySelectorAll('.runops-op').forEach(cb => { cb.checked = false; });
        _updateRunOpsParams();
        // Pre-fill Recovery Email/Phone from first selected profile (if any)
        setTimeout(() => {
            const firstId = [..._runOpsChecked][0];
            const firstProfile = _runOpsProfiles.find(p => p.id === firstId);
            if (firstProfile) {
                const reEl = document.getElementById('runOpsRecoveryEmail');
                const rpEl = document.getElementById('runOpsRecoveryPhone');
                if (reEl && !reEl.value) reEl.value = firstProfile.recovery_email || '';
                if (rpEl && !rpEl.value) rpEl.value = firstProfile.recovery_phone || '';
            }
        }, 250);
        modal.style.display = 'flex';
    }

    function _closeRunOpsModal() {
        const modal = document.getElementById('runOpsModal');
        if (modal) modal.style.display = 'none';
    }

    function _filteredRunOpsProfiles() {
        let list = _runOpsProfiles;
        const q = _runOpsSearch.trim().toLowerCase();
        if (q) list = list.filter(p => (p.email || '').toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q));
        if (_runOpsGroupFilter) list = list.filter(p => {
            const gs = (p.groups && p.groups.length) ? p.groups : [p.group || 'default'];
            return gs.some(g => g.toLowerCase() === _runOpsGroupFilter.toLowerCase());
        });
        return list;
    }

    function _renderRunOpsProfiles() {
        const container = document.getElementById('runOpsProfileList');
        if (!container) return;
        const filtered = _filteredRunOpsProfiles();
        const totalPages = Math.max(1, Math.ceil(filtered.length / _RUNOPS_PAGE_SIZE));
        _runOpsPage = Math.min(_runOpsPage, totalPages);
        const start = (_runOpsPage - 1) * _RUNOPS_PAGE_SIZE;
        const page = filtered.slice(start, start + _RUNOPS_PAGE_SIZE);

        let html = page.map(p => {
            const checked = _runOpsChecked.has(p.id) ? 'checked' : '';
            const statusCls = p.status === 'logged_in' ? 'color:#22c55e' : p.status === 'login_failed' ? 'color:#ef4444' : 'color:#64748b';
            return `<label class="runops-profile-row">
                <input type="checkbox" data-id="${p.id}" ${checked}>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(p.name || 'Unnamed')}</div>
                    <div style="font-size:10px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(p.email || '')}</div>
                </div>
                <span style="font-size:10px;${statusCls};">${p.status === 'logged_in' ? '✓' : p.status === 'login_failed' ? '✗' : '—'}</span>
            </label>`;
        }).join('');

        // Pagination
        if (totalPages > 1) {
            html += '<div class="modal-pg-bar">';
            if (_runOpsPage > 1) html += `<button class="modal-pg-btn" data-pg="${_runOpsPage - 1}">‹</button>`;
            for (let i = 1; i <= totalPages; i++) {
                html += `<button class="modal-pg-btn ${i === _runOpsPage ? 'active' : ''}" data-pg="${i}">${i}</button>`;
            }
            if (_runOpsPage < totalPages) html += `<button class="modal-pg-btn" data-pg="${_runOpsPage + 1}">›</button>`;
            html += '</div>';
        }
        container.innerHTML = html;

        // Bind checkbox events
        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                if (cb.checked) _runOpsChecked.add(cb.dataset.id);
                else _runOpsChecked.delete(cb.dataset.id);
                _updateRunOpsCount(); _updateNameMapping();
            });
        });
        // Bind pagination
        container.querySelectorAll('.modal-pg-btn').forEach(btn => {
            btn.addEventListener('click', () => { _runOpsPage = parseInt(btn.dataset.pg); _renderRunOpsProfiles(); });
        });
    }

    function _updateRunOpsCount() {
        const el = document.getElementById('runOpsSelectedCount');
        if (el) el.textContent = _runOpsChecked.size;
    }

    function _updateRunOpsParams() {
        const checked = document.querySelectorAll('.runops-op:checked');
        const ops = new Set([...checked].map(cb => cb.value));

        // Param visibility (security tab + identity tab)
        const show = (id, on) => { const el = document.getElementById(id); if (el) el.style.display = on ? '' : 'none'; };
        show('runOpsParamRecoveryPhone', ops.has('2a'));
        show('runOpsParamRecoveryEmail', ops.has('3a'));
        show('runOpsParamNames', ops.has('8'));

        // Footer chip summary
        const summary = document.getElementById('runOpsOpSummary');
        if (summary) {
            if (!ops.size) {
                summary.innerHTML = '<span style="font-size:11px;color:#64748b;font-style:italic;">no operations</span>';
            } else {
                summary.innerHTML = [...ops].map(op => `<span class="runops-op-chip">${op}</span>`).join('');
            }
        }

        // Per-tab badges
        const tabCounts = { language: 0, security: 0, reviews: 0, identity: 0 };
        checked.forEach(cb => {
            const t = cb.dataset.tab;
            if (t in tabCounts) tabCounts[t]++;
        });
        Object.entries(tabCounts).forEach(([t, n]) => {
            const badge = document.querySelector(`#runOpsTabRail .runops-tab-badge[data-badge="${t}"]`);
            if (badge) {
                badge.style.display = n > 0 ? '' : 'none';
                badge.textContent = String(n);
            }
        });

        // Identity tab — also refresh the mapping preview when toggled
        if (typeof _updateNameMapping === 'function') _updateNameMapping();
    }

    function _updateNameMapping() {
        const op8 = document.getElementById('runOpsOp8');
        if (!op8 || !op8.checked) return;

        const ta = document.getElementById('runOpsNameList');
        const counter = document.getElementById('runOpsNameCounter');
        const mismatch = document.getElementById('runOpsNameMismatch');
        const table = document.getElementById('runOpsNameMapping');
        if (!ta || !counter || !mismatch || !table) return;

        const names = ta.value.split('\n').map(l => l.trim()).filter(Boolean);
        const filtered = _filteredRunOpsProfiles();
        const selected = filtered.filter(p => _runOpsChecked.has(p.id));
        const n = Math.min(names.length, selected.length);

        counter.textContent = `${names.length} name${names.length === 1 ? '' : 's'} · ${selected.length} profile${selected.length === 1 ? '' : 's'}`;

        if (names.length === 0 || selected.length === 0) {
            mismatch.style.display = 'none';
            table.innerHTML = '<div style="padding:8px;color:#64748b;font-style:italic;">Add names and select profiles to preview the mapping.</div>';
            return;
        }

        if (names.length < selected.length) {
            const otherOps = [...document.querySelectorAll('.runops-op:checked')].map(cb => cb.value).filter(v => v !== '8');
            const extra = otherOps.length
                ? ` (other ops in this run — ${otherOps.join(', ')} — will also be limited to those ${n} profiles)`
                : '';
            mismatch.style.display = '';
            mismatch.textContent = `Will run on ${n}/${selected.length} — last ${selected.length - n} profile${selected.length - n === 1 ? '' : 's'} skipped${extra}.`;
        } else if (names.length > selected.length) {
            mismatch.style.display = '';
            mismatch.textContent = `${names.length - selected.length} extra name${names.length - selected.length === 1 ? '' : 's'} unused (only ${selected.length} profile${selected.length === 1 ? '' : 's'} selected).`;
        } else {
            mismatch.style.display = 'none';
        }

        const rows = [];
        for (let i = 0; i < selected.length; i++) {
            const p = selected[i];
            const email = p.email || p.name || p.id;
            if (i < n) {
                const name = names[i].replace(/</g, '&lt;');
                rows.push(`<div class="runops-map-row"><span class="idx">${i + 1}.</span><span class="email">${email}</span><span class="arrow">→</span><span class="name">${name}</span></div>`);
            } else {
                rows.push(`<div class="runops-map-row skip"><span class="idx">${i + 1}.</span><span class="email">${email}</span><span class="arrow">→</span><span class="name">SKIP</span></div>`);
            }
        }
        table.innerHTML = rows.join('');
    }

    function _setupRunOpsModal() {
        // Close buttons
        _btn('runOpsModalClose', _closeRunOpsModal);
        _btn('runOpsModalCancelBtn', _closeRunOpsModal);

        // Vertical tab rail — toggle panel visibility
        document.querySelectorAll('#runOpsTabRail .runops-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                document.querySelectorAll('#runOpsTabRail .runops-tab').forEach(t => {
                    t.classList.toggle('active', t === tab);
                });
                document.querySelectorAll('.runops-tab-panel').forEach(panel => {
                    const match = panel.dataset.panel === target;
                    panel.classList.toggle('active', match);
                    panel.style.display = match ? '' : 'none';
                });
            });
        });

        // Op checkboxes → toggle param fields
        document.querySelectorAll('.runops-op').forEach(cb => {
            cb.addEventListener('change', _updateRunOpsParams);
        });

        // Search
        const searchEl = document.getElementById('runOpsSearchInput');
        if (searchEl) searchEl.addEventListener('input', () => {
            _runOpsSearch = searchEl.value; _runOpsPage = 1; _renderRunOpsProfiles(); _updateNameMapping();
        });

        // Group filter
        const gfEl = document.getElementById('runOpsGroupFilter');
        if (gfEl) gfEl.addEventListener('change', () => {
            _runOpsGroupFilter = gfEl.value; _runOpsPage = 1; _renderRunOpsProfiles(); _updateNameMapping();
        });

        // Select All / None
        _btn('runOpsSelectAll', () => {
            _filteredRunOpsProfiles().forEach(p => _runOpsChecked.add(p.id));
            _renderRunOpsProfiles(); _updateRunOpsCount(); _updateNameMapping();
        });
        _btn('runOpsDeselectAll', () => {
            _runOpsChecked.clear(); _renderRunOpsProfiles(); _updateRunOpsCount(); _updateNameMapping();
        });

        // Load names from file
        _btn('runOpsLoadNamesBtn', () => {
            document.getElementById('runOpsNameFileInput')?.click();
        });
        const nameFileInput = document.getElementById('runOpsNameFileInput');
        if (nameFileInput) nameFileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            try {
                const text = await file.text();
                const textarea = document.getElementById('runOpsNameList');
                if (textarea) textarea.value = text.trim();
                App.toast(`Loaded ${text.trim().split('\n').length} names from file`, 'success');
                _updateNameMapping();
            } catch (err) { App.toast('Failed to read file', 'error'); }
            nameFileInput.value = '';
        });

        // Name textarea input — live update mapping
        const nameListTa = document.getElementById('runOpsNameList');
        if (nameListTa) nameListTa.addEventListener('input', _updateNameMapping);

        // Start button
        _btn('runOpsModalStartBtn', _submitRunOps);
    }

    async function _submitRunOps() {
        if (!_runOpsChecked.size) { App.toast('No profiles selected', 'warn'); return; }

        // Collect selected operations
        const ops = [];
        document.querySelectorAll('.runops-op:checked').forEach(cb => ops.push(cb.value));
        if (!ops.length) { App.toast('No operations selected', 'warn'); return; }

        const workers = parseInt(document.getElementById('runOpsWorkers')?.value || '5') || 5;
        const stagger = parseInt(document.getElementById('runOpsStagger')?.value || '3') || 3;

        // Collect params
        const params = {};
        if (ops.includes('1')) params.new_password = _val('runOpsNewPassword') || '';
        if (ops.includes('2a') || ops.includes('6a')) params.recovery_phone = _val('runOpsRecoveryPhone') || '';
        if (ops.includes('3a')) params.recovery_email = _val('runOpsRecoveryEmail') || '';
        if (ops.includes('6a')) params.twofa_phone = _val('runOps2FAPhone') || '';
        if (ops.includes('8')) {
            params.name_list = (_val('runOpsNameList') || '').trim();
            params.name_country = document.getElementById('runOpsNameCountry')?.value || 'US';
        }

        // Validate required params
        if (ops.includes('1') && !params.new_password) { App.toast('New password is required for Change Password', 'warn'); return; }

        // Validate Op 8 — need name source (textarea or stored first_name on all profiles)
        if (ops.includes('8') && !params.name_list) {
            const allHaveStoredName = [..._runOpsChecked].every(id => {
                const p = _runOpsProfiles.find(x => x.id === id);
                return p && (p.first_name || '').trim();
            });
            if (!allHaveStoredName) {
                App.toast('Op 8 needs at least one name (textarea is empty and some selected profiles have no stored First Name)', 'warn');
                return;
            }
        }

        try {
            const data = await _api('/api/profiles/run-ops', {
                method: 'POST',
                body: JSON.stringify({
                    profile_ids: [..._runOpsChecked],
                    operations: ops.join(','),
                    params,
                    num_workers: workers,
                    stagger_delay: stagger,
                })
            });
            if (data.success) {
                _closeRunOpsModal();
                App.toast(`Operations started on ${data.total || _runOpsChecked.size} profiles`, 'success');
                _startOpProgress('run-ops');
                _startStatusPolling();
            } else {
                App.toast(data.error || data.message || 'Failed to start operations', 'error');
            }
        } catch (e) { App.toast('Error: ' + e.message, 'error'); }
    }

    // ══════════════════════════════════════════════════════════════════════
    // WRITE REVIEW
    // ══════════════════════════════════════════════════════════════════════

    let _wrPreviewTimer = null;
    let _wrSource = 'excel';                  // 'excel' | 'sheet'
    let _wrSheetId = '';
    let _wrSheetName = '';
    let _wrSelectedTabs = new Set();          // tabs the user ticked
    let _wrTabCounts = {};                    // {tab: posts_to_make}
    let _wrSearchTimer = null;
    let _wrPreviewDebounceTimer = null;
    function _wrPreviewTabsDebounced() {
        if (_wrPreviewDebounceTimer) clearTimeout(_wrPreviewDebounceTimer);
        _wrPreviewDebounceTimer = setTimeout(_wrPreviewTabs, 300);
    }

    function openWriteReviewModal() {
        _$('writeReviewModalOverlay').style.display = 'flex';
        _setWRPreview(null);
        _switchWRSource(_wrSource);
    }

    function closeWriteReviewModal() { _$('writeReviewModalOverlay').style.display = 'none'; }

    function _switchWRSource(src) {
        _wrSource = src;
        const xb = _$('wrSrcExcel'), sb = _$('wrSrcSheet');
        const xg = _$('wrExcelGroup'), sg = _$('wrSheetGroup');
        const hint = _$('wrWorkerHint');
        if (src === 'sheet') {
            if (xb) xb.style = 'flex:1;background:transparent;color:#94a3b8;';
            if (sb) sb.style = 'flex:1;background:rgba(245,158,11,0.18);';
            if (xg) xg.style.display = 'none';
            if (sg) sg.style.display = '';
            if (hint) hint.textContent = 'Profiles auto-matched by the Email column on each sheet row.';
            _wrRefreshSheetAuth();
        } else {
            if (xb) xb.style = 'flex:1;background:rgba(245,158,11,0.18);';
            if (sb) sb.style = 'flex:1;background:transparent;color:#94a3b8;';
            if (xg) xg.style.display = '';
            if (sg) sg.style.display = 'none';
            if (hint) hint.textContent = 'Profiles are matched automatically by email from the Excel file.';
        }
    }

    async function _wrRefreshSheetAuth() {
        try {
            const r = await App.apiFetch('/api/sheets/status');
            const s = await r.json();
            const auth = _$('wrSheetAuth'), picker = _$('wrSheetPicker');
            if (s.configured) {
                if (auth) auth.style.display = 'none';
                if (picker) picker.style.display = '';
                _wrLoadSheetList();
            } else {
                if (auth) auth.style.display = '';
                if (picker) picker.style.display = 'none';
            }
        } catch { /* ignore */ }
    }

    async function _wrAuthorize() {
        const btn = _$('wrSheetAuthBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting…'; }
        try {
            const r = await App.apiFetch('/api/sheets/authorize', { method: 'POST' });
            const d = await r.json();
            if (d.success) { App.toast('Connected ✓', 'success'); _wrRefreshSheetAuth(); }
            else App.toast(d.message || 'Auth failed', 'error');
        } catch (e) { App.toast(e.message, 'error'); }
        finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-key"></i> Connect'; }
        }
    }

    async function _wrLoadSheetList() {
        const list = _$('wrSheetList');
        if (!list) return;
        const q = (_$('wrSheetSearch') || {}).value || '';
        list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';
        try {
            const url = '/api/sheets/list' + (q ? `?q=${encodeURIComponent(q)}` : '');
            const r = await App.apiFetch(url);
            const d = await r.json();
            if (!d.success) {
                list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${_esc(d.message)}</div>`;
                return;
            }
            const sheets = d.sheets || [];
            list.innerHTML = sheets.map(s => {
                const isSel = s.id === _wrSheetId ? 'background:rgba(245,158,11,0.18);' : '';
                return `<div class="wr-s-row" data-id="${_esc(s.id)}" data-name="${_esc(s.name||'')}"
                    style="padding:7px 10px;border-bottom:1px solid #1e293b;cursor:pointer;${isSel}">
                    <div style="font-size:12px;color:#e2e8f0;">${_esc(s.name||'(unnamed)')}</div>
                </div>`;
            }).join('');
            list.querySelectorAll('.wr-s-row').forEach(el => {
                el.addEventListener('click', () => _wrPickSheet(
                    el.getAttribute('data-id'), el.getAttribute('data-name')
                ));
            });
        } catch (e) {
            list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${_esc(e.message)}</div>`;
        }
    }

    async function _wrPickSheet(id, name) {
        _wrSheetId = id; _wrSheetName = name || '';
        _wrSelectedTabs.clear(); _wrTabCounts = {};
        const _ts = _$('wrTabSearch'); if (_ts) _ts.value = '';
        // Refresh profile list whenever a new sheet is picked so the
        // user sees up-to-date profile data.
        _wrLoadProfileList();
        document.querySelectorAll('#wrSheetList .wr-s-row').forEach(el => {
            el.style.background = el.getAttribute('data-id') === id
                ? 'rgba(245,158,11,0.18)' : 'transparent';
        });
        const block = _$('wrTabBlock'); if (block) block.style.display = '';
        const tabList = _$('wrTabList'); if (tabList)
            tabList.innerHTML = '<div style="padding:10px;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading tabs…</div>';
        try {
            const r = await App.apiFetch(`/api/sheets/${encodeURIComponent(id)}/tabs`);
            const d = await r.json();
            if (!d.success) {
                if (tabList) tabList.innerHTML = `<div style="padding:10px;color:#fca5a5;font-size:12px;">${_esc(d.message)}</div>`;
                return;
            }
            const tabs = (d.tabs || []).map(t => t.title);
            if (tabList) {
                tabList.innerHTML = tabs.map(t => {
                    const tid = `wrTab_${btoa(unescape(encodeURIComponent(t))).replace(/[+/=]/g,'_')}`;
                    // NOTE: row is a <div>, not a <label> — wrapping a number
                    // input inside a <label> would let every click on the
                    // input toggle the sibling checkbox, breaking typing.
                    return `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:4px;">
                        <input type="checkbox" class="wr-tab-cb" data-tab="${_esc(t)}" id="${tid}" style="cursor:pointer;">
                        <label for="${tid}" style="font-size:12px;color:#e2e8f0;flex:1;cursor:pointer;">${_esc(t)}</label>
                        <span data-summary="${_esc(t)}" style="font-size:11px;color:#64748b;">—</span>
                        <input type="number" class="wr-tab-count" data-tab="${_esc(t)}" placeholder="post"
                               style="width:64px;background:#1a1a1a;border:1px solid #475569;border-radius:4px;padding:2px 6px;color:#e2e8f0;font-size:11px;display:none;" min="1" value="1">
                    </div>`;
                }).join('');
                tabList.querySelectorAll('.wr-tab-cb').forEach(cb => {
                    cb.addEventListener('change', () => _wrToggleTab(cb));
                });
                tabList.querySelectorAll('.wr-tab-count').forEach(inp => {
                    inp.addEventListener('input', () => {
                        const t = inp.getAttribute('data-tab');
                        const v = parseInt(inp.value, 10);
                        if (!isNaN(v) && v > 0) _wrTabCounts[t] = v;
                        else delete _wrTabCounts[t];
                    });
                });
            }
        } catch (e) {
            if (tabList) tabList.innerHTML = `<div style="padding:10px;color:#fca5a5;font-size:12px;">${_esc(e.message)}</div>`;
        }
    }

    let _wrSelectedProfiles = new Set();
    let _wrAllProfiles = [];

    function _wrPopulateGroupFilter() {
        const sel = _$('wrGroupFilter');
        if (!sel) return;
        const groupSet = new Set();
        _wrAllProfiles.forEach(p => {
            if (p.groups && p.groups.length) p.groups.forEach(g => g && groupSet.add(g));
            else if (p.group) groupSet.add(p.group);
        });
        const groups = [...groupSet].sort();
        sel.innerHTML = '<option value="">All groups</option>' +
            groups.map(g => `<option value="${_esc(g)}">${_esc(g)}</option>`).join('');
    }

    async function _wrLoadProfileList() {
        const list = _$('wrProfileList');
        if (!list) return;
        list.innerHTML = '<div style="padding:10px;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading profiles…</div>';
        try {
            const r = await App.apiFetch('/api/profiles?per_page=10000&slim=1');
            const d = await r.json();
            _wrAllProfiles = (d.profiles || d || [])
                .filter(p => p.email)
                .sort((a, b) => (a.email || '').localeCompare(b.email || ''));
            _wrPopulateGroupFilter();
            _wrRenderProfileList();
        } catch (e) {
            list.innerHTML = `<div style="padding:10px;color:#fca5a5;font-size:12px;">${_esc(e.message)}</div>`;
        }
    }

    function _wrGetFilteredProfiles() {
        const q = ((_$('wrProfileSearch') || {}).value || '').toLowerCase().trim();
        const grp = (_$('wrGroupFilter') || {}).value || '';
        return _wrAllProfiles.filter(p => {
            if (grp) {
                const pg = (p.groups && p.groups.length) ? p.groups : [(p.group || '')];
                if (!pg.includes(grp)) return false;
            }
            if (!q) return true;
            return (p.email || '').toLowerCase().includes(q) ||
                   (p.name || '').toLowerCase().includes(q);
        });
    }

    function _wrRenderProfileList() {
        const list = _$('wrProfileList');
        if (!list) return;
        const filtered = _wrGetFilteredProfiles();
        if (!filtered.length) {
            list.innerHTML = '<div style="padding:10px;text-align:center;color:#64748b;font-size:12px;">No profiles match.</div>';
            return;
        }
        list.innerHTML = filtered.map(p => {
            const checked = _wrSelectedProfiles.has(p.id) ? 'checked' : '';
            const grp = p.group ? `<span style="color:#64748b;">· ${_esc(p.group)}</span>` : '';
            const status = p.status === 'logged_in'
                ? '<span style="color:#22c55e;font-size:10px;">●</span>'
                : '<span style="color:#64748b;font-size:10px;">○</span>';
            return `<label style="display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:4px;cursor:pointer;">
                <input type="checkbox" class="wr-prof-cb" data-id="${_esc(p.id)}" ${checked}>
                ${status}
                <span style="font-size:12px;color:#e2e8f0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(p.email)}</span>
                ${grp}
            </label>`;
        }).join('');
        list.querySelectorAll('.wr-prof-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                const id = cb.getAttribute('data-id');
                if (cb.checked) _wrSelectedProfiles.add(id);
                else _wrSelectedProfiles.delete(id);
                _wrUpdateProfileCount();
            });
        });
    }

    function _wrUpdateProfileCount() {
        const el = _$('wrProfileCount');
        if (el) el.textContent = `${_wrSelectedProfiles.size} selected`;
    }

    function _wrFindBadge(tab) {
        const all = document.querySelectorAll('#wrTabList [data-summary]');
        for (const el of all) if (el.dataset.summary === tab) return el;
        return null;
    }
    function _wrFindCountInput(tab) {
        const all = document.querySelectorAll('#wrTabList input.wr-tab-count');
        for (const el of all) if (el.dataset.tab === tab) return el;
        return null;
    }

    // Client-side filter for the business-tab checklist. Only hides/shows
    // existing rows so checkbox state, counts and badges are all preserved.
    function _wrFilterTabs() {
        const q = ((_$('wrTabSearch') || {}).value || '').trim().toLowerCase();
        document.querySelectorAll('#wrTabList .wr-tab-cb').forEach(cb => {
            const row = cb.parentElement;
            if (!row) return;
            const name = (cb.getAttribute('data-tab') || '').toLowerCase();
            row.style.display = (!q || name.includes(q)) ? 'flex' : 'none';
        });
    }

    function _wrToggleTab(cb) {
        const t = cb.getAttribute('data-tab');
        const inp = _wrFindCountInput(t);
        if (cb.checked) {
            _wrSelectedTabs.add(t);
            if (inp) {
                inp.style.display = '';
                if (!inp.value) inp.value = '1';
                _wrTabCounts[t] = parseInt(inp.value, 10) || 1;
            }
            const badge = _wrFindBadge(t);
            if (badge) badge.innerHTML = '<i class="fas fa-spinner fa-spin" style="color:#94a3b8;"></i>';
            _wrPreviewTabsDebounced();
        } else {
            _wrSelectedTabs.delete(t);
            delete _wrTabCounts[t];
            if (inp) { inp.style.display = 'none'; }
            const badge = _wrFindBadge(t);
            if (badge) badge.innerHTML = '—';
            _wrUpdateSummary();
        }
    }

    async function _wrPreviewTabs() {
        const tabs = Array.from(_wrSelectedTabs);
        if (tabs.length === 0) { _wrUpdateSummary(); return; }
        const summaryEl = _$('wrTabSummary');
        if (summaryEl) {
            summaryEl.style.display = '';
            summaryEl.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Reading ${tabs.length} tab${tabs.length===1?'':'s'}…`;
        }
        tabs.forEach(t => {
            const badge = _wrFindBadge(t);
            if (badge && !badge.querySelector('.fa-spinner')) {
                badge.innerHTML = '<i class="fas fa-spinner fa-spin" style="color:#94a3b8;"></i>';
            }
        });
        try {
            const r = await App.apiFetch('/api/profiles/write-review/sheet/preview', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sheet_id: _wrSheetId, tabs }),
            });
            const d = await r.json().catch(() => ({ success: false, message: `HTTP ${r.status}` }));
            if (!r.ok || !d.success) {
                const msg = d.message || `HTTP ${r.status}`;
                if (summaryEl) summaryEl.innerHTML = `<i class="fas fa-times-circle"></i> ${_esc(msg)}`;
                tabs.forEach(t => {
                    const badge = _wrFindBadge(t);
                    if (badge) badge.innerHTML = `<span style="color:#ef4444;" title="${_esc(msg)}">err</span>`;
                });
                return;
            }
            (d.tabs || []).forEach(info => {
                const badge = _wrFindBadge(info.tab);
                if (badge) {
                    badge.innerHTML = info.error
                        ? `<span style="color:#ef4444;" title="${_esc(info.error)}">err</span>`
                        : `<span style="color:#22c55e;">${info.eligible_count} new</span>`
                          + `<span style="color:#64748b;"> · ${info.posted_count} done</span>`;
                }
                const inp = _wrFindCountInput(info.tab);
                if (inp && !inp.value) {
                    inp.value = '1';
                    _wrTabCounts[info.tab] = 1;
                }
            });
            _wrUpdateSummary(d);
        } catch (e) {
            if (summaryEl) summaryEl.innerHTML = `<i class="fas fa-times-circle"></i> ${_esc(e.message)}`;
            tabs.forEach(t => {
                const badge = _wrFindBadge(t);
                if (badge) badge.innerHTML = `<span style="color:#ef4444;" title="${_esc(e.message)}">err</span>`;
            });
        }
    }

    function _wrUpdateSummary(data) {
        const summaryEl = _$('wrTabSummary');
        if (!summaryEl) return;
        const tabs = Array.from(_wrSelectedTabs);
        if (!tabs.length) { summaryEl.style.display = 'none'; return; }
        const total = tabs.reduce((s, t) => s + (_wrTabCounts[t] || 0), 0);
        summaryEl.style.display = '';
        summaryEl.innerHTML =
            `<b>${tabs.length}</b> tab${tabs.length===1?'':'s'} selected · ` +
            `<b>${total}</b> review${total===1?'':'s'} planned to post`;
    }

    function _setWRPreview(info) {
        const el = _$('writeReviewPreview');
        if (!el) return;
        if (!info) { el.style.display = 'none'; return; }
        el.style.display = 'flex';
        if (!info.success) {
            el.innerHTML = `<span style="color:#f87171;"><i class="fas fa-exclamation-circle"></i> ${_esc(info.message || 'Cannot read file')}</span>`;
            return;
        }
        el.innerHTML = `
            <span style="color:#4ade80;"><i class="fas fa-file-excel"></i> <strong>${info.valid_rows}</strong> rows with GMB URL</span>
            <span style="color:#a5b4fc;"><i class="fas fa-users"></i> <strong>${info.matched_profiles}</strong> profiles matched</span>
            ${info.has_review_text ? '<span style="color:#64748b;font-size:11px;">· Review Text ✓</span>' : '<span style="color:#f59e0b;font-size:11px;">· No Review Text col</span>'}
            ${info.has_stars ? '<span style="color:#64748b;font-size:11px;">· Stars ✓</span>' : ''}
        `;
    }

    async function _previewWRFile() {
        const filePath = (_$('writeReviewFilePath') ? _$('writeReviewFilePath').value : '').trim();
        if (!filePath) { _setWRPreview(null); return; }
        if (_wrPreviewTimer) clearTimeout(_wrPreviewTimer);
        _wrPreviewTimer = setTimeout(async () => {
            try {
                const data = await _api('/api/profiles/write-review-preview', {
                    method: 'POST', body: JSON.stringify({ excel_file: filePath })
                });
                _setWRPreview(data);
            } catch(e) { _setWRPreview({ success: false, message: e.message }); }
        }, 400);
    }

    async function startWriteReview() {
        const workers = parseInt(_$('writeReviewWorkers') ? _$('writeReviewWorkers').value : '3') || 3;

        // Sheet mode
        if (_wrSource === 'sheet') {
            if (!_wrSheetId) { App.toast('Pick a Google Sheet first', 'error'); return; }
            const tabs_config = Array.from(_wrSelectedTabs)
                .filter(t => (_wrTabCounts[t] || 0) > 0)
                .map(t => ({ tab_name: t, count: _wrTabCounts[t] }));
            if (!tabs_config.length) {
                App.toast('Tick at least one tab and set a post count', 'error');
                return;
            }
            const profile_ids = Array.from(_wrSelectedProfiles);
            if (profile_ids.length === 0) {
                App.toast('Pick at least one profile that will post', 'error');
                return;
            }
            closeWriteReviewModal();
            App.toast(
                `Reading ${tabs_config.length} tab${tabs_config.length===1?'':'s'} from sheet… `
                + `this may take a moment.`, 'info'
            );
            _startOpProgress('review');
            try {
                const data = await _api('/api/profiles/write-review/sheet/start', {
                    method: 'POST',
                    body: JSON.stringify({
                        sheet_id: _wrSheetId,
                        tabs_config,
                        workers,
                        profile_ids,
                    })
                });
                if (data.success) {
                    let msg = `Write Review started: ${data.total_planned} review(s) `
                            + `across ${data.tabs} tab(s)`;
                    if (data.rows_skipped > 0) {
                        msg += ` — ${data.rows_skipped} row(s) skipped (not enough profiles)`;
                    }
                    App.toast(msg, 'success');
                } else {
                    _stopOpProgress('review', false);
                    App.toast(data.message || data.error || 'Failed to start', 'error');
                }
            } catch (e) {
                _stopOpProgress('review', false);
                App.toast('Write Review error: ' + e.message, 'error');
            }
            return;
        }

        // Excel mode (existing flow)
        const filePath = (_$('writeReviewFilePath') ? _$('writeReviewFilePath').value : '').trim();
        if (!filePath) { App.toast('Select an Excel file first', 'error'); return; }
        closeWriteReviewModal();
        try {
            const data = await _api('/api/profiles/do-write-review', {
                method: 'POST',
                body: JSON.stringify({ excel_file: filePath, num_workers: workers })
            });
            if (data.success) {
                App.toast(`Write Review started: ${data.matched} profiles matched by email`, 'success');
                _startOpProgress('review');
            } else App.toast(data.message || data.error || 'Failed to start', 'error');
        } catch(e) { App.toast('Write Review error: ' + e.message, 'error'); }
    }

    // ── GMB URL → Review URL Converter ──────────────────────────────────────
    let _gmbPreviewTimer = null;

    function openGmbToReviewModal() {
        _$('gmbToReviewModalOverlay').style.display = 'flex';
        _setGmbPreview(null);
        _$('gmbToReviewProgress').style.display = 'none';
        const btn = _$('gmbToReviewStartBtn');
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Generate Review URLs'; }
    }

    function closeGmbToReviewModal() {
        _$('gmbToReviewModalOverlay').style.display = 'none';
    }

    function _setGmbPreview(info) {
        const el = _$('gmbToReviewPreview');
        if (!el) return;
        if (!info) { el.style.display = 'none'; return; }
        el.style.display = 'flex';
        if (!info.success) {
            el.innerHTML = `<span style="color:#f87171;"><i class="fas fa-exclamation-circle"></i> ${_esc(info.message || 'Cannot read file')}</span>`;
            return;
        }
        el.innerHTML = `
            <span style="color:#4ade80;"><i class="fas fa-file-excel"></i> <strong>${info.total_rows}</strong> total rows</span>
            <span style="color:#a5b4fc;"><i class="fas fa-link"></i> <strong>${info.gmb_url_count}</strong> GMB URLs found</span>
            ${info.columns ? `<span style="color:#64748b;font-size:11px;">Columns: ${_esc(info.columns.join(', '))}</span>` : ''}
        `;
    }

    async function _previewGmbFile() {
        const filePath = _val('gmbToReviewFilePath').trim();
        if (!filePath) { _setGmbPreview(null); return; }
        if (_gmbPreviewTimer) clearTimeout(_gmbPreviewTimer);
        _gmbPreviewTimer = setTimeout(async () => {
            try {
                const data = await _api('/api/gmb-to-review/preview', {
                    method: 'POST', body: JSON.stringify({ file_path: filePath })
                });
                _setGmbPreview(data);
            } catch(e) { _setGmbPreview({ success: false, message: e.message }); }
        }, 400);
    }

    async function startGmbToReview() {
        const filePath = _val('gmbToReviewFilePath').trim();
        if (!filePath) { App.toast('Select an Excel file first', 'error'); return; }

        try {
            const data = await _api('/api/gmb-to-review/process', {
                method: 'POST',
                body: JSON.stringify({ file_path: filePath })
            });
            if (data.success) {
                closeGmbToReviewModal();
                App.toast('GMB Review URL generation started', 'success');
                _startOpProgress('gmb-review');
            } else {
                App.toast(data.message || 'Failed to start', 'error');
            }
        } catch(e) {
            App.toast('GMB Review URL error: ' + e.message, 'error');
        }
    }

    // ── Pagination helper ─────────────────────────────────────────────────────
    const _MODAL_PAGE_SIZE = 15;

    function _modalPagination(page, total) {
        if (total <= 1) return '';
        let s = Math.max(1, page - 2), e = Math.min(total, s + 4);
        if (e - s < 4) s = Math.max(1, e - 4);
        let btns = '';
        btns += `<button class="modal-pg-btn" data-pg="${page - 1}" ${page <= 1 ? 'disabled' : ''}>&#8249;</button>`;
        for (let i = s; i <= e; i++) {
            btns += `<button class="modal-pg-btn${i === page ? ' active' : ''}" data-pg="${i}">${i}</button>`;
        }
        btns += `<button class="modal-pg-btn" data-pg="${page + 1}" ${page >= total ? 'disabled' : ''}>&#8250;</button>`;
        btns += `<span class="modal-pg-info">${page} / ${total}</span>`;
        return `<div class="modal-pg-bar">${btns}</div>`;
    }

    // ── Appeal Modal ─────────────────────────────────────────────────────────

    let _appealModalProfiles = [];
    const _appealChecked = new Set();
    let _appealSearch = '';
    let _appealPage = 1;
    let _appealGroupFilter = '';

    function _filteredAppeal() {
        let list = _appealModalProfiles;
        const q = _appealSearch.trim().toLowerCase();
        if (q) list = list.filter(p =>
            (p.email || '').toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q)
        );
        if (_appealGroupFilter) list = list.filter(p => {
            const gs = (p.groups && p.groups.length) ? p.groups : [(p.group || 'default')];
            return gs.map(g => g.toLowerCase()).includes(_appealGroupFilter.toLowerCase());
        });
        return list;
    }

    async function openAppealModal() {
        const modal = document.getElementById('appealModal');
        if (!modal) return;

        // Reset mode to Select
        _appealMode = 'select';
        _appealExcelPath = '';
        _setAppealMode('select');
        const excelName = document.getElementById('appealExcelFileName');
        if (excelName) excelName.textContent = 'No file selected';
        const excelInfo = document.getElementById('appealExcelMatchInfo');
        if (excelInfo) { excelInfo.style.display = 'none'; excelInfo.innerHTML = ''; }

        // Reset search/page/group state
        _appealSearch = '';
        _appealPage = 1;
        _appealGroupFilter = '';
        const searchEl = document.getElementById('appealSearchInput');
        if (searchEl) searchEl.value = '';
        const groupEl = document.getElementById('appealGroupFilter');
        if (groupEl) groupEl.value = '';
        _loadGroups();

        // Load profiles
        _appealModalProfiles = [];
        _appealChecked.clear();
        document.getElementById('appealProfileList').innerHTML =
            '<div style="color:#64748b;font-size:13px;text-align:center;padding:30px;">Loading...</div>';
        modal.style.display = 'flex';

        try {
            // slim=1 strips fingerprint/perf/bookmarks_text/etc. — modal only
            // needs id/email/group/status. Drops payload from ~10MB to ~200KB.
            const data = await _api('/api/profiles?per_page=10000&slim=1');
            _appealModalProfiles = (data.profiles || data || []);
        } catch (e) {
            _appealModalProfiles = [];
        }

        // Pre-check profiles that were already selected in the main table
        _appealModalProfiles.forEach(p => {
            if (_selectedIds.has(p.id)) _appealChecked.add(p.id);
        });

        _renderAppealList();
        _updateAppealCount();
    }

    function _renderAppealList() {
        const container = document.getElementById('appealProfileList');
        if (!container) return;

        const filtered = _filteredAppeal();
        if (!filtered.length) {
            container.innerHTML = '<div style="color:#64748b;font-size:13px;text-align:center;padding:30px;">No profiles found</div>';
            return;
        }

        const totalPages = Math.max(1, Math.ceil(filtered.length / _MODAL_PAGE_SIZE));
        if (_appealPage > totalPages) _appealPage = totalPages;
        const pageItems = filtered.slice((_appealPage - 1) * _MODAL_PAGE_SIZE, _appealPage * _MODAL_PAGE_SIZE);

        const cards = pageItems.map(p => {
            const checked = _appealChecked.has(p.id) ? 'checked' : '';
            const email = p.email || p.name || p.id;
            const status = p.login_status || p.status || 'unknown';
            const proxy = p.proxy ? `${p.proxy.host || ''}:${p.proxy.port || ''}` : '—';
            const osVerRaw = p.overview?.os_version || '';
            const osVerNum = osVerRaw.replace(/^Windows\s*/i, '').replace(/\.\d+\.\d+$/, '').trim();
            const winTag = osVerNum ? `<span style="font-size:10px;background:rgba(99,102,241,0.2);color:#a5b4fc;padding:1px 5px;border-radius:4px;">WIN ${osVerNum}</span>` : '';
            const engTag = p.engine === 'nst' ? '<span style="font-size:10px;background:rgba(59,130,246,0.2);color:#60a5fa;padding:1px 5px;border-radius:4px;">NST</span>' : '';
            const statusColor = status === 'logged_in' ? '#22c55e' : '#94a3b8';
            const statusBg = status === 'logged_in' ? 'rgba(34,197,94,0.12)' : 'rgba(100,116,139,0.15)';

            let appealTrack;
            if (p.last_appeal_at) {
                const ico = p.last_appeal_ok ? '✓' : '✗';
                const clr = p.last_appeal_ok ? '#34d399' : '#f87171';
                const summ = p.last_appeal_summary ? ` — ${_esc(p.last_appeal_summary)}` : '';
                const hist = (p.appeal_history || []).slice(-5).reverse();
                const histHtml = hist.length > 1 ? hist.map(h => {
                    const d = h.date ? new Date(h.date).toLocaleDateString('en-GB', {day:'2-digit',month:'short'}) : '?';
                    const hIco = h.ok ? '<span style="color:#34d399;">✓</span>' : '<span style="color:#f87171;">✗</span>';
                    const hSumm = h.summary ? ` <span style="color:#64748b;">${_esc(h.summary)}</span>` : '';
                    return `<span style="display:inline-flex;align-items:center;gap:3px;background:rgba(255,255,255,0.04);border-radius:3px;padding:1px 5px;font-size:10px;">${hIco} ${d}${hSumm}</span>`;
                }).join('') : '';
                appealTrack = `<div style="font-size:11px;color:${clr};margin-top:4px;display:flex;align-items:center;gap:4px;flex-wrap:wrap;">
                    <span style="font-weight:600;">${ico} Last: ${_timeAgo(p.last_appeal_at)}${summ}</span>
                </div>${histHtml ? `<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:4px;">${histHtml}</div>` : ''}`;
            } else {
                appealTrack = `<div style="font-size:11px;color:#475569;margin-top:4px;"><i class="fas fa-clock" style="margin-right:4px;font-size:10px;"></i>Never appealed</div>`;
            }

            return `<label style="display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-radius:8px;cursor:pointer;border:1px solid rgba(255,255,255,0.07);background:rgba(255,255,255,0.025);transition:background 0.15s;margin-bottom:4px;" class="appeal-row">
                <input type="checkbox" data-id="${p.id}" ${checked} style="width:15px;height:15px;accent-color:#f59e0b;flex-shrink:0;margin-top:3px;">
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:2px;">${winTag}${engTag}<span style="font-size:13px;font-weight:600;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(email)}</span></div>
                    <div style="font-size:11px;color:#64748b;">${_esc(proxy)}</div>
                    ${appealTrack}
                </div>
                <span style="font-size:10px;padding:2px 8px;border-radius:10px;white-space:nowrap;flex-shrink:0;background:${statusBg};color:${statusColor};margin-top:2px;">${status.replace(/_/g,' ')}</span>
            </label>`;
        }).join('');

        container.innerHTML = cards + _modalPagination(_appealPage, totalPages);

        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                if (cb.checked) _appealChecked.add(cb.dataset.id);
                else _appealChecked.delete(cb.dataset.id);
                _updateAppealCount();
            });
        });
        container.querySelectorAll('.modal-pg-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
                _appealPage = parseInt(btn.dataset.pg);
                _renderAppealList();
                container.scrollTop = 0;
            });
        });
    }

    function _updateAppealCount() {
        const el = document.getElementById('appealSelectedCount');
        if (el) el.textContent = _appealChecked.size;
    }

    function closeAppealModal() {
        const modal = document.getElementById('appealModal');
        if (modal) modal.style.display = 'none';
    }

    // ── Appeal Mode Toggle (Select vs Excel) ────────────────────────────────
    let _appealMode = 'select'; // 'select' | 'excel' | 'sheet'
    let _appealExcelPath = '';
    let _appealSheetId = '';
    let _appealSheetName = '';
    let _appealSelectedTabs = new Set();

    function _updateAppealTabCount() {
        const el = document.getElementById('appealSheetTabCount');
        if (el) el.textContent = `${_appealSelectedTabs.size} selected`;
    }

    function _setAppealMode(mode) {
        _appealMode = mode;
        const ids = ['appealModeSelectBtn', 'appealModeExcelBtn', 'appealModeSheetBtn'];
        const ctrls = {
            select: 'appealSelectControls',
            excel:  'appealExcelControls',
            sheet:  'appealSheetControls',
        };
        const hint = document.getElementById('appealModeHint');
        // Reset visuals
        ids.forEach(id => {
            const b = document.getElementById(id);
            if (!b) return;
            b.classList.remove('active');
            b.style.background = 'transparent';
            b.style.color = '#94a3b8';
        });
        Object.values(ctrls).forEach(cid => {
            const c = document.getElementById(cid);
            if (c) c.style.display = 'none';
        });
        // Activate selected
        const activeBtnId =
            mode === 'excel' ? 'appealModeExcelBtn' :
            mode === 'sheet' ? 'appealModeSheetBtn' :
                               'appealModeSelectBtn';
        const ab = document.getElementById(activeBtnId);
        if (ab) {
            ab.classList.add('active');
            ab.style.background = '';
            ab.style.color = '';
        }
        const ac = document.getElementById(ctrls[mode] || ctrls.select);
        if (ac) ac.style.display = '';
        if (hint) {
            if (mode === 'excel')      hint.textContent = 'Upload an Excel file with an Email column.';
            else if (mode === 'sheet') hint.textContent = "Pick a Google Sheet — rows with Status='Missing' will be appealed.";
            else                       hint.textContent = 'Select profiles to run Appeal on.';
        }
        if (mode === 'sheet') _refreshAppealSheetAuth();

        const profileList = document.getElementById('appealProfileList');
        if (profileList) {
            if (mode === 'sheet') {
                profileList.style.display = 'none';
            } else {
                profileList.style.display = '';
            }
        }
    }

    // ── Appeal: Google Sheet mode ─────────────────────────────────────────
    async function _refreshAppealSheetAuth() {
        try {
            const r = await App.apiFetch('/api/sheets/status');
            const s = await r.json();
            const auth = document.getElementById('appealSheetAuthBox');
            const picker = document.getElementById('appealSheetPicker');
            if (s.configured) {
                if (auth) auth.style.display = 'none';
                if (picker) picker.style.display = '';
                _loadAppealSheetList();
            } else {
                if (auth) auth.style.display = '';
                if (picker) picker.style.display = 'none';
            }
        } catch { /* ignore */ }
    }

    let _appealSheetSearchTimer = null;
    async function _loadAppealSheetList() {
        const list = document.getElementById('appealSheetList');
        if (!list) return;
        const q = (document.getElementById('appealSheetSearch') || {}).value || '';
        list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';
        try {
            const url = '/api/sheets/list' + (q ? `?q=${encodeURIComponent(q)}` : '');
            const r = await App.apiFetch(url);
            const d = await r.json();
            if (!d.success) {
                list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${_esc(d.message)}</div>`;
                return;
            }
            const sheets = d.sheets || [];
            if (!sheets.length) {
                list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;">No spreadsheets.</div>';
                return;
            }
            list.innerHTML = sheets.map(s => {
                const isSel = s.id === _appealSheetId ? 'background:rgba(245,158,11,0.18);' : '';
                return `<div class="ap-sheet-row" data-id="${_esc(s.id)}" data-name="${_esc(s.name||'')}"
                            style="padding:8px 10px;border-bottom:1px solid #1e293b;cursor:pointer;${isSel}">
                    <div style="font-size:13px;color:#e2e8f0;">${_esc(s.name||'(unnamed)')}</div>
                    <div style="font-size:11px;color:#64748b;">${_esc(s.owner||'')}</div>
                </div>`;
            }).join('');
            list.querySelectorAll('.ap-sheet-row').forEach(el => {
                el.addEventListener('click', () => _onAppealSheetPicked(
                    el.getAttribute('data-id'),
                    el.getAttribute('data-name'),
                ));
            });
        } catch (e) {
            list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${_esc(e.message)}</div>`;
        }
    }

    async function _onAppealSheetPicked(id, name) {
        _appealSheetId = id;
        _appealSheetName = name || '';
        _appealSelectedTabs.clear();
        document.querySelectorAll('#appealSheetList .ap-sheet-row').forEach(el => {
            el.style.background = el.getAttribute('data-id') === id
                ? 'rgba(245,158,11,0.18)' : 'transparent';
        });
        const tabRow = document.getElementById('appealSheetTabRow');
        const tabList = document.getElementById('appealSheetTabList');
        if (tabRow) tabRow.style.display = '';
        if (tabList) tabList.innerHTML = '<div style="padding:10px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading tabs…</div>';
        _updateAppealTabCount();
        try {
            const r = await App.apiFetch(`/api/sheets/${encodeURIComponent(id)}/tabs`);
            const d = await r.json();
            if (!d.success) {
                if (tabList) tabList.innerHTML = `<div style="padding:10px;color:#fca5a5;font-size:12px;">${_esc(d.message)}</div>`;
                return;
            }
            const tabs = d.tabs || [];
            if (!tabList) return;
            tabList.innerHTML = '';
            tabs.forEach(t => {
                const row = document.createElement('label');
                row.className = 'ap-tab-row';
                row.setAttribute('data-tab', t.title);
                row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:5px 10px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.04);font-size:12px;color:#e2e8f0;';
                row.innerHTML =
                    `<input type="checkbox" class="ap-tab-cb" value="${_esc(t.title)}" checked style="accent-color:#f59e0b;">` +
                    `<span style="flex:1;">${_esc(t.title)}</span>` +
                    `<span class="ap-tab-count" style="font-size:11px;color:#64748b;"></span>`;
                const cb = row.querySelector('input');
                cb.addEventListener('change', () => {
                    if (cb.checked) _appealSelectedTabs.add(t.title);
                    else _appealSelectedTabs.delete(t.title);
                    _updateAppealTabCount();
                    _scheduleAppealPreview();
                });
                _appealSelectedTabs.add(t.title);
                tabList.appendChild(row);
            });
            _updateAppealTabCount();
            _scheduleAppealPreview();
        } catch (e) { App.toast('Tabs error: ' + e.message, 'error'); }
    }

    function _appealToggleAllTabs(selectAll) {
        const tabList = document.getElementById('appealSheetTabList');
        if (!tabList) return;
        _appealSelectedTabs.clear();
        tabList.querySelectorAll('.ap-tab-cb').forEach(cb => {
            cb.checked = selectAll;
            if (selectAll) _appealSelectedTabs.add(cb.value);
        });
        _updateAppealTabCount();
        _scheduleAppealPreview();
    }


    // Debounce + AbortController so rapid checkbox toggles don't pile
    // up multiple in-flight requests (which previously froze the modal
    // and looked like a crash on 5+ tab selections).
    let _appealPreviewTimer = null;
    let _appealPreviewAbort = null;

    function _scheduleAppealPreview() {
        if (_appealPreviewTimer) clearTimeout(_appealPreviewTimer);
        _appealPreviewTimer = setTimeout(_previewAppealSheet, 300);
    }

    async function _previewAppealSheet() {
        if (_appealPreviewAbort) {
            try { _appealPreviewAbort.abort(); } catch (_) {}
        }
        const controller = new AbortController();
        _appealPreviewAbort = controller;

        const id = _appealSheetId;
        const selectedTabs = [..._appealSelectedTabs];
        const info = document.getElementById('appealSheetMatchInfo');
        // Clear stale per-tab counts before the new fetch resolves
        document.querySelectorAll('#appealSheetTabList .ap-tab-row').forEach(row => {
            const c = row.querySelector('.ap-tab-count');
            if (c) c.textContent = '';
        });
        if (!id || selectedTabs.length === 0 || !info) {
            if (info) info.style.display = 'none';
            return;
        }
        info.style.display = '';
        info.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Matching…';
        try {
            const r = await App.apiFetch('/api/profiles/appeal/match-sheet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sheet_id: id, tab_name: selectedTabs[0], tabs: selectedTabs }),
                signal: controller.signal,
            });
            const d = await r.json();
            if (controller.signal.aborted) return;
            if (!d.success) {
                info.innerHTML = `<i class="fas fa-times-circle" style="color:#ef4444;"></i> ${_esc(d.message)}`;
                return;
            }
            // Per-tab counts next to each checkbox
            const perTab = {};
            (d.per_tab || []).forEach(p => { perTab[p.tab] = p; });
            document.querySelectorAll('#appealSheetTabList .ap-tab-row').forEach(row => {
                const tabName = row.getAttribute('data-tab');
                const countEl = row.querySelector('.ap-tab-count');
                const p = perTab[tabName];
                if (!countEl) return;
                if (!p) { countEl.textContent = ''; return; }
                if (!p.success) {
                    countEl.textContent = 'error';
                    countEl.style.color = '#f87171';
                    return;
                }
                countEl.textContent = `${p.missing_rows} missing`;
                countEl.style.color = p.missing_rows > 0 ? '#f59e0b' : '#64748b';
            });
            let html =
                `<i class="fas fa-check-circle" style="color:#22c55e;"></i> ` +
                `<b>${_esc(_appealSheetName)}</b> — ` +
                `<b>${d.matched_count}</b> profile${d.matched_count===1?'':'s'} to appeal ` +
                `(out of ${d.total_missing_rows} 'Missing' rows across ${selectedTabs.length} tab${selectedTabs.length===1?'':'s'})`;
            if (d.not_found_count > 0) {
                html += ` · <span style="color:#f59e0b;">${d.not_found_count} email${d.not_found_count>1?'s':''} not in profile manager</span>`;
            }
            if (d.total_missing_rows === 0 && Array.isArray(d.unique_status_values) && d.unique_status_values.length > 0) {
                const list = d.unique_status_values
                    .map(v => `<code style="background:#1e293b;padding:1px 5px;border-radius:3px;">${_esc(v.value)}</code> ×${v.count}`)
                    .join(', ');
                const colName = d.status_header_used || 'Status';
                html += `<div style="margin-top:6px;font-size:11px;color:#94a3b8;line-height:1.5;">` +
                        `Looked at column <b>${_esc(colName)}</b>. Values found: ${list}` +
                        `</div>`;
            }
            info.innerHTML = html;
        } catch (e) {
            if (e && e.name === 'AbortError') return;
            info.innerHTML = `<i class="fas fa-times-circle" style="color:#ef4444;"></i> ${_esc(e.message)}`;
        } finally {
            if (_appealPreviewAbort === controller) _appealPreviewAbort = null;
        }
    }

    
    async function _doAppealSheetAuthorize() {
        const btn = document.getElementById('appealSheetAuthBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting…'; }
        App.toast('Browser will open — log in and grant access', 'info');
        try {
            const r = await App.apiFetch('/api/sheets/authorize', { method: 'POST' });
            const d = await r.json();
            if (d.success) {
                App.toast('Google Sheets connected ✓', 'success');
                await _refreshAppealSheetAuth();
            } else {
                App.toast(d.message || 'Authorization failed', 'error');
            }
        } catch (e) { App.toast('Auth error: ' + e.message, 'error'); }
        finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-key"></i> Connect Google Sheets'; }
        }
    }

    async function _appealBrowseExcel() {
        const filePath = await window.electronAPI.selectFile();
        if (!filePath) return;
        _appealExcelPath = filePath;
        const nameEl = document.getElementById('appealExcelFileName');
        if (nameEl) nameEl.textContent = filePath.split(/[\\/]/).pop();

        // Match emails against profiles
        const infoEl = document.getElementById('appealExcelMatchInfo');
        if (infoEl) {
            infoEl.style.display = '';
            infoEl.innerHTML = '<i class="fas fa-spinner fa-spin" style="color:#f59e0b;"></i> <span style="color:#94a3b8;font-size:12px;">Matching emails...</span>';
        }
        try {
            const data = await _api('/api/profiles/appeal-match-excel', {
                method: 'POST',
                body: JSON.stringify({ file_path: filePath })
            });
            if (!data.success) {
                if (infoEl) infoEl.innerHTML = `<span style="color:#f87171;font-size:12px;"><i class="fas fa-exclamation-circle"></i> ${_esc(data.message)}</span>`;
                return;
            }
            // Auto-select matched profiles
            _appealChecked.clear();
            (data.matched || []).forEach(m => _appealChecked.add(m.id));
            _renderAppealList();
            _updateAppealCount();

            // Show match summary
            let html = `<div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;">
                <span style="font-size:13px;color:#e2e8f0;font-weight:600;"><i class="fas fa-check-circle" style="color:#22c55e;margin-right:4px;"></i>${data.matched_count} matched</span>
                <span style="font-size:12px;color:#94a3b8;">out of ${data.total_emails} emails</span>`;
            if (data.not_found_count > 0) {
                html += `<span style="font-size:12px;color:#f59e0b;"><i class="fas fa-exclamation-triangle" style="margin-right:3px;"></i>${data.not_found_count} not found</span>`;
            }
            html += `</div>`;
            if (data.not_found_count > 0 && data.not_found.length <= 10) {
                html += `<div style="margin-top:6px;font-size:11px;color:#64748b;max-height:80px;overflow-y:auto;">Not found: ${data.not_found.map(e => _esc(e)).join(', ')}</div>`;
            }
            if (infoEl) infoEl.innerHTML = html;
        } catch (e) {
            if (infoEl) infoEl.innerHTML = `<span style="color:#f87171;font-size:12px;"><i class="fas fa-exclamation-circle"></i> Error reading file</span>`;
        }
    }

    async function startDoAllAppeal() {
        const workers = parseInt(document.getElementById('appealWorkers')?.value || '3', 10);

        // ── Google Sheet mode ────────────────────────────────────────
        if (_appealMode === 'sheet') {
            const tabs = [..._appealSelectedTabs];
            if (!_appealSheetId || tabs.length === 0) {
                App.toast('Pick a sheet and select at least one tab', 'error');
                return;
            }
            closeAppealModal();
            try {
                const data = await _api('/api/profiles/appeal/start-from-sheet', {
                    method: 'POST',
                    body: JSON.stringify({
                        sheet_id: _appealSheetId,
                        tab_name: tabs[0],
                        tabs: tabs,
                        workers,
                    })
                });
                if (data.success) {
                    App.toast(`Appeal started on ${data.matched} profile(s) from sheet`, 'success');
                    _startOpProgress('appeal');
                    _startStatusPolling();
                } else {
                    App.toast(data.error || data.message || 'Failed', 'error');
                }
            } catch (e) { App.toast('Appeal error: ' + e.message, 'error'); }
            return;
        }

        // ── Select / Excel mode (existing flow) ──────────────────────
        if (_appealChecked.size === 0) { App.toast('Select at least one profile', 'error'); return; }
        const profileIds = Array.from(_appealChecked);
        closeAppealModal();
        try {
            const data = await _api('/api/profiles/do-all-appeal', {
                method: 'POST',
                body: JSON.stringify({ num_workers: workers, profile_ids: profileIds })
            });
            if (data.success) {
                App.toast(`Appeal started on ${profileIds.length} profile(s)`, 'success');
                _startOpProgress('appeal');
                _startStatusPolling();
            }
            else App.toast(data.message || data.error || 'Failed', 'error');
        } catch (e) { App.toast('Appeal error', 'error'); }
    }

    // ── Health Modal ─────────────────────────────────────────────────────────

    let _healthModalProfiles = [];
    const _healthChecked = new Set();
    let _healthProfileSearch = '';
    let _healthProfilePage = 1;
    let _healthGroupFilter = '';

    function _filteredHealth() {
        let list = _healthModalProfiles;
        const q = _healthProfileSearch.trim().toLowerCase();
        if (q) list = list.filter(p =>
            (p.email || '').toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q)
        );
        if (_healthGroupFilter) list = list.filter(p => {
            const gs = (p.groups && p.groups.length) ? p.groups : [(p.group || 'default')];
            return gs.map(g => g.toLowerCase()).includes(_healthGroupFilter.toLowerCase());
        });
        return list;
    }

    // ── Group helpers ──────────────────────────────────────────────────────────

    function _refreshGroupsFromProfiles(allProfilesOrGroups) {
        // Accepts either:
        //   - a flat array of group-name strings (from /api/profiles/counts)
        //   - a list of profile objects (legacy callers — extracts groups)
        // The counts endpoint returns the group list directly so we no longer
        // need to walk the full profile array just to dedupe groups.
        if (!allProfilesOrGroups || !allProfilesOrGroups.length) return;
        let groups;
        if (typeof allProfilesOrGroups[0] === 'string') {
            groups = allProfilesOrGroups.slice().sort();
        } else {
            const groupSet = new Set();
            allProfilesOrGroups.forEach(p => {
                const gs = (p.groups && p.groups.length) ? p.groups : [(p.group || 'default')];
                gs.forEach(g => { if (g && g.trim()) groupSet.add(g.trim()); });
            });
            groups = [...groupSet].sort();
        }
        const selectors = ['pmGroupFilter', 'appealGroupFilter', 'healthGroupFilter'];
        selectors.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            const current = el.value;
            el.innerHTML = '<option value="">All Groups</option>';
            groups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                opt.textContent = g;
                el.appendChild(opt);
            });
            el.value = (groups.includes(current)) ? current : '';
        });
        // Also update datalists
        const datalists = ['pmGroupList', 'batchLoginGroupList'];
        datalists.forEach(id => {
            const dl = document.getElementById(id);
            if (!dl) return;
            dl.innerHTML = '';
            groups.forEach(g => {
                const opt = document.createElement('option');
                opt.value = g;
                dl.appendChild(opt);
            });
        });
    }

    async function _loadGroups() {
        try {
            const data = await _api('/api/profiles/groups');
            const groups = data.groups || [];

            // Populate all group selects/datalists
            const selectors = ['pmGroupFilter', 'appealGroupFilter', 'healthGroupFilter'];
            selectors.forEach(id => {
                const el = document.getElementById(id);
                if (!el) return;
                const current = el.value;
                // Keep "All Groups" option
                el.innerHTML = '<option value="">All Groups</option>';
                groups.forEach(g => {
                    const opt = document.createElement('option');
                    opt.value = g;
                    opt.textContent = g;
                    el.appendChild(opt);
                });
                el.value = current;
            });

            // Populate datalists for text inputs
            const datalists = ['pmGroupList', 'batchLoginGroupList'];
            datalists.forEach(id => {
                const dl = document.getElementById(id);
                if (!dl) return;
                dl.innerHTML = '';
                groups.forEach(g => {
                    const opt = document.createElement('option');
                    opt.value = g;
                    dl.appendChild(opt);
                });
            });
        } catch (e) { /* ignore */ }
    }

    async function openHealthModal() {
        const modal = document.getElementById('healthModal');
        if (!modal) return;

        _healthProfileSearch = '';
        _healthProfilePage = 1;
        _healthGroupFilter = '';
        const hSearchEl = document.getElementById('healthProfileSearchInput');
        if (hSearchEl) hSearchEl.value = '';
        const hGroupEl = document.getElementById('healthGroupFilter');
        if (hGroupEl) hGroupEl.value = '';
        _loadGroups();

        _healthModalProfiles = [];
        _healthChecked.clear();
        const listEl = document.getElementById('healthProfileList');
        if (listEl) listEl.innerHTML = '<div style="color:#64748b;font-size:12px;text-align:center;padding:20px;">Loading...</div>';
        _updateHealthCount();
        modal.style.display = 'flex';

        try {
            // slim=1 keeps the payload light — modal only needs id/email/group/status
            const data = await _api('/api/profiles?per_page=10000&slim=1');
            _healthModalProfiles = (data.profiles || data || []);
        } catch (e) {
            _healthModalProfiles = [];
        }

        // Pre-check profiles selected in main table (only those from current group filter if active)
        _healthModalProfiles.forEach(p => {
            if (_selectedIds.has(p.id)) _healthChecked.add(p.id);
        });
        // If none pre-selected, DON'T auto-check all — let user pick via Select All button

        _renderHealthProfileList();
        _updateHealthCount();
    }

    function _renderHealthProfileList() {
        const container = document.getElementById('healthProfileList');
        if (!container) return;

        const filtered = _filteredHealth();
        if (!filtered.length) {
            container.innerHTML = '<div style="color:#64748b;font-size:12px;text-align:center;padding:20px;">No profiles found</div>';
            return;
        }

        const totalPages = Math.max(1, Math.ceil(filtered.length / _MODAL_PAGE_SIZE));
        if (_healthProfilePage > totalPages) _healthProfilePage = totalPages;
        const pageItems = filtered.slice((_healthProfilePage - 1) * _MODAL_PAGE_SIZE, _healthProfilePage * _MODAL_PAGE_SIZE);

        const cards = pageItems.map(p => {
            const checked = _healthChecked.has(p.id) ? 'checked' : '';
            const email = p.email || p.name || p.id;
            const status = p.login_status || p.status || 'unknown';
            const engTag = p.engine === 'nst' ? '<span style="font-size:9px;background:rgba(59,130,246,0.2);color:#60a5fa;padding:1px 4px;border-radius:3px;">NST</span>' : '';
            const dot = status === 'logged_in' ? '#22c55e' : '#64748b';

            let healthTrack;
            if (p.last_health_at) {
                const done = p.last_health_done || 0;
                const total = p.last_health_total || 0;
                const clr = p.last_health_ok ? '#34d399' : '#f87171';
                const ico = p.last_health_ok ? '✓' : '✗';
                const hist = (p.health_history || []).slice(-5).reverse();
                const histHtml = hist.length > 1 ? hist.map(h => {
                    const d = h.date ? new Date(h.date).toLocaleDateString('en-GB', {day:'2-digit',month:'short'}) : '?';
                    const hIco = h.ok ? '<span style="color:#34d399;">✓</span>' : '<span style="color:#f87171;">✗</span>';
                    return `<span style="display:inline-flex;align-items:center;gap:2px;background:rgba(255,255,255,0.04);border-radius:3px;padding:1px 4px;font-size:9px;">${hIco} ${d}: ${h.done||0}/${h.total||0}</span>`;
                }).join('') : '';
                healthTrack = `<div style="font-size:10px;color:${clr};margin-top:3px;font-weight:600;"><span>${ico} ${_timeAgo(p.last_health_at)} — ${done}/${total} done</span></div>
                ${histHtml ? `<div style="display:flex;flex-wrap:wrap;gap:2px;margin-top:3px;">${histHtml}</div>` : ''}`;
            } else {
                healthTrack = `<div style="font-size:10px;color:#475569;margin-top:3px;">Never run</div>`;
            }

            return `<label style="display:flex;align-items:flex-start;gap:8px;padding:8px 10px;border-radius:6px;cursor:pointer;border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.025);transition:background 0.12s;margin-bottom:4px;" class="health-profile-row">
                <input type="checkbox" data-id="${p.id}" ${checked} style="width:13px;height:13px;accent-color:#22c55e;flex-shrink:0;margin-top:3px;">
                <span style="width:7px;height:7px;border-radius:50%;background:${dot};flex-shrink:0;margin-top:4px;"></span>
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;">${engTag}<span style="font-size:12px;font-weight:600;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(email)}</span></div>
                    ${healthTrack}
                </div>
            </label>`;
        }).join('');

        container.innerHTML = cards + _modalPagination(_healthProfilePage, totalPages);

        container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                if (cb.checked) _healthChecked.add(cb.dataset.id);
                else _healthChecked.delete(cb.dataset.id);
                _updateHealthCount();
            });
        });
        container.querySelectorAll('.modal-pg-btn:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
                _healthProfilePage = parseInt(btn.dataset.pg);
                _renderHealthProfileList();
                container.scrollTop = 0;
            });
        });
    }

    function closeHealthModal() {
        const modal = document.getElementById('healthModal');
        if (modal) modal.style.display = 'none';
    }

    function _updateHealthCount() {
        // Activity count (only activity checkboxes in right panel, not profile checkboxes)
        const actChecked = document.querySelectorAll('#healthModal .health-act-item input[type="checkbox"]:checked');
        const countEl = document.getElementById('healthSelectedCount');
        if (countEl) countEl.textContent = actChecked.length;
        const countEl2 = document.getElementById('healthSelectedCount2');
        if (countEl2) countEl2.textContent = actChecked.length;
        // Profile count
        const profCount = document.getElementById('healthProfileCount');
        if (profCount) profCount.textContent = _healthChecked.size;
        const profCountFooter = document.getElementById('healthProfileCountFooter');
        if (profCountFooter) profCountFooter.textContent = _healthChecked.size;
    }

    // Smart Activity Presets — activities picked automatically based on goal
    const _SMART_PRESETS = {
        'gmail_trust': {
            activities: [
                'gmail_inbox', 'gmail_read_email', 'gmail_scroll_inbox', 'gmail_search_email', 'gmail_check_sent',
                'search_news', 'search_weather', 'search_local', 'search_restaurants', 'search_tech',
                'youtube_browse_feed', 'youtube_trending', 'youtube_watch_video',
                'maps_search_restaurants', 'maps_browse_places',
                'drive_browse', 'drive_recent',
                'account_security', 'account_activity',
                'news_headlines', 'calendar_view',
            ],
            duration: 10, rounds: 2,
        },
        'review_ready': {
            activities: [
                'maps_search_restaurants', 'maps_browse_places', 'maps_read_reviews', 'maps_view_photos', 'maps_street_view',
                'maps_coffee_shops', 'maps_hotels', 'maps_supermarkets', 'maps_parks',
                'search_restaurants', 'search_local', 'search_food', 'search_realestate',
                'gmail_inbox', 'gmail_read_email',
                'youtube_browse_feed', 'youtube_travel',
                'custom_gmb',
            ],
            duration: 8, rounds: 2,
        },
        'review_sticky': {
            activities: [
                'maps_search_restaurants', 'maps_browse_places', 'maps_read_reviews', 'maps_view_photos', 'maps_directions',
                'maps_street_view', 'maps_coffee_shops', 'maps_hotels', 'maps_parks', 'maps_supermarkets',
                'maps_gas_stations', 'maps_pharmacies', 'maps_banks', 'maps_museums',
                'search_local', 'search_restaurants', 'search_food',
                'gmail_inbox',
                'custom_gmb',
            ],
            duration: 15, rounds: 3,
        },
        'full_warmup': {
            activities: [
                'gmail_inbox', 'gmail_read_email', 'gmail_check_spam', 'gmail_check_sent', 'gmail_scroll_inbox',
                'search_news', 'search_weather', 'search_tech', 'search_movies', 'search_sports',
                'search_restaurants', 'search_local', 'search_music', 'search_books',
                'youtube_browse_feed', 'youtube_trending', 'youtube_watch_video', 'youtube_music_playlist', 'youtube_shorts',
                'maps_search_restaurants', 'maps_browse_places', 'maps_read_reviews',
                'drive_browse', 'drive_recent', 'drive_shared',
                'account_security', 'account_activity', 'account_profile',
                'news_headlines', 'news_tech',
                'shopping_electronics', 'shopping_clothing',
                'photos_browse', 'translate_phrases', 'calendar_view', 'keep_browse',
            ],
            duration: 20, rounds: 2,
        },
        'local_presence': {
            activities: [
                'maps_search_restaurants', 'maps_browse_places', 'maps_read_reviews', 'maps_view_photos',
                'maps_directions', 'maps_street_view', 'maps_coffee_shops', 'maps_hotels',
                'maps_gas_stations', 'maps_parks', 'maps_shopping_malls', 'maps_pharmacies',
                'maps_banks', 'maps_supermarkets', 'maps_museums', 'maps_gyms',
                'search_local', 'search_restaurants', 'search_food', 'search_realestate',
                'custom_gmb',
            ],
            duration: 12, rounds: 2,
        },
        'social_engage': {
            activities: [
                'youtube_browse_feed', 'youtube_trending', 'youtube_watch_video', 'youtube_shorts',
                'youtube_gaming', 'youtube_cooking', 'youtube_news', 'youtube_comedy', 'youtube_music_playlist',
                'news_headlines', 'news_tech', 'news_sports', 'news_entertainment',
                'shopping_electronics', 'shopping_clothing', 'shopping_deals',
                'gmail_inbox', 'gmail_read_email',
                'search_news', 'search_movies', 'search_sports',
            ],
            duration: 10, rounds: 2,
        },
    };

    async function startHealth() {
        const isSmartMode = !!(document.getElementById('healthSmartPanel')?.style.display !== 'none');
        const profileIds = _healthChecked.size > 0 ? Array.from(_healthChecked) : [];
        const workers = parseInt(document.getElementById('healthWorkers')?.value || '3', 10);
        const country = document.getElementById('healthCountry')?.value || 'US';
        let activities, rounds, duration, gmbName, gmbAddress, smartGoal = '';

        if (isSmartMode) {
            // Smart mode — use preset
            smartGoal = document.querySelector('input[name="healthSmartGoal"]:checked')?.value || 'gmail_trust';
            const preset = _SMART_PRESETS[smartGoal] || _SMART_PRESETS['gmail_trust'];
            activities = [...preset.activities];
            rounds = parseInt(document.getElementById('healthRounds')?.value || String(preset.rounds), 10);
            duration = parseInt(document.getElementById('healthDuration')?.value || String(preset.duration), 10);
            gmbName = (document.getElementById('healthSmartGmbName')?.value || '').trim();
            gmbAddress = (document.getElementById('healthSmartGmbAddress')?.value || '').trim();
        } else {
            // Manual mode
            activities = Array.from(document.querySelectorAll('#healthManualPanel .health-act-item input[type="checkbox"]:checked')).map(cb => cb.value);
            rounds = parseInt(document.getElementById('healthRounds')?.value || '1', 10);
            duration = parseInt(document.getElementById('healthDuration')?.value || '0', 10);
            gmbName = (document.getElementById('healthGmbName')?.value || '').trim();
            gmbAddress = (document.getElementById('healthGmbAddress')?.value || '').trim();
        }

        // Auto-add custom_gmb if GMB fields filled
        if (gmbName && gmbAddress && !activities.includes('custom_gmb')) {
            activities.unshift('custom_gmb');
        }
        if (activities.length === 0) { App.toast('Select at least one activity', 'error'); return; }

        closeHealthModal();
        try {
            const data = await _api('/api/profiles/run-health', {
                method: 'POST',
                body: JSON.stringify({
                    num_workers: workers, activities, profile_ids: profileIds, country,
                    rounds, duration_minutes: duration,
                    gmb_name: gmbName, gmb_address: gmbAddress,
                    smart_goal: smartGoal,
                })
            });
            if (data.success) {
                const modeLabel = isSmartMode ? `Smart: ${smartGoal.replace(/_/g,' ')}` : 'Manual';
                App.toast(`Health started (${modeLabel}) on ${data.total} profile(s)`, 'success');
                _startOpProgress('health');
                _startStatusPolling();
            }
            else App.toast(data.message || data.error || 'Failed', 'error');
        } catch (e) { App.toast('Health error', 'error'); }
    }

    async function cleanupOrphans() {
        try {
            const data = await _api('/api/profiles/cleanup', { method: 'POST' });
            if (data.success) App.toast(`Cleanup done. Removed ${data.removed || 0} orphan folders.`, 'success');
        } catch (e) { App.toast('Cleanup error', 'error'); }
    }

    // ── Bulk Proxy modal ───────────────────────────────────────────────────
    async function _openBulkProxyModal() {
        const ov = _$('bulkProxyModalOverlay');
        if (!ov) return;
        ov.classList.add('active');
        // Populate group dropdown from counts endpoint (cheap)
        try {
            const r = await App.apiFetch('/api/profiles/counts');
            const d = await r.json();
            const groups = (d && d.groups) || [];
            const sel = _$('bulkProxyGroup');
            if (sel) {
                sel.innerHTML = groups.map(g => `<option value="${_esc(g)}">${_esc(g)}</option>`).join('');
            }
        } catch (e) { /* leave empty */ }
        _bulkProxyUpdateCount();
        // If a job is already running (user closed the modal mid-run),
        // pick the progress display back up.
        try {
            const r = await App.apiFetch('/api/profiles/bulk-proxy/status');
            const s = await r.json();
            if (s && s.running) {
                _bulkProxyShowProgress();
                _startBulkProxyPoll(() => loadProfiles());
            } else {
                const el = _$('bulkProxyProgress');
                if (el) el.style.display = 'none';
            }
        } catch (e) { /* ignore */ }
    }

    function _closeBulkProxyModal() {
        const ov = _$('bulkProxyModalOverlay');
        if (ov) ov.classList.remove('active');
    }

    // Resolve the scope picker's current selection into a request body
    // payload that backend `_resolve_proxy_scope` understands.
    function _bulkProxyScopeBody() {
        const scope = (_$('bulkProxyScope') || {}).value || 'all';
        if (scope === 'group') {
            const g = (_$('bulkProxyGroup') || {}).value || '';
            return { group: g };
        }
        return { all: true };
    }

    async function _bulkProxyUpdateCount() {
        const body = _bulkProxyScopeBody();
        const out = _$('bulkProxyScopeCount');
        const grpEl = _$('bulkProxyGroup');
        const scope = (_$('bulkProxyScope') || {}).value || 'all';
        if (grpEl) grpEl.style.display = scope === 'group' ? '' : 'none';
        // Use the same listing API the rest of the UI does so the count
        // matches what the user sees in the table.
        try {
            const qs = body.group ? `&group=${encodeURIComponent(body.group)}` : '';
            const r = await App.apiFetch(`/api/profiles?per_page=1${qs}`);
            const d = await r.json();
            if (out) out.textContent = `${d.total || 0} profile${(d.total||0) === 1 ? '' : 's'}`;
        } catch (e) {
            if (out) out.textContent = '— profiles';
        }
    }

    // ── Bulk-proxy progress polling ────────────────────────────────────
    let _bpPollTimer = null;
    function _bulkProxyShowProgress() {
        const el = _$('bulkProxyProgress');
        if (el) el.style.display = '';
        ['bulkProxyApplyBtn', 'bulkProxyTurnOnBtn', 'bulkProxyTurnOffBtn']
            .forEach(id => { const b = _$(id); if (b) b.disabled = true; });
    }
    function _bulkProxyHideProgress() {
        ['bulkProxyApplyBtn', 'bulkProxyTurnOnBtn', 'bulkProxyTurnOffBtn']
            .forEach(id => { const b = _$(id); if (b) b.disabled = false; });
    }
    function _bulkProxyRenderProgress(s) {
        const t = _$('bulkProxyProgressText');
        const p = _$('bulkProxyProgressPct');
        const f = _$('bulkProxyProgressFill');
        const c = _$('bulkProxyProgressCurrent');
        const total = s.total || 0, done = s.done || 0;
        const pct = total ? Math.round(done * 100 / total) : 0;
        const opLabel = s.op === 'set' ? 'Setting proxies'
                      : (s.op === 'toggle'
                            ? (s.extra && s.extra.enabled ? 'Turning proxy ON' : 'Turning proxy OFF')
                            : 'Working');
        const verbing = s.running ? `${opLabel}…` : (done >= total ? '✓ Done.' : opLabel);
        if (t) t.textContent = `${verbing}  ${done}/${total} · ${s.ok || 0} ok · ${s.failed || 0} skipped/failed`;
        if (p) p.textContent = pct + '%';
        if (f) f.style.width = pct + '%';
        if (c) c.textContent = s.current_email ? `Current: ${s.current_email}` : '';
    }
    function _startBulkProxyPoll(onDone) {
        if (_bpPollTimer) clearInterval(_bpPollTimer);
        const tick = async () => {
            try {
                const r = await App.apiFetch('/api/profiles/bulk-proxy/status');
                const s = await r.json();
                _bulkProxyRenderProgress(s);
                if (!s.running) {
                    clearInterval(_bpPollTimer); _bpPollTimer = null;
                    _bulkProxyHideProgress();
                    if (typeof onDone === 'function') onDone(s);
                }
            } catch (e) { /* keep polling */ }
        };
        tick();
        _bpPollTimer = setInterval(tick, 500);
    }

    function _initBulkProxyEvents() {
        const scope = _$('bulkProxyScope');
        if (scope) scope.addEventListener('change', _bulkProxyUpdateCount);
        const grp = _$('bulkProxyGroup');
        if (grp) grp.addEventListener('change', _bulkProxyUpdateCount);

        _btn('bulkProxyApplyBtn', async () => {
            const lines = ((_$('bulkProxyLines') || {}).value || '').trim();
            if (!lines) {
                App.toast('Paste at least one proxy line', 'error');
                return;
            }
            const proxyCount = lines.split(/\r?\n/).filter(Boolean).length;
            const body = { ..._bulkProxyScopeBody(), proxy_lines: lines.split(/\r?\n/) };
            if (!confirm(`Apply ${proxyCount} proxies (round-robin) to the selected scope?`)) return;
            try {
                const data = await _api('/api/profiles/bulk-set-proxies', {
                    method: 'POST',
                    body: JSON.stringify(body),
                });
                if (!data.success) {
                    App.toast(data.message || 'Failed to start', 'error');
                    return;
                }
                _bulkProxyShowProgress();
                _startBulkProxyPoll((s) => {
                    App.toast(`Proxies applied: ${s.ok || 0} ok · ${s.failed || 0} failed (of ${s.total || 0})`, 'success');
                    loadProfiles();
                });
            } catch (e) { App.toast('Backend unreachable', 'error'); }
        });

        _btn('bulkProxyTurnOffBtn', async () => {
            if (!confirm('Turn proxy OFF for the selected scope?\n\nCurrent proxy is archived per-profile so you can restore it with Turn ON later.')) return;
            const body = { ..._bulkProxyScopeBody(), enabled: false };
            try {
                const data = await _api('/api/profiles/bulk-toggle-proxy', {
                    method: 'POST',
                    body: JSON.stringify(body),
                });
                if (!data.success) {
                    App.toast(data.message || 'Failed to start', 'error');
                    return;
                }
                _bulkProxyShowProgress();
                _startBulkProxyPoll((s) => {
                    App.toast(`Proxy OFF: ${s.ok || 0} updated · ${s.failed || 0} skipped (of ${s.total || 0})`, 'success');
                    loadProfiles();
                });
            } catch (e) { App.toast('Backend unreachable', 'error'); }
        });

        _btn('bulkProxyTurnOnBtn', async () => {
            if (!confirm('Turn proxy ON for the selected scope?\n\nRestores the proxy archived by the previous Turn OFF. Profiles with no archive are skipped — use Apply Proxies to assign new ones.')) return;
            const body = { ..._bulkProxyScopeBody(), enabled: true };
            try {
                const data = await _api('/api/profiles/bulk-toggle-proxy', {
                    method: 'POST',
                    body: JSON.stringify(body),
                });
                if (!data.success) {
                    App.toast(data.message || 'Failed to start', 'error');
                    return;
                }
                _bulkProxyShowProgress();
                _startBulkProxyPoll((s) => {
                    App.toast(`Proxy ON: ${s.ok || 0} restored · ${s.failed || 0} skipped (of ${s.total || 0})`, 'success');
                    loadProfiles();
                });
            } catch (e) { App.toast('Backend unreachable', 'error'); }
        });
    }

    // ── Google Drive backup / restore ──────────────────────────────────────
    function openDriveBackupModal() {
        const modal = document.getElementById('driveBackupModal');
        if (!modal) return;
        modal.style.display = 'flex';
        loadDriveStatus();
        loadDriveBackups();
    }

    async function loadDriveStatus() {
        const el = document.getElementById('driveBackupStatus');
        if (!el) return;
        try {
            const r = await App.apiFetch('/api/profiles/drive/status');
            const s = await r.json();
            const tgl = document.getElementById('driveAutoBackupToggle');
            const ivl = document.getElementById('driveAutoBackupInterval');
            if (tgl) tgl.checked = !!s.auto_backup;
            if (ivl) ivl.value = s.auto_backup_interval_hours || 24;
            if (s.configured) {
                el.innerHTML = '<i class="fas fa-check-circle" style="color:#22c55e;"></i> ' +
                    'Drive connected — backups go to folder ' +
                    '<code style="background:#1e293b;padding:1px 6px;border-radius:3px;font-size:11px;">' +
                    (s.folder_id || '?').slice(0, 12) + '…</code>';
            } else {
                let why = '';
                if (!s.has_token) why = 'OAuth token missing — run <code>python tools/gdrive_setup.py</code> on the host.';
                else if (!s.folder_id) why = 'No folder_id in <code>config/gdrive.json</code>.';
                el.innerHTML = '<i class="fas fa-exclamation-triangle" style="color:#f59e0b;"></i> ' +
                    'Drive NOT configured. ' + why;
            }
        } catch (e) {
            el.innerHTML = '<i class="fas fa-times-circle" style="color:#ef4444;"></i> ' +
                'Could not reach backend: ' + e.message;
        }
    }

    async function loadDriveBackups() {
        const list = document.getElementById('driveBackupList');
        if (!list) return;
        list.innerHTML = '<div style="padding:18px;text-align:center;color:#64748b;font-size:12px;">' +
                         '<i class="fas fa-spinner fa-spin"></i> Loading&hellip;</div>';
        try {
            const r = await App.apiFetch('/api/profiles/drive/backups');
            const d = await r.json();
            if (!d.success && d.message) {
                list.innerHTML = '<div style="padding:14px;color:#fca5a5;font-size:12px;">' + d.message + '</div>';
                return;
            }
            const backups = d.backups || [];
            if (!backups.length) {
                list.innerHTML = '<div style="padding:24px;text-align:center;color:#64748b;font-size:12px;">' +
                    'No backups yet. Click "Backup Now" to create your first one.</div>';
                return;
            }
            list.innerHTML = backups.map((b, i) => {
                const created = b.created ? new Date(b.created).toLocaleString() : '—';
                const sizeKb = b.size ? (b.size / 1024).toFixed(1) + ' KB' : '?';
                const cnt = b.profiles_count != null ? b.profiles_count + ' profiles' : '? profiles';
                const isLatest = i === 0;
                return '<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid #1e293b;">' +
                    '<div style="flex:1;min-width:0;">' +
                        '<div style="font-size:13px;color:#e2e8f0;font-weight:500;">' +
                            (isLatest ? '<span style="display:inline-block;background:#22c55e;color:#0f1629;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;margin-right:6px;">LATEST</span>' : '') +
                            cnt +
                        '</div>' +
                        '<div style="font-size:11px;color:#94a3b8;margin-top:2px;font-family:monospace;">' +
                            created + ' &middot; ' + sizeKb +
                        '</div>' +
                    '</div>' +
                    '<button class="btn btn-secondary btn-sm" data-restore-id="' + b.id + '" data-restore-name="' + (b.profiles_count || '?') + ' profiles">' +
                        '<i class="fas fa-cloud-download-alt"></i> Restore' +
                    '</button>' +
                '</div>';
            }).join('');
            // Wire up restore buttons
            list.querySelectorAll('button[data-restore-id]').forEach(btn => {
                btn.addEventListener('click', () => doRestoreFromDrive(
                    btn.getAttribute('data-restore-id'),
                    btn.getAttribute('data-restore-name')
                ));
            });
        } catch (e) {
            list.innerHTML = '<div style="padding:14px;color:#fca5a5;font-size:12px;">Error: ' + e.message + '</div>';
        }
    }

    async function doDriveBackupNow() {
        const btn = document.getElementById('driveBackupNowBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading…'; }
        try {
            const r = await App.apiFetch('/api/profiles/drive/backup', { method: 'POST' });
            const d = await r.json();
            if (d.success) {
                // Distinguish 3 cases: both saved, drive-only, local-only.
                const onDrive = !!d.file_id;
                const localPath = d.local_path || '';
                let msg = '';
                if (onDrive && localPath) {
                    msg = `Backup saved ✓ Drive + Local · ${d.profiles_count} profiles`;
                } else if (onDrive) {
                    msg = `Backup uploaded to Drive ✓ ${d.profiles_count} profiles (local copy failed)`;
                } else if (localPath) {
                    msg = `Backup saved LOCALLY ✓ ${d.profiles_count} profiles — Drive upload failed`;
                } else {
                    msg = `Backup ${d.profiles_count} profiles`;
                }
                App.toast(msg, onDrive && localPath ? 'success' : 'warn');
                if (localPath) {
                    console.log('[backup] local copy:', localPath);
                }
                await loadDriveBackups();
            } else {
                // Even on failure the local copy may have been written.
                const fallback = d.local_path ? ` (local copy still saved → ${d.local_path})` : '';
                App.toast((d.message || 'Backup failed') + fallback, 'error');
            }
        } catch (e) {
            App.toast('Backup error: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Backup Now'; }
        }
    }

    async function doRestoreFromDrive(fileId, label) {
        if (!(await App.confirm('Restore profiles from this backup?\n\n' +
                     'Backup: ' + label + '\n\n' +
                     'Your CURRENT profiles.json will be saved as a local .bak file ' +
                     'before being replaced. The app will reload after restore.', 'Restore', 'btn-primary', 'fa-undo'))) return;
        App.toast('Downloading backup…', 'info');
        try {
            const r = await App.apiFetch('/api/profiles/drive/restore', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_id: fileId })
            });
            const d = await r.json();
            if (d.success) {
                App.toast('Restored ' + d.restored_count + ' profiles ✓ Reloading…', 'success');
                setTimeout(() => location.reload(), 800);
            } else {
                App.toast(d.message || 'Restore failed', 'error');
            }
        } catch (e) {
            App.toast('Restore error: ' + e.message, 'error');
        }
    }

    async function setAutoBackup() {
        const tgl = document.getElementById('driveAutoBackupToggle');
        const ivl = document.getElementById('driveAutoBackupInterval');
        try {
            const r = await App.apiFetch('/api/profiles/drive/auto-backup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: tgl ? tgl.checked : false,
                    interval_hours: ivl ? parseInt(ivl.value, 10) || 24 : 24,
                })
            });
            const d = await r.json();
            if (d.success) {
                App.toast(d.auto_backup ? 'Auto-backup ON' : 'Auto-backup OFF', 'success');
            }
        } catch (e) { App.toast('Auto-backup error: ' + e.message, 'error'); }
    }

    async function doDriveReauthorize() {
        if (!(await App.confirm('Re-authorize Google Drive?\n\nA browser tab will open for you to log in and grant access. Once you finish, this app will continue automatically.\n\nUse this if you see "invalid_grant" errors.', 'Re-authorize', 'btn-primary', 'fa-key'))) return;
        const btn = document.getElementById('driveReauthBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting for browser…'; }
        App.toast('Opening browser for Drive login…', 'info');
        try {
            const r = await App.apiFetch('/api/profiles/drive/reauthorize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: '{}',
            });
            const d = await r.json();
            if (d.success) {
                App.toast('Drive re-authorized ✓', 'success');
                await loadDriveStatus();
                await loadDriveBackups();
            } else {
                App.toast(d.message || 'Re-auth failed', 'error');
            }
        } catch (e) {
            App.toast('Re-auth error: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-key"></i> Re-authorize'; }
        }
    }

    function setupDriveBackupModal() {
        const close = (id) => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        };
        document.getElementById('driveBackupModalClose')?.addEventListener('click', () => close('driveBackupModal'));
        document.getElementById('driveBackupModalCancelBtn')?.addEventListener('click', () => close('driveBackupModal'));
        document.getElementById('driveBackupNowBtn')?.addEventListener('click', doDriveBackupNow);
        document.getElementById('driveBackupRefreshBtn')?.addEventListener('click', loadDriveBackups);
        document.getElementById('driveReauthBtn')?.addEventListener('click', doDriveReauthorize);
        document.getElementById('driveAutoBackupToggle')?.addEventListener('change', setAutoBackup);
        document.getElementById('driveAutoBackupInterval')?.addEventListener('change', setAutoBackup);
    }

    async function restoreFromNst() {
        // Step 1: dry-run to see what's missing
        App.toast('Scanning NST for missing profiles…', 'info');
        let preview;
        try {
            preview = await _api('/api/profiles/restore-from-nst', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dry_run: true })
            });
        } catch (e) { App.toast('Restore scan failed: ' + e.message, 'error'); return; }

        if (!preview.success) { App.toast(preview.error || 'NST scan failed', 'error'); return; }

        const groupsList = Object.entries(preview.groups || {})
            .sort((a, b) => b[1] - a[1])
            .map(([g, c]) => `  • ${g}: ${c}`).join('\n');

        if (preview.missing === 0) {
            App.toast(`All ${preview.total_in_nst} NST profiles already present locally — nothing to restore.`, 'success');
            return;
        }

        const groupNames = Object.keys(preview.groups || {});
        const groupChoice = prompt(
            `NST has ${preview.total_in_nst} total profiles.\n` +
            `${preview.already_present} already in local registry.\n` +
            `${preview.missing} MISSING — can be restored.\n\n` +
            `Groups available in NST:\n${groupsList}\n\n` +
            `Type a group name to restore ONLY that group,\n` +
            `or leave EMPTY and click OK to restore ALL ${preview.missing} missing.\n` +
            `(Cancel to abort.)`,
            ''
        );
        if (groupChoice === null) return;

        const body = { dry_run: false };
        if (groupChoice.trim()) {
            if (!groupNames.includes(groupChoice.trim())) {
                App.toast(`Group "${groupChoice}" not found in NST`, 'error');
                return;
            }
            body.group = groupChoice.trim();
        }

        if (!(await App.confirm(`Restore profiles to local registry now?\n\n` +
                     (body.group ? `Group filter: ${body.group}\n` : `All groups\n`) +
                     `\nA backup of profiles.json will be made automatically.`, 'Restore', 'btn-primary', 'fa-undo'))) return;

        App.toast('Restoring… please wait.', 'info');
        try {
            const result = await _api('/api/profiles/restore-from-nst', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (result.success) {
                App.toast(`✓ Restored ${result.restored} profile(s). Reloading…`, 'success');
                if (typeof loadProfiles === 'function') await loadProfiles();
                else location.reload();
            } else {
                App.toast(result.error || 'Restore failed', 'error');
            }
        } catch (e) { App.toast('Restore error: ' + e.message, 'error'); }
    }

    async function checkProxy() {
        const host = _val('pmProxyHost').trim();
        const port = _val('pmProxyPort').trim();
        if (!host) { App.toast('Enter proxy host first', 'error'); return; }
        const resultEl = _$('pmProxyResult');
        if (resultEl) {
            resultEl.style.display = 'block';
            resultEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking proxy...';
        }
        // For now just show the proxy info — server-side check can be added later
        if (resultEl) {
            resultEl.innerHTML = `<i class="fas fa-check" style="color:#22c55e;"></i> Proxy: ${_esc(host)}:${_esc(port)} (check via server not yet wired)`;
        }
    }

    function parseProxyString() {
        const raw = _val('pmProxyPaste').trim();
        if (!raw) return;
        // Try common formats
        let host = '', port = '', user = '', pass = '', type = 'http';

        // socks5://user:pass@host:port or http(s)://user:pass@host:port
        const urlMatch = raw.match(/^(socks5|http|https):\/\/([^:]+):([^@]+)@([^:]+):(\d+)/);
        if (urlMatch) {
            type = urlMatch[1] === 'socks5' ? 'socks5' : 'http';
            user = urlMatch[2]; pass = urlMatch[3]; host = urlMatch[4]; port = urlMatch[5];
        } else if (raw.includes('@')) {
            // user:pass@host:port
            const [auth, hp] = raw.split('@');
            const [u, p] = auth.split(':');
            const [h, pt] = hp.split(':');
            user = u || ''; pass = p || ''; host = h || ''; port = pt || '';
        } else {
            // host:port:user:pass
            const parts = raw.split(':');
            if (parts.length >= 4) { host = parts[0]; port = parts[1]; user = parts[2]; pass = parts[3]; }
            else if (parts.length === 2) { host = parts[0]; port = parts[1]; }
        }

        if (host) {
            _setVal('pmProxyType', type);
            _setVal('pmProxyHost', host);
            _setVal('pmProxyPort', port);
            _setVal('pmProxyUser', user);
            _setVal('pmProxyPass', pass);
            _toggleProxyFields();
            App.toast('Proxy parsed', 'success');
        } else {
            App.toast('Could not parse proxy string', 'error');
        }
    }

    // ── Operation Progress Panel (Rich, multi-card) ────────────────────
    // Each running op gets its own card in the #opProgressStack container.
    // Per-op state lives in _opSessions keyed by type (e.g. 'batch-login').
    // The old _opType/_opPoll singletons are kept as ALIASES for the
    // most-recently-started session so any external readers still resolve.
    const _opSessions = new Map();  // type -> { card, poll, timer, startTime, everRunning, type }
    let _opPoll = null;          // alias for legacy reads (set to latest session's poll)
    let _opType = null;          // alias for legacy reads
    let _opStartTime = null;     // alias for legacy reads
    let _opTimerInterval = null; // alias for legacy reads
    let _opEverRunning = false;  // alias for legacy reads

    // DOM helpers
    function _opRole(card, role) { return card ? card.querySelector(`[data-role="${role}"]`) : null; }
    function _opSession(type) { return _opSessions.get(type) || null; }
    function _opPrimaryType() {
        // Legacy code reads _opType to know "is anything running" or to pick a stop endpoint.
        // Return the most recently started session's type as a sensible default.
        let latest = null, latestTime = 0;
        for (const s of _opSessions.values()) {
            if (s.startTime > latestTime) { latestTime = s.startTime; latest = s.type; }
        }
        return latest;
    }
    function _opRefreshAliases() {
        const t = _opPrimaryType();
        const s = t ? _opSessions.get(t) : null;
        _opType = t;
        _opPoll = s ? s.poll : null;
        _opStartTime = s ? s.startTime : null;
        _opTimerInterval = s ? s.timer : null;
        _opEverRunning = s ? s.everRunning : false;
    }

    // Operation type configs
    const _OP_CONFIGS = {
        'batch-login': { icon: 'fa-file-excel',   label: 'Batch Login',    successLbl: 'Logged In',   failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'relogin':     { icon: 'fa-sign-in-alt',  label: 'Re-Login',       successLbl: 'Re-Logged In',failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'appeal':      { icon: 'fa-gavel',        label: 'Appeal',         successLbl: 'Submitted',   failLbl: 'Refused',  pendingLbl: 'Remaining' },
        'review':      { icon: 'fa-star',         label: 'Write Review',   successLbl: 'Posted',      failLbl: 'Failed',  pendingLbl: 'Pending' },
        'proxy':       { icon: 'fa-plug',         label: 'Proxy Update',   successLbl: 'Updated',     failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'health':      { icon: 'fa-heartbeat',    label: 'Health Activity', successLbl: 'Done',       failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'setai':       { icon: 'fa-robot',        label: 'SetAI Hook',     successLbl: 'Hooked',      failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'delete':      { icon: 'fa-trash',        label: 'Delete Profiles', successLbl: 'Deleted',    failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'run-ops':     { icon: 'fa-cogs',         label: 'Run Operations',  successLbl: 'Done',       failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'gmb-review':  { icon: 'fa-link',         label: 'GMB Review URL',  successLbl: 'Resolved',   failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'live-check':  { icon: 'fa-satellite-dish', label: 'Live Status Check', successLbl: 'Live',     failLbl: 'Missing', pendingLbl: 'Remaining' },
        'fast-mode':   { icon: 'fa-bolt',          label: 'Fast Mode Apply',  successLbl: 'Updated',     failLbl: 'Failed',  pendingLbl: 'Remaining' },
        'bookmarks':   { icon: 'fa-bookmark',      label: 'Bookmarks Apply',  successLbl: 'Updated',     failLbl: 'Failed',  pendingLbl: 'Remaining' },
    };

    // Auto-detect running operations on page load / refresh AND periodically.
    // After a hard refresh the frontend forgets every running op; this scan
    // re-attaches a card for each backend job that's still running, so users
    // never lose their progress popups. It also brings back a popup that the
    // user accidentally closed (since backend is the source of truth).
    async function _autoDetectRunningOps() {
        if (!App.state || !App.state.serverOnline) return;
        try {
            const checks = [
                { type: 'run-ops',    url: '/api/profiles/ops-status' },
                { type: 'appeal',     url: '/api/profiles/appeal-status' },
                { type: 'health',     url: '/api/profiles/health-status' },
                { type: 'review',     url: '/api/profiles/review-status' },
                { type: 'gmb-review', url: '/api/gmb-to-review/status' },
                { type: 'live-check', url: '/api/profiles/live-check/status' },
            ];
            // Run all status checks in parallel — start a card for EACH running op.
            // Skip types that already have a session (idempotency lives in _startOpProgress).
            await Promise.all(checks.map(async (chk) => {
                try {
                    if (_opSessions.has(chk.type)) return;
                    const res = await App.apiFetch(chk.url);
                    const st = await res.json();
                    if (st && st.running) _startOpProgress(chk.type);
                } catch (e) { /* ignore */ }
            }));

            // Bulk delete progress
            try {
                if (!_opSessions.has('delete')) {
                    const delRes = await App.apiFetch('/api/profiles/delete-bulk-status');
                    const delData = await delRes.json();
                    if (delData.success && delData.progress && delData.progress.status === 'processing') {
                        _startOpProgress('delete');
                    }
                }
            } catch (e) { /* ignore */ }

            // Batch login — dedicated endpoint
            try {
                if (!_opSessions.has('batch-login')) {
                    const st = await _api('/api/profiles/batch-login-status');
                    if (st && (st.running || st.status === 'processing')) {
                        _startOpProgress('batch-login');
                    }
                }
            } catch (e) { /* ignore */ }

            // Bulk re-login — dedicated endpoint (no longer reads /api/progress)
            try {
                if (!_opSessions.has('relogin')) {
                    const st = await _api('/api/profiles/bulk-relogin-status');
                    if (st && (st.running || st.status === 'processing')) {
                        _startOpProgress('relogin');
                    }
                }
            } catch (e) { /* ignore */ }

            // Fast Mode bulk apply
            try {
                if (!_opSessions.has('fast-mode')) {
                    const st = await _api('/api/profiles/bulk-perf-status');
                    if (st && (st.running || st.status === 'processing')) {
                        _startOpProgress('fast-mode');
                    }
                }
            } catch (e) { /* ignore */ }

            // Bookmark bulk apply
            try {
                if (!_opSessions.has('bookmarks')) {
                    const st = await _api('/api/profiles/bulk-bookmark-status');
                    if (st && (st.running || st.status === 'processing')) {
                        _startOpProgress('bookmarks');
                    }
                }
            } catch (e) { /* ignore */ }
        } catch (e) { /* ignore */ }
    }

    // Run continuously every 8s so even if a user closes a popup or the
    // initial post-auth scan missed something, the popups come back.
    let _autoDetectInterval = null;
    function _startAutoDetectLoop() {
        if (_autoDetectInterval) return;
        _autoDetectInterval = setInterval(_autoDetectRunningOps, 8000);
    }
    // Kick once immediately and start the loop. App.js also calls
    // _autoDetectRunningOps after auth — that one-shot stays fine.
    setTimeout(() => { _autoDetectRunningOps(); _startAutoDetectLoop(); }, 1500);

    // When the tab becomes visible again, do an immediate scan.
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) _autoDetectRunningOps();
    });

    // Expose for app.js to call after auth
    App._autoDetectRunningOps = _autoDetectRunningOps;

    function _formatTimer(ms) {
        const s = Math.floor(ms / 1000);
        const m = Math.floor(s / 60);
        const sec = s % 60;
        return `${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
    }

    // Per-card stat setters — card may be a session object, a card DOM,
    // or omitted (falls back to the primary card so legacy callers still work).
    function _resolveCard(cardOrType) {
        if (!cardOrType) {
            const t = _opPrimaryType();
            return t ? (_opSessions.get(t) || {}).card : null;
        }
        if (typeof cardOrType === 'string') {
            return (_opSessions.get(cardOrType) || {}).card || null;
        }
        if (cardOrType.card) return cardOrType.card;
        return cardOrType;  // already a card element
    }
    function _setOpStat(role, val, cardOrType) {
        const card = _resolveCard(cardOrType);
        if (!card) return;
        const el = _opRole(card, role);
        if (!el) return;
        const valEl = el.querySelector('.op-stat-val');
        if (valEl) valEl.textContent = val;
    }
    function _setOpStatLabel(role, lbl, cardOrType) {
        const card = _resolveCard(cardOrType);
        if (!card) return;
        const el = _opRole(card, role);
        if (!el) return;
        const lblEl = el.querySelector('.op-stat-lbl');
        if (lblEl) lblEl.textContent = lbl;
    }

    function _startOpProgress(type) {
        // Idempotent: same op already running → just keep it. The auto-detector
        // calls _startOpProgress(type) on every poll; we must not spawn duplicate
        // cards or duplicate intervals for the same type.
        const existing = _opSessions.get(type);
        if (existing && document.body.contains(existing.card)) {
            return;
        }

        const stack = document.getElementById('opProgressStack');
        const tpl   = document.getElementById('opProgressCardTemplate');
        if (!stack || !tpl) return;

        // Clone a fresh card from the template
        const frag = tpl.content.cloneNode(true);
        const card = frag.querySelector('[data-op-card]');
        if (!card) return;
        card.dataset.opType = type;
        stack.appendChild(card);

        const cssType = 'op-type-' + type;
        const iconW   = _opRole(card, 'iconWrap');
        const icon    = _opRole(card, 'icon');
        const label   = _opRole(card, 'label');
        const sublabel = _opRole(card, 'sublabel');
        const bar     = _opRole(card, 'bar');
        const count   = _opRole(card, 'count');
        const pctEl   = _opRole(card, 'pct');
        const timerEl = _opRole(card, 'timer');
        const stopBtn = _opRole(card, 'stopBtn');

        const cfg = _OP_CONFIGS[type] || _OP_CONFIGS['health'];

        // Set icon + colors based on type
        if (icon) icon.className = 'fas ' + cfg.icon;
        if (iconW) { iconW.className = 'op-icon-wrap ' + cssType; }
        if (label) label.textContent = cfg.label;
        if (sublabel) sublabel.textContent = 'Starting...';
        if (bar) { bar.className = 'op-bar-fill ' + cssType; bar.style.width = '0%'; }
        if (count) count.textContent = '0 / 0';
        if (pctEl) pctEl.textContent = '0%';
        if (timerEl) timerEl.textContent = '00:00';

        // Stat labels — pass type so setters target this card
        _setOpStatLabel('statSuccess', cfg.successLbl, type);
        _setOpStatLabel('statFailed', cfg.failLbl, type);
        _setOpStatLabel('statPending', cfg.pendingLbl, type);
        _setOpStat('statTotal', '0', type);
        _setOpStat('statSuccess', '0', type);
        _setOpStat('statFailed', '0', type);
        _setOpStat('statPending', '0', type);

        // Stop button is wired per-card; delegated handlers also exist for
        // legacy code paths but binding directly here is the simplest.
        if (stopBtn) {
            stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop';
            stopBtn.dataset.completed = '';
            stopBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isCompleted = stopBtn.dataset.completed === 'true';
                _stopOpProgress(type, !isCompleted);
            });
        }

        // Create the session record. Poll/timer fill in below.
        const session = {
            type,
            card,
            poll: null,
            timer: null,
            startTime: Date.now(),
            everRunning: false,
        };
        _opSessions.set(type, session);
        _opRefreshAliases();

        // Per-card timer
        session.timer = setInterval(() => {
            if (timerEl) timerEl.textContent = _formatTimer(Date.now() - session.startTime);
        }, 1000);

        // Per-card status polling
        session.poll = setInterval(async () => {
            try {
                let done = 0, total = 0, successCount = 0, failedCount = 0, isRunning = true;
                let reportPath = null, currentAccount = '', stepLabel = '';

                if (type === 'delete') {
                    // Bulk delete progress endpoint
                    const st = await _api('/api/profiles/delete-bulk-status');
                    if (st.success && st.progress) {
                        const p = st.progress;
                        total = p.total || 0;
                        done = (p.deleted || 0) + (p.failed || 0);
                        successCount = p.deleted || 0;
                        failedCount = p.failed || 0;
                        isRunning = p.status === 'processing';
                        currentAccount = p.current_account || p.current_profile || '';
                        stepLabel = p.step_label || p.progress || '';
                    }
                } else if (type === 'batch-login') {
                    // Dedicated endpoint — no longer shares /api/progress with bulk-relogin.
                    const st = await _api('/api/profiles/batch-login-status');
                    total = st.total || 0;
                    successCount = st.success || 0;
                    failedCount = st.failed || 0;
                    done = successCount + failedCount;
                    isRunning = !!(st.running) || st.status === 'processing';
                    currentAccount = st.current_account || '';
                    stepLabel = st.step_label || 'Batch Login';
                    reportPath = st.report_path || '';
                } else if (type === 'relogin') {
                    // Dedicated bulk-relogin endpoint — independent of /api/progress
                    // so it survives concurrent Live Check / Batch Login runs.
                    const st = await _api('/api/profiles/bulk-relogin-status');
                    total = st.total || 0;
                    successCount = st.success || 0;
                    failedCount = st.failed || 0;
                    done = st.done || (successCount + failedCount);
                    isRunning = !!(st.running) || st.status === 'processing';
                    currentAccount = st.current_account || '';
                    stepLabel = st.step_label || 'Bulk Re-Login';
                    reportPath = st.report_path || '';
                } else if (type === 'fast-mode') {
                    const st = await _api('/api/profiles/bulk-perf-status');
                    total = st.total || 0;
                    successCount = st.success || 0;
                    failedCount = st.failed || 0;
                    done = st.done || (successCount + failedCount);
                    isRunning = !!(st.running) || st.status === 'processing';
                    currentAccount = st.current_account || '';
                    stepLabel = st.step_label || 'Fast Mode';
                } else if (type === 'bookmarks') {
                    const st = await _api('/api/profiles/bulk-bookmark-status');
                    total = st.total || 0;
                    successCount = st.success || 0;
                    failedCount = st.failed || 0;
                    done = st.done || (successCount + failedCount);
                    isRunning = !!(st.running) || st.status === 'processing';
                    currentAccount = st.current_account || '';
                    stepLabel = st.step_label || 'Bookmarks';
                } else if (type === 'gmb-review') {
                    const st = await _api('/api/gmb-to-review/status');
                    done = st.done || 0;
                    total = st.total || 0;
                    isRunning = !!st.running;
                    successCount = st.success || 0;
                    failedCount = st.failed || 0;
                    reportPath = st.report_path;
                    currentAccount = st.current_url || st.current_profile || '';
                    stepLabel = st.step_label || '';
                } else if (type === 'live-check') {
                    const st = await _api('/api/profiles/live-check/status');
                    done = st.done || 0;
                    total = st.total || 0;
                    isRunning = !!st.running;
                    successCount = st.live || 0;
                    failedCount  = st.not_live || 0;
                    reportPath = st.report_path;
                    currentAccount = st.current_url || st.current_profile || '';
                    stepLabel = st.step_label || '';
                    // Show write-phase progress or current URL in sublabel
                    if (isRunning && st.current_url) {
                        if (sublabel) sublabel.textContent = st.current_url;
                    }
                } else {
                    let endpoint;
                    if (type === 'run-ops') endpoint = '/api/profiles/ops-status';
                    else if (type === 'appeal') endpoint = '/api/profiles/appeal-status';
                    else if (type === 'review') endpoint = '/api/profiles/review-status';
                    else endpoint = '/api/profiles/health-status';

                    const st = await _api(endpoint);
                    done = st.done || 0;
                    total = st.total || 0;
                    isRunning = !!st.running;
                    reportPath = st.report_path;
                    currentAccount = st.current_profile || st.current_account || '';
                    stepLabel = st.progress || st.step_label || '';

                    if (st.results && st.results.length) {
                        successCount = st.results.filter(r => r.status === 'success' || r.ok || r.success === true).length;
                        failedCount  = st.results.filter(r => r.status === 'failed' || r.status === 'error' || r.ok === false || r.success === false).length;
                    } else {
                        successCount = st.success || done;
                        failedCount  = st.failed || 0;
                    }
                }

                if (isRunning) { session.everRunning = true; _opRefreshAliases(); }

                // Suppress premature "Complete" — if backend hasn't started yet
                // (e.g. server is still parsing the sheet plan), keep showing
                // "Starting..." for up to 5 minutes instead of flipping to done.
                const startupGraceMs = 5 * 60 * 1000;
                const inStartupGrace = !session.everRunning &&
                    session.startTime &&
                    (Date.now() - session.startTime) < startupGraceMs;

                const pct = total > 0 ? Math.round((done / total) * 100) : 0;
                const remaining = Math.max(0, total - done);

                // Update panel
                if (count) count.textContent = `${done} / ${total}`;
                if (pctEl) pctEl.textContent = pct + '%';
                if (bar) bar.style.width = `${pct}%`;
                if (sublabel) {
                    sublabel.textContent = isRunning
                        ? (stepLabel || `Processing... ${done}/${total}`)
                        : (inStartupGrace ? 'Starting…' : 'Complete');
                }
                _setOpStat('statTotal', total, type);
                _setOpStat('statSuccess', successCount, type);
                _setOpStat('statFailed', failedCount, type);
                _setOpStat('statPending', remaining, type);

                // Also update main Dashboard overview for ALL operation types
                {
                    const overviewBar  = document.getElementById('progressBar');
                    const overviewPct  = document.getElementById('progressPercentage');
                    const overviewTxt  = document.getElementById('progressText');
                    const overviewCur  = document.getElementById('currentAccount');
                    const overviewStep = document.getElementById('stepIndicator');
                    if (overviewBar) overviewBar.style.width = pct + '%';
                    if (overviewPct) overviewPct.innerText = pct + '%';
                    if (overviewTxt) overviewTxt.innerText = `${cfg.label}: ${done} / ${total}`;
                    if (overviewCur) overviewCur.innerText = isRunning
                        ? (currentAccount ? `${cfg.label.toUpperCase()}: ${currentAccount} (${done}/${total})` : `${cfg.label.toUpperCase()} RUNNING... (${done}/${total})`)
                        : `${cfg.label.toUpperCase()} COMPLETE`;
                    if (overviewStep) overviewStep.innerText = cfg.label.toUpperCase();
                    const _updCard = (id, val, lbl, ico) => {
                        const el = document.getElementById(id);
                        if (!el) return;
                        el.innerText = val;
                        const card = el.closest('.stat-card');
                        if (!card) return;
                        const lblEl = card.querySelector('.stat-label');
                        if (lblEl) lblEl.innerText = lbl;
                        const icoEl = card.querySelector('.stat-icon i');
                        if (icoEl) icoEl.className = 'fas ' + ico;
                    };
                    _updCard('totalAccounts', total,        'Total Profiles',  'fa-users');
                    _updCard('totalSuccess',  successCount, cfg.successLbl,    'fa-check-circle');
                    _updCard('totalFailed',   failedCount,  cfg.failLbl,       'fa-times-circle');
                    _updCard('totalPending',  remaining,    cfg.pendingLbl,    'fa-hourglass-half');
                }

                if (!isRunning && !inStartupGrace) {
                    // Stop THIS session's intervals but keep its card visible
                    // with final state until the user clicks Close.
                    if (session.poll) { clearInterval(session.poll); session.poll = null; }
                    if (session.timer) { clearInterval(session.timer); session.timer = null; }
                    _opRefreshAliases();

                    if (sublabel) sublabel.textContent = 'Complete';
                    if (bar) bar.style.width = '100%';
                    if (pctEl) pctEl.textContent = '100%';

                    // Switch this card's Stop button to Close
                    if (stopBtn) {
                        stopBtn.innerHTML = '<i class="fas fa-times"></i> Close';
                        stopBtn.dataset.completed = 'true';
                    }

                    // Show toast notifications
                    if (type === 'live-check') {
                        const msg = reportPath || `Live: ${successCount}, Missing: ${failedCount}`;
                        App.toast(`Live Check complete — ${msg}`, 'success');
                    } else if (type === 'review' && reportPath) {
                        _showReviewReportReady(reportPath, done, total);
                    } else if (type === 'review') {
                        App.toast(`Write Review complete: ${done}/${total} done`, 'success');
                    } else if (type === 'delete') {
                        App.toast(`Delete complete: ${successCount} deleted, ${failedCount} failed`, 'success');
                    } else if (type === 'run-ops') {
                        App.toast(`Operations complete: ${successCount} done, ${failedCount} failed`, 'success');
                    } else if (type === 'batch-login') {
                        App.toast(`Batch Login complete: ${successCount} logged in, ${failedCount} failed`, 'success');
                    } else if (type === 'relogin') {
                        App.toast(`Re-Login complete: ${successCount} success, ${failedCount} failed`, 'success');
                        if (reportPath) _showReloginReportReady(reportPath, { success: successCount, failed: failedCount });
                    } else if (type === 'gmb-review') {
                        App.toast(`GMB Review URLs: ${successCount} resolved, ${failedCount} failed`, 'success');
                        // Auto-download the generated Excel
                        if (reportPath) {
                            try {
                                const dlResp = await App.apiFetch('/api/gmb-to-review/download');
                                if (dlResp.ok) {
                                    const cd = dlResp.headers.get('Content-Disposition') || '';
                                    const m = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                                    const fn = m ? m[1].replace(/['"]/g, '') : 'GMB_Review_URLs.xlsx';
                                    const blob = await dlResp.blob();
                                    const u = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = u; a.download = fn;
                                    document.body.appendChild(a); a.click();
                                    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(u); }, 1000);
                                }
                            } catch(e) { /* ignore download error */ }
                            // Refresh Reports tab so file is always accessible
                            if (typeof App !== 'undefined' && App.loadReports) setTimeout(() => App.loadReports(), 1000);
                        }
                    }
                    loadProfiles();
                }
            } catch (e) { /* ignore */ }
        }, 2000);
    }

    function _showReloginReportReady(reportPath, p) {
        const ok = p.success || 0, fail = p.failed || 0;
        App.toast(`✓ Re-Login Report Ready — ${ok} success, ${fail} failed`, 'success');
        if (typeof App !== 'undefined' && App.loadReports) setTimeout(() => App.loadReports(), 1000);
        if (window.electronAPI && window.electronAPI.openPath) {
            window.electronAPI.openPath(reportPath);
        }
    }

    function _showReviewReportReady(reportPath, done, total) {
        const live = reportPath.match(/(\d+)live/)?.[1] || '?';
        App.toast(`✓ Review Report Ready — ${live} live, ${done}/${total} done`, 'success');
        // Refresh Results tab so report shows up there immediately
        if (typeof App !== 'undefined' && App.loadReports) {
            setTimeout(() => App.loadReports(), 1000);
        }
        // Show a persistent notification bar if possible
        const bar = document.getElementById('reviewReportBar');
        if (bar) {
            bar.style.display = 'flex';
            const link = bar.querySelector('#reviewReportPath');
            if (link) { link.textContent = reportPath.split(/[\\/]/).pop(); link.dataset.path = reportPath; }
        }
    }

    function _stopOpProgress(typeOrEvent, sendStop = true) {
        // Legacy callers do _stopOpProgress() or _stopOpProgress(true) with no type
        // — resolve to the primary (most-recently-started) session.
        let type;
        if (typeof typeOrEvent === 'string') {
            type = typeOrEvent;
        } else {
            // First arg may be a boolean for sendStop (legacy signature)
            if (typeof typeOrEvent === 'boolean') sendStop = typeOrEvent;
            type = _opPrimaryType();
        }
        if (!type) return;

        const session = _opSessions.get(type);
        if (session) {
            if (session.poll) { clearInterval(session.poll); session.poll = null; }
            if (session.timer) { clearInterval(session.timer); session.timer = null; }
        }

        if (sendStop) {
            let endpoint;
            if (type === 'appeal') endpoint = '/api/profiles/stop-appeal';
            else if (type === 'review') endpoint = '/api/profiles/stop-review';
            else if (type === 'live-check') endpoint = '/api/profiles/live-check/cancel';
            else endpoint = '/api/profiles/stop-health';
            _api(endpoint, { method: 'POST' }).catch(() => {});
        }

        // Remove the card with a small slide-out animation, then drop session.
        if (session && session.card) {
            session.card.classList.add('op-card-closing');
            setTimeout(() => {
                try { session.card.remove(); } catch (e) {}
                _opSessions.delete(type);
                _opRefreshAliases();
            }, 220);
        } else {
            _opSessions.delete(type);
            _opRefreshAliases();
        }

        // Auto-refresh Report Ledger so new report appears immediately
        if (typeof App !== 'undefined' && App.loadReports) {
            setTimeout(() => App.loadReports(), 1500);
        }
    }

    // ── Status polling (real-time sync) ────────────────────────────────
    // Polls every 2s while any browser is open. Auto-stops when none are running.

    function _startStatusPolling() {
        if (_statusPoll) return;  // already polling
        _statusPoll = setInterval(async () => {
            try {
                await loadProfiles();
                // Auto-stop polling when there are no open/launching browsers
                // AND we're past the "hold" window. The hold window keeps the
                // loop alive for ~90s after Re-Login so the status flip lands
                // in the UI even after the browser has closed.
                const rows = document.querySelectorAll('.pm-close-btn, .pm-launching-btn');
                if (rows.length === 0 && Date.now() > _statusPollHoldUntil && _statusPoll) {
                    clearInterval(_statusPoll);
                    _statusPoll = null;
                }
            } catch (e) { /* ignore */ }
        }, 2000);
    }

    function _stopStatusPolling() {
        if (_statusPoll) { clearInterval(_statusPoll); _statusPoll = null; }
    }

    // ── File browser ────────────────────────────────────────────────────

    async function browseFile(inputId) {
        try {
            if (window.electronAPI && window.electronAPI.selectFile) {
                const filePath = await window.electronAPI.selectFile();
                if (filePath) _setVal(inputId, filePath);
            } else if (window.electronAPI && window.electronAPI.selectFolder && inputId === 'profileStoragePath') {
                const folderPath = await window.electronAPI.selectFolder();
                if (folderPath) _setVal(inputId, folderPath);
            } else {
                App.toast('File picker not available', 'error');
            }
        } catch (e) { App.toast('File picker error', 'error'); }
    }

    // ══════════════════════════════════════════════════════════════════════
    // SETUP — Wire up all buttons and events
    // ══════════════════════════════════════════════════════════════════════

    App.loadProfiles = loadProfiles;

    App.setupProfilesPage = function () {
        // Search — reset to page 1 on every search change so we don't land
        // on an out-of-range page when the result set shrinks.
        const searchEl = _$('profileSearch');
        if (searchEl) {
            searchEl.addEventListener('input', () => {
                clearTimeout(_searchDebounce);
                _searchDebounce = setTimeout(() => _resetPageAndReload(), 300);
            });
        }

        // Group filter dropdown
        const groupFilterEl = document.getElementById('pmGroupFilter');
        if (groupFilterEl) {
            const _syncDeleteGroupBtn = () => {
                const delBtn = _$('pmDeleteGroupBtn');
                if (!delBtn) return;
                // Show the inline trash only when a specific non-default group is picked
                delBtn.style.display =
                    (groupFilterEl.value && groupFilterEl.value !== 'default') ? '' : 'none';
            };
            groupFilterEl.addEventListener('change', () => {
                _currentGroup = groupFilterEl.value;
                _syncDeleteGroupBtn();
                _resetPageAndReload();
            });
            // Run once on bind so the initial state is correct
            _syncDeleteGroupBtn();
        }

        // Table Sort Headers
        document.querySelectorAll('.pm-sortable').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.sort;
                if (_currentSort.column === col) {
                    _currentSort.dir = _currentSort.dir === 'asc' ? 'desc' : 'asc';
                } else {
                    _currentSort.column = col;
                    _currentSort.dir = 'asc';
                }
                
                // Update UI classes
                document.querySelectorAll('.pm-sortable').forEach(el => {
                    el.classList.remove('active', 'desc');
                });
                th.classList.add('active');
                if (_currentSort.dir === 'desc') th.classList.add('desc');

                _resetPageAndReload();
            });
        });

        // Filter buttons
        document.querySelectorAll('.pm-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.pm-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                _currentFilter = btn.dataset.filter;
                _resetPageAndReload();
            });
        });

        // Review-stats Sync button + scope dropdown (Task 11)
        _initReviewStatsSync();

        // Review-stats drill-down modal (Task 13)
        _initReviewStatsModal();

        // Bulk Proxy modal — wire up scope picker + apply / on / off buttons
        _initBulkProxyEvents();

        // Pagination controls — Prev/Next buttons + per-page selector
        _btn('pmPagePrevBtn', () => {
            if (_currentPage > 1) {
                _currentPage--;
                loadProfiles();
            }
        });
        _btn('pmPageNextBtn', () => {
            if (_currentPage < _lastTotalPages) {
                _currentPage++;
                loadProfiles();
            }
        });
        const perPageEl = _$('pmPerPage');
        if (perPageEl) {
            perPageEl.addEventListener('change', () => {
                const v = parseInt(perPageEl.value, 10);
                if (v >= 10 && v <= 10000) {
                    _perPage = v;
                    _resetPageAndReload();
                }
            });
        }

        // Export ALL profiles to Excel — sibling of Bookmark All. Pagination
        // caps the selectable rows at 50, so this button bypasses the
        // _selectedIds path entirely and asks the backend to export every
        // profile in one shot via the `all: true` flag.
        _btn('profileExportAllBtn', async () => {
            const btn = _$('profileExportAllBtn');
            if (!confirm('Export EVERY profile to Excel?\n\nThis ignores any filter, search, or page selection — every profile in the database gets exported.')) return;
            const origHTML = btn ? btn.innerHTML : '';
            if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting…'; }
            try {
                const resp = await App.apiFetch('/api/profiles/export-excel', {
                    method: 'POST',
                    body: JSON.stringify({ all: true })
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.message || `HTTP ${resp.status}`);
                }
                const cd = resp.headers.get('Content-Disposition') || '';
                const match = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                const filename = match ? match[1].replace(/['"]/g, '') : 'profiles_export_all.xlsx';
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);
                App.toast(`✅ Exported all profiles → ${filename}`, 'success');
            } catch(e) {
                App.toast('Export All failed: ' + e.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = origHTML || '<i class="fas fa-file-excel" style="color:#22c55e;"></i> Export All'; }
            }
        });

        // Custom in-page worker/stagger picker for "Re-Login All Failed".
        // Electron's BrowserWindow does NOT implement window.prompt() —
        // calling it logs "prompt() is and will not be supported" and
        // returns null immediately, which is what the user saw. Same for
        // any future button that needs interactive input. This builds a
        // minimal modal on demand and resolves to { workers, stagger } or
        // null if the user cancelled.
        function _askReloginAllOptions(failedCount, defWorkers, defStagger) {
            return new Promise(resolve => {
                const overlay = document.createElement('div');
                overlay.style.cssText =
                    'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:99999;' +
                    'display:flex;align-items:center;justify-content:center;';
                overlay.innerHTML =
                    '<div style="background:#0f1629;border:1px solid rgba(255,255,255,0.08);' +
                    'border-radius:8px;padding:18px 20px;min-width:360px;max-width:440px;' +
                    'color:#e2e8f0;font-size:13px;box-shadow:0 8px 32px rgba(0,0,0,0.5);">' +
                    '<div style="font-size:15px;font-weight:700;margin-bottom:6px;color:#fff;">' +
                    '<i class="fas fa-sign-in-alt" style="color:#22c55e;margin-right:6px;"></i>Re-Login All Failed</div>' +
                    '<div style="color:#94a3b8;margin-bottom:14px;line-height:1.5;">' +
                    'Re-login <b style="color:#fbbf24;">' + failedCount + '</b> failed profile(s) across all pages.' +
                    '</div>' +
                    '<div style="display:flex;gap:12px;margin-bottom:14px;">' +
                    '<label style="flex:1;">' +
                    '<div style="color:#94a3b8;font-size:11px;margin-bottom:4px;">Parallel workers (1–10)</div>' +
                    '<input type="number" id="_reloginAllWorkersInp" value="' + defWorkers + '" min="1" max="10" ' +
                    'style="width:100%;background:#1a233a;border:1px solid rgba(255,255,255,0.1);' +
                    'border-radius:4px;padding:6px 8px;color:#fff;font-size:13px;">' +
                    '</label>' +
                    '<label style="flex:1;">' +
                    '<div style="color:#94a3b8;font-size:11px;margin-bottom:4px;">Stagger delay (sec)</div>' +
                    '<input type="number" id="_reloginAllStaggerInp" value="' + defStagger + '" min="0" max="30" ' +
                    'style="width:100%;background:#1a233a;border:1px solid rgba(255,255,255,0.1);' +
                    'border-radius:4px;padding:6px 8px;color:#fff;font-size:13px;">' +
                    '</label>' +
                    '</div>' +
                    '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
                    '<button id="_reloginAllCancel" class="btn btn-sm" ' +
                    'style="background:rgba(255,255,255,0.05);color:#94a3b8;border:1px solid rgba(255,255,255,0.1);">Cancel</button>' +
                    '<button id="_reloginAllStart" class="btn btn-sm" ' +
                    'style="background:rgba(34,197,94,0.18);color:#4ade80;border:1px solid rgba(34,197,94,0.4);">' +
                    '<i class="fas fa-sign-in-alt"></i> Start Re-Login</button>' +
                    '</div>' +
                    '</div>';
                document.body.appendChild(overlay);
                const wInp = overlay.querySelector('#_reloginAllWorkersInp');
                const sInp = overlay.querySelector('#_reloginAllStaggerInp');
                const cleanup = (val) => { overlay.remove(); resolve(val); };
                overlay.querySelector('#_reloginAllCancel').onclick = () => cleanup(null);
                overlay.querySelector('#_reloginAllStart').onclick = () => {
                    let w = parseInt(wInp.value, 10);
                    let s = parseInt(sInp.value, 10);
                    if (!w || w < 1) w = defWorkers;
                    if (!Number.isFinite(s) || s < 0) s = defStagger;
                    w = Math.max(1, Math.min(w, 10));
                    s = Math.max(0, Math.min(s, 30));
                    cleanup({ workers: w, stagger: s });
                };
                overlay.addEventListener('click', e => { if (e.target === overlay) cleanup(null); });
                setTimeout(() => { try { wInp.focus(); wInp.select(); } catch {} }, 30);
            });
        }

        // Re-Login All Failed — toolbar shortcut. Pagination caps the
        // selectable rows at 50/page, so users couldn't bulk-relogin
        // every Failed profile in one shot. This button asks the backend
        // for every profile whose status is `login_failed` (one call, no
        // pagination — backend allows per_page up to 10000) and feeds
        // those IDs into the existing bulk-relogin endpoint.
        _btn('profileReloginAllFailedBtn', async () => {
            const btn = _$('profileReloginAllFailedBtn');
            const origHTML = btn ? btn.innerHTML : '';
            try {
                // 1) Fetch how many failed profiles exist (cheap counts endpoint).
                if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Counting…'; }
                const counts = await _api('/api/profiles/counts');
                const failedCount = (counts && counts.by_filter && counts.by_filter.login_failed) || 0;
                if (!failedCount) {
                    App.toast('No failed profiles to re-login', 'info');
                    return;
                }

                // 2) Ask for workers + stagger via custom modal (Electron
                //    doesn't support window.prompt()).
                const defWorkers = parseInt(_$('pmBulkReloginWorkers') ? _$('pmBulkReloginWorkers').value : '3') || 3;
                const defStagger = parseInt(_$('pmBulkReloginStagger') ? _$('pmBulkReloginStagger').value : '3') || 3;
                if (btn) { btn.disabled = false; btn.innerHTML = origHTML; }
                const opts = await _askReloginAllOptions(failedCount, defWorkers, defStagger);
                if (!opts) return;  // cancelled
                const { workers, stagger } = opts;
                if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading IDs…'; }

                // 3) Fetch ALL failed profile IDs in one shot.
                const list = await _api('/api/profiles?filter=login_failed&page=1&per_page=10000');
                if (!list || !list.success) throw new Error('Failed to load failed-profile list');
                const ids = (list.profiles || []).map(p => p.id).filter(Boolean);
                if (ids.length === 0) {
                    App.toast('No failed profiles found after fetch', 'warn');
                    return;
                }

                // 4) Kick off bulk-relogin with every failed ID.
                if (btn) { btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting…'; }
                const data = await _api('/api/profiles/bulk-relogin', {
                    method: 'POST',
                    body: JSON.stringify({ ids, workers, stagger_delay: stagger })
                });
                if (data && data.success) {
                    App.toast(`Re-login started for ${data.total || ids.length} failed profile(s) — ${workers} workers`, 'success');
                    _startOpProgress('relogin');
                    _startStatusPolling();
                } else {
                    App.toast((data && data.error) || 'Failed to start re-login', 'error');
                }
            } catch (e) {
                App.toast('Re-Login All Failed: ' + e.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = origHTML || '<i class="fas fa-sign-in-alt" style="color:#22c55e;"></i> Re-Login All Failed'; }
            }
        });

        // Bookmark All Profiles — toolbar shortcut. Pagination prevents
        // bulk-select-all (only the current page's rows are selectable),
        // so this button clears the selection and opens the existing
        // bookmark modal in its "apply to ALL profiles" mode (the modal
        // already shows that scope label when _selectedIds is empty, and
        // the backend treats empty `ids` as "all profiles").
        _btn('profileBookmarkAllBtn', () => {
            if (_selectedIds.size > 0) {
                _selectedIds.clear();
                document.querySelectorAll('.pm-row-check').forEach(cb => {
                    cb.checked = false;
                    const row = cb.closest('.pm-row');
                    if (row) row.classList.remove('pm-selected');
                });
                _updateBulkBar();
            }
            _openBookmarkModal();
        });

        // Custom-N select — First / Last N profiles from current filtered+sorted view.
        // Reads the rendered .pm-row-check elements (they appear in the same order
        // as _allProfiles after filter+search+group+sort have been applied) so the
        // user gets exactly what they see. Replaces existing selection.
        function _selectFirstOrLastN(position) {
            const n = parseInt((_$('pmSelectN') || {}).value, 10);
            if (!n || n < 1) { App.toast('Enter a count (N) first', 'warn'); return; }
            const rows = Array.from(document.querySelectorAll('.pm-row-check'));
            if (rows.length === 0) { App.toast('No profiles visible', 'warn'); return; }
            const slice = position === 'first' ? rows.slice(0, n) : rows.slice(-n);
            _selectedIds.clear();
            rows.forEach(cb => {
                cb.checked = false;
                const row = cb.closest('.pm-row');
                if (row) row.classList.remove('pm-selected');
            });
            slice.forEach(cb => {
                cb.checked = true;
                _selectedIds.add(cb.dataset.id);
                const row = cb.closest('.pm-row');
                if (row) row.classList.add('pm-selected');
            });
            _updateBulkBar();
            App.toast(`Selected ${position} ${slice.length} profile${slice.length === 1 ? '' : 's'}`, 'success');
        }
        _btn('pmSelectFirstNBtn', () => _selectFirstOrLastN('first'));
        _btn('pmSelectLastNBtn',  () => _selectFirstOrLastN('last'));

        // Inline delete-group button — visible only when a specific group is picked
        // in pmGroupFilter. Opens the existing Delete Group modal for that group
        // (label-only delete: profiles get reassigned, not deleted).
        _btn('pmDeleteGroupBtn', () => {
            if (!_currentGroup || _currentGroup === 'default') {
                App.toast('Pick a group first (default cannot be deleted)', 'warn');
                return;
            }
            _openDeleteGroup(_currentGroup);
        });

        // Select All checkbox — only selects VISIBLE (filtered) profiles
        const selectAll = _$('pmSelectAll');
        if (selectAll) {
            selectAll.addEventListener('change', () => {
                if (selectAll.checked) {
                    // Add only currently visible rows (respects group/status/search filter)
                    document.querySelectorAll('.pm-row-check').forEach(cb => {
                        cb.checked = true;
                        _selectedIds.add(cb.dataset.id);
                        cb.closest('.pm-row').classList.add('pm-selected');
                    });
                } else {
                    // Clear ALL selections (not just visible)
                    _selectedIds.clear();
                    document.querySelectorAll('.pm-row-check').forEach(cb => {
                        cb.checked = false;
                        cb.closest('.pm-row').classList.remove('pm-selected');
                    });
                }
                _updateBulkBar();
            });
        }

        // Bulk re-login
        _btn('pmBulkReloginBtn', async () => {
            if (!_selectedIds.size) { App.toast('Select profiles first', 'warn'); return; }
            const workers = parseInt(_$('pmBulkReloginWorkers') ? _$('pmBulkReloginWorkers').value : '2') || 2;
            const staggerDelay = parseInt(_$('pmBulkReloginStagger') ? _$('pmBulkReloginStagger').value : '3') || 3;
            try {
                const data = await _api('/api/profiles/bulk-relogin', {
                    method: 'POST',
                    body: JSON.stringify({ ids: [..._selectedIds], workers, stagger_delay: staggerDelay })
                });
                if (data.success) {
                    App.toast(`Re-login started for ${data.total} profiles (${workers} workers)`, 'success');
                    _startOpProgress('relogin');
                    _startStatusPolling();
                } else App.toast(data.error || 'Failed to start re-login', 'error');
            } catch(e) { App.toast('Re-login error: ' + e.message, 'error'); }
        });

        // Export selected profiles to Excel
        _btn('pmBulkExportBtn', async () => {
            if (!_selectedIds.size) { App.toast('Select profiles first', 'warn'); return; }
            const btn = _$('pmBulkExportBtn');
            if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting…'; }
            try {
                const resp = await App.apiFetch('/api/profiles/export-excel', {
                    method: 'POST',
                    body: JSON.stringify({ ids: [..._selectedIds] })
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.message || `HTTP ${resp.status}`);
                }
                // Extract filename from Content-Disposition header
                const cd = resp.headers.get('Content-Disposition') || '';
                const match = cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                const filename = match ? match[1].replace(/['"]/g, '') : 'profiles_export.xlsx';

                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);

                App.toast(`✅ Exported ${_selectedIds.size} profiles → ${filename}`, 'success');
            } catch(e) {
                App.toast('Export failed: ' + e.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-file-excel"></i> Export'; }
            }
        });

        // Add Bookmarks button
        _btn('pmBulkBookmarkBtn', _openBookmarkModal);

        // Fast Mode (bulk perf settings)
        _btn('pmBulkFastModeBtn', _openBulkFastModeModal);
        _btn('bulkFastModeClose', _closeBulkFastModeModal);
        _btn('bulkFastModeCancel', _closeBulkFastModeModal);
        _btn('bulkFastModeApply', _applyBulkFastMode);
        document.querySelectorAll('.bfm-scope-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.bfm-scope-btn').forEach(b => {
                    b.classList.remove('active');
                    b.style.background = 'transparent';
                    b.style.color = '#94a3b8';
                });
                btn.classList.add('active');
                btn.style.background = 'rgba(99,102,241,0.20)';
                btn.style.color = '#a5b4fc';
                const isGroup = btn.dataset.scope === 'group';
                const groupRow = _$('bfmGroupRow');
                if (groupRow) groupRow.style.display = isGroup ? 'block' : 'none';
            });
        });

        // Performance tab — preset buttons (in edit modal)
        _btn('pmPerfPresetMax', () => {
            document.querySelectorAll('.pm-perf-toggle').forEach(cb => { cb.checked = true; });
        });
        _btn('pmPerfPresetNormal', () => {
            document.querySelectorAll('.pm-perf-toggle').forEach(cb => {
                cb.checked = (cb.dataset.perfKey === 'block_popups');  // popups blocked by default
            });
        });

        // Bulk bar buttons
        _btn('pmBulkAddBtn', _bulkAddToGroup);
        _btn('pmBulkMoveBtn', _bulkMoveToGroup);
        _btn('pmBulkRemoveBtn', _bulkRemoveFromGroup);
        _btn('pmBulkDeleteBtn', deleteSelectedProfiles);
        _btn('pmBulkSaveNoteBtn', _bulkSaveNoteOnly);
        _btn('pmBulkUpdateProxyBtn', _bulkUpdateProxy);
        _btn('pmBulkClearBtn', () => {
            _selectedIds.clear();
            document.querySelectorAll('.pm-row-check').forEach(cb => {
                cb.checked = false;
                if (cb.closest('.pm-row')) cb.closest('.pm-row').classList.remove('pm-selected');
            });
            const sa = _$('pmSelectAll'); if (sa) sa.checked = false;
            _updateBulkBar();
        });

        // Bookmark modal buttons
        _btn('bookmarkCancelBtn', _closeBookmarkModal);
        _btn('bookmarkApplyBtn', _applyBookmarks);

        // Extension manager
        _btn('pmExtensionsBtn', _openExtModal);
        _btn('extModalCloseBtn', _closeExtModal);
        _btn('extInstallUrlBtn', _extInstallUrl);
        _btn('extZipBtn', () => _$('extZipInput') && _$('extZipInput').click());
        const _extZipInput = _$('extZipInput');
        if (_extZipInput) {
            _extZipInput.addEventListener('change', async () => {
                const file = _extZipInput.files[0];
                if (!file) return;
                const span = _$('extZipName');
                if (span) span.textContent = file.name;
                const fd = new FormData();
                fd.append('file', file);
                fd.append('name', file.name.replace(/\.(zip|crx)$/i, ''));
                const btn = _$('extZipBtn');
                if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing…'; }
                try {
                    const res = await fetch('/api/extensions/install-zip', {
                        method: 'POST',
                        body: fd,
                        headers: App.state.apiToken ? { 'X-Api-Token': App.state.apiToken } : {}
                    });
                    const data = await res.json();
                    if (data.success) { App.toast(`Extension installed: ${data.name}`, 'success'); _extZipInput.value = ''; if (span) span.textContent = ''; _loadExtList(); }
                    else App.toast(data.message || 'Install failed', 'error');
                } catch(e) { App.toast('Install error: ' + e.message, 'error'); }
                finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-upload"></i> Upload ZIP / CRX'; } }
            });
        }
        const _extOverlay = _$('extModalOverlay');
        if (_extOverlay) _extOverlay.addEventListener('click', (e) => { if (e.target === _extOverlay) _closeExtModal(); });

        // Group manager
        _btn('manageGroupsBtn', _openGroupManager);
        _btn('groupManagerCloseBtn', _closeGroupManager);
        _btn('groupManagerDoneBtn', _closeGroupManager);
        _btn('createGroupBtn', _createGroup);
        _btn('renameGroupCloseBtn', _closeRenameGroup);
        _btn('renameGroupCancelBtn', _closeRenameGroup);
        _btn('renameGroupConfirmBtn', _confirmRenameGroup);
        _btn('deleteGroupCloseBtn', _closeDeleteGroup);
        _btn('deleteGroupCancelBtn', _closeDeleteGroup);
        _btn('deleteGroupConfirmBtn', _confirmDeleteGroup);

        // Create dropdown
        _btn('profileCreateBtn', (e) => {
            e.stopPropagation();
            _$('profileCreateMenu').classList.toggle('show');
        });
        _btn('pmCreateSingle', (e) => { e.preventDefault(); _$('profileCreateMenu').classList.remove('show'); openCreateModal(); });
        _btn('pmBatchCreate', (e) => { e.preventDefault(); _$('profileCreateMenu').classList.remove('show'); App.toast('Batch create coming soon', 'info'); });
        _btn('pmBatchImport', (e) => { e.preventDefault(); _$('profileCreateMenu').classList.remove('show'); App.toast('Batch import coming soon', 'info'); });

        // Close dropdown on outside click
        document.addEventListener('click', () => {
            const menu = _$('profileCreateMenu');
            if (menu) menu.classList.remove('show');
            _hideContextMenu();
        });

        // Action buttons
        _btn('profileCloseAllBtn', closeAllProfiles);
        _btn('profileCleanupBtn', cleanupOrphans);
        _btn('profileBulkProxyBtn', _openBulkProxyModal);
        _btn('bulkProxyCloseBtn', _closeBulkProxyModal);
        _btn('profileRestoreNstBtn', restoreFromNst);
        _btn('profileExtensionsBtn', _openExtModal);
        _btn('profileDuplicateCheckBtn', _openDuplicateCheckModal);
        _btn('duplicateCheckModalClose', _closeDuplicateCheckModal);
        _btn('duplicateCheckCancelBtn', _closeDuplicateCheckModal);
        _btn('duplicateCheckDeleteBtn', _dupDeleteSelected);
        _btn('dupSelectAllBtn', () => {
            _$('duplicateCheckList').querySelectorAll('.dup-row-cb').forEach(cb => { cb.checked = true; _dupSelectedIds.add(cb.dataset.profileId); });
            _dupUpdateCount();
        });
        _btn('dupDeselectAllBtn', () => {
            _$('duplicateCheckList').querySelectorAll('.dup-row-cb').forEach(cb => { cb.checked = false; });
            _dupSelectedIds = new Set();
            _dupUpdateCount();
        });
        _btn('profileSwitchLocalBtn', async () => {
            if (!(await App.confirm('Switch ALL NST profiles to local (nexus) engine?\n\nExisting profile data (cookies, sessions, bookmarks) will be preserved.\nAfter this, profiles will launch using the local nstchrome binary.', 'Switch to Local', 'btn-primary', 'fa-laptop'))) return;
            try {
                const data = await _api('/api/profiles/switch-to-local', { method: 'POST', body: JSON.stringify({}) });
                if (data.success) {
                    App.toast(`Switched ${data.switched} profile(s) to local engine`, 'success');
                    // Reset filter to 'all' so switched (now nexus) profiles are visible
                    _currentFilter = 'all';
                    document.querySelectorAll('.pm-filter-btn').forEach(b => b.classList.remove('active'));
                    const allBtn = document.querySelector('.pm-filter-btn[data-filter="all"]');
                    if (allBtn) allBtn.classList.add('active');
                    await loadProfiles();
                } else App.toast(data.error || 'Switch failed', 'error');
            } catch(e) { App.toast('Error: ' + e.message, 'error'); }
        });
        _btn('profileDriveBackupBtn', openDriveBackupModal);
        setupDriveBackupModal();
        _btn('profileBatchLoginBtn', openBatchLoginModal);
        _btn('profileRunOpsBtn', openRunOpsModal);
        _setupRunOpsModal();
        _btn('profileDoAllAppealBtn', openAppealModal);
        _btn('appealModalClose', closeAppealModal);
        _btn('appealModalCancelBtn', closeAppealModal);
        _btn('appealModalStartBtn', startDoAllAppeal);
        _btn('appealSelectAll', () => {
            // Only select profiles visible in current filter (group + search)
            _filteredAppeal().forEach(p => _appealChecked.add(p.id));
            _renderAppealList();
            _updateAppealCount();
        });
        _btn('appealDeselectAll', () => {
            // Clear ALL selections (clean slate), not just filtered
            _appealChecked.clear();
            _renderAppealList();
            _updateAppealCount();
        });
        const appealSearchEl = document.getElementById('appealSearchInput');
        if (appealSearchEl) {
            appealSearchEl.addEventListener('input', () => {
                _appealSearch = appealSearchEl.value;
                _appealPage = 1;
                _renderAppealList();
            });
        }
        const appealGroupEl = document.getElementById('appealGroupFilter');
        if (appealGroupEl) {
            appealGroupEl.addEventListener('change', () => {
                _appealGroupFilter = appealGroupEl.value;
                _appealPage = 1;
                // Clear old selections when group changes to avoid cross-group accumulation
                _appealChecked.clear();
                _renderAppealList();
                _updateAppealCount();
            });
        }
        // Appeal mode toggle (Select vs Excel)
        _btn('appealModeSelectBtn', () => _setAppealMode('select'));
        _btn('appealModeExcelBtn', () => _setAppealMode('excel'));
        _btn('appealModeSheetBtn', () => _setAppealMode('sheet'));
        _btn('appealSheetAuthBtn', _doAppealSheetAuthorize);
        _btn('appealSheetRefreshBtn', _loadAppealSheetList);
        const apSearch = document.getElementById('appealSheetSearch');
        if (apSearch) apSearch.addEventListener('input', () => {
            if (_appealSheetSearchTimer) clearTimeout(_appealSheetSearchTimer);
            _appealSheetSearchTimer = setTimeout(_loadAppealSheetList, 350);
        });
        // Appeal tab All/None/Reconnect buttons
        _btn('appealTabAllBtn', () => _appealToggleAllTabs(true));
        _btn('appealTabNoneBtn', () => _appealToggleAllTabs(false));
        _btn('appealSheetReconnectBtn', async () => {
            App.toast('Browser will open — log in and grant access', 'info');
            try {
                await App.apiFetch('/api/sheets/reauthorize', { method: 'POST' });
                App.toast('Google Sheets reconnected', 'success');
                _refreshAppealSheetAuth();
            } catch (e) { App.toast('Reconnect failed: ' + e.message, 'error'); }
        });
        _btn('appealExcelBrowseBtn', _appealBrowseExcel);

        document.getElementById('appealModal')?.addEventListener('click', e => {
            if (e.target === document.getElementById('appealModal')) closeAppealModal();
        });
        _btn('profileHealthBtn', openHealthModal);
        _btn('profileWriteReviewBtn', openWriteReviewModal);
        _btn('writeReviewCloseBtn', closeWriteReviewModal);
        _btn('writeReviewCancelBtn', closeWriteReviewModal);
        _btn('writeReviewStartBtn', startWriteReview);
        // Sheet mode controls
        _btn('wrSrcExcel', () => _switchWRSource('excel'));
        _btn('wrSrcSheet', () => _switchWRSource('sheet'));
        _btn('wrSheetAuthBtn', _wrAuthorize);
        _btn('wrSheetRefreshBtn', _wrLoadSheetList);
        const wrss = _$('wrSheetSearch');
        if (wrss) wrss.addEventListener('input', () => {
            if (_wrSearchTimer) clearTimeout(_wrSearchTimer);
            _wrSearchTimer = setTimeout(_wrLoadSheetList, 350);
        });
        _btn('wrSelectAllTabsBtn', () => {
            document.querySelectorAll('#wrTabList .wr-tab-cb').forEach(cb => {
                if (cb.parentElement && cb.parentElement.style.display === 'none') return;
                if (!cb.checked) { cb.checked = true; _wrToggleTab(cb); }
            });
        });
        _btn('wrSelectNoneTabsBtn', () => {
            document.querySelectorAll('#wrTabList .wr-tab-cb').forEach(cb => {
                if (cb.parentElement && cb.parentElement.style.display === 'none') return;
                if (cb.checked) { cb.checked = false; _wrToggleTab(cb); }
            });
        });
        const wrts = _$('wrTabSearch');
        if (wrts) wrts.addEventListener('input', _wrFilterTabs);
        const wrPS = _$('wrProfileSearch');
        if (wrPS) wrPS.addEventListener('input', _wrRenderProfileList);
        const wrGF = _$('wrGroupFilter');
        if (wrGF) wrGF.addEventListener('change', _wrRenderProfileList);
        _btn('wrApplyGroupBtn', () => {
            const n = parseInt((_$('wrSelectN') || {}).value, 10);
            if (!n || n < 1) { App.toast('Enter a count first', 'warn'); return; }
            const filtered = _wrGetFilteredProfiles();
            const pick = filtered.slice(0, n);
            _wrSelectedProfiles.clear();
            pick.forEach(p => _wrSelectedProfiles.add(p.id));
            _wrRenderProfileList();
            _wrUpdateProfileCount();
            App.toast(`${pick.length} profile${pick.length === 1 ? '' : 's'} selected`, 'success');
        });
        _btn('wrImportXlBtn', async () => {
            const filePath = await window.electronAPI.selectFile();
            if (!filePath) return;
            const ext = filePath.split('.').pop().toLowerCase();
            if (ext !== 'xlsx' && ext !== 'xls') {
                App.toast('Select an .xlsx or .xls file', 'warn'); return;
            }
            try {
                const r = await App.apiFetch('/api/profiles/write-review/import-emails', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: filePath }),
                });
                const d = await r.json();
                if (!d.success) { App.toast(d.message || 'Import failed', 'error'); return; }
                d.matched_ids.forEach(id => _wrSelectedProfiles.add(id));
                _wrRenderProfileList();
                _wrUpdateProfileCount();
                const suffix = d.not_found.length ? ` · ${d.not_found.length} not found` : '';
                App.toast(`${d.matched_count} profile${d.matched_count === 1 ? '' : 's'} selected${suffix}`, 'success');
            } catch (e) { App.toast('Import error: ' + e.message, 'error'); }
        });
        _btn('wrSelectAllProfilesBtn', () => {
            // Drive selection from the filtered ARRAY, not DOM checkboxes —
            // if rendering ever becomes virtualised (or the list element is
            // scrolled / hidden), querySelectorAll would only see a partial
            // slice. The array is authoritative.
            const filtered = _wrGetFilteredProfiles();
            filtered.forEach(p => _wrSelectedProfiles.add(p.id));
            _wrRenderProfileList();
            _wrUpdateProfileCount();
            App.toast && App.toast(`${filtered.length} profile${filtered.length === 1 ? '' : 's'} selected`, 'success');
        });
        _btn('wrSelectNoProfilesBtn', () => {
            _wrSelectedProfiles.clear();
            _wrRenderProfileList();
            _wrUpdateProfileCount();
        });
        _btn('writeReviewBrowseBtn', async () => { await browseFile('writeReviewFilePath'); _previewWRFile(); });

        // GMB → Review URL
        _btn('profileGmbToReviewBtn', openGmbToReviewModal);
        _btn('gmbToReviewCloseBtn', closeGmbToReviewModal);
        _btn('gmbToReviewCancelBtn', closeGmbToReviewModal);
        _btn('gmbToReviewStartBtn', startGmbToReview);
        _btn('gmbToReviewBrowseBtn', async () => { await browseFile('gmbToReviewFilePath'); _previewGmbFile(); });
        const gmbFileInp = _$('gmbToReviewFilePath');
        if (gmbFileInp) gmbFileInp.addEventListener('input', _previewGmbFile);

        // Export template
        _btn('writeReviewTemplateBtn', async () => {
            const btn = _$('writeReviewTemplateBtn');
            if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading…'; }
            try {
                const resp = await App.apiFetch('/api/profiles/write-review-template', { method: 'GET' });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'WriteReview_Template.xlsx';
                document.body.appendChild(a);
                a.click();
                setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);
                App.toast('✅ Template downloaded — open it to see instructions + examples', 'success');
            } catch(e) {
                App.toast('Template download failed: ' + e.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-file-download"></i> Export Template'; }
            }
        });
        const wrFileInp = _$('writeReviewFilePath');
        if (wrFileInp) wrFileInp.addEventListener('input', _previewWRFile);
        _btn('healthModalClose', closeHealthModal);
        _btn('healthModalCancelBtn', closeHealthModal);
        _btn('healthModalStartBtn', startHealth);

        // Smart vs Manual mode toggle
        document.querySelectorAll('.health-mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.health-mode-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const mode = btn.dataset.mode;
                const smartPanel = document.getElementById('healthSmartPanel');
                const manualPanel = document.getElementById('healthManualPanel');
                if (smartPanel) smartPanel.style.display = mode === 'smart' ? 'block' : 'none';
                if (manualPanel) manualPanel.style.display = mode === 'manual' ? 'block' : 'none';
                // When switching to smart, auto-set recommended duration
                if (mode === 'smart') {
                    const goal = document.querySelector('input[name="healthSmartGoal"]:checked')?.value || 'gmail_trust';
                    const preset = _SMART_PRESETS[goal];
                    if (preset) {
                        const durEl = document.getElementById('healthDuration');
                        const rndEl = document.getElementById('healthRounds');
                        if (durEl && !parseInt(durEl.value)) durEl.value = preset.duration;
                        if (rndEl) rndEl.value = preset.rounds;
                    }
                }
            });
        });
        // Smart goal change → update recommended duration
        document.querySelectorAll('input[name="healthSmartGoal"]').forEach(radio => {
            radio.addEventListener('change', () => {
                const preset = _SMART_PRESETS[radio.value];
                if (preset) {
                    const durEl = document.getElementById('healthDuration');
                    const rndEl = document.getElementById('healthRounds');
                    if (durEl) durEl.value = preset.duration;
                    if (rndEl) rndEl.value = preset.rounds;
                }
            });
        });
        _btn('healthSelectAll', () => {
            document.querySelectorAll('#healthModal .health-act-item input[type="checkbox"]').forEach(cb => cb.checked = true);
            _updateHealthCount();
        });
        _btn('healthDeselectAll', () => {
            document.querySelectorAll('#healthModal .health-act-item input[type="checkbox"]').forEach(cb => cb.checked = false);
            _updateHealthCount();
        });
        _btn('healthRandomPick', () => {
            const countInput = document.getElementById('healthRandomCount');
            const n = Math.max(1, parseInt(countInput ? countInput.value : '5') || 5);
            const allCbs = Array.from(document.querySelectorAll('#healthModal .health-act-item input[type="checkbox"]'));
            // Uncheck all first
            allCbs.forEach(cb => cb.checked = false);
            // Shuffle and pick N
            const shuffled = allCbs.sort(() => Math.random() - 0.5);
            const pick = Math.min(n, shuffled.length);
            for (let i = 0; i < pick; i++) shuffled[i].checked = true;
            _updateHealthCount();
            App.toast(`Randomly picked ${pick} activities`, 'info');
        });
        _btn('healthProfileSelectAll', () => {
            // Only select profiles visible in current filter (group + search)
            _filteredHealth().forEach(p => _healthChecked.add(p.id));
            _renderHealthProfileList();
            _updateHealthCount();
        });
        _btn('healthProfileDeselectAll', () => {
            // Clear ALL selections (clean slate)
            _healthChecked.clear();
            _renderHealthProfileList();
            _updateHealthCount();
        });
        const healthSearchEl = document.getElementById('healthProfileSearchInput');
        if (healthSearchEl) {
            healthSearchEl.addEventListener('input', () => {
                _healthProfileSearch = healthSearchEl.value;
                _healthProfilePage = 1;
                _renderHealthProfileList();
            });
        }
        const healthGroupEl = document.getElementById('healthGroupFilter');
        if (healthGroupEl) {
            healthGroupEl.addEventListener('change', () => {
                _healthGroupFilter = healthGroupEl.value;
                _healthProfilePage = 1;
                // Clear old selections when group changes to avoid cross-group accumulation
                _healthChecked.clear();
                _renderHealthProfileList();
                _updateHealthCount();
            });
        }
        document.querySelectorAll('#healthModal .health-act-item input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', _updateHealthCount);
        });
        const healthModal = document.getElementById('healthModal');
        if (healthModal) {
            healthModal.addEventListener('click', (e) => {
                if (e.target === healthModal) closeHealthModal();
            });
        }
        // Per-card stop buttons are wired inside _startOpProgress (one handler
        // per card). The legacy singleton #opStopBtn no longer exists — the
        // template only renders [data-role="stopBtn"] elements per-card.
        _btn('reviewReportDismissBtn', () => {
            const bar = document.getElementById('reviewReportBar');
            if (bar) bar.style.display = 'none';
        });
        _btn('reviewReportOpenBtn', async () => {
            const pathEl = document.getElementById('reviewReportPath');
            if (!pathEl) return;
            const reportPath = pathEl.dataset.path || '';
            if (!reportPath) return;
            try {
                if (window.electronAPI && window.electronAPI.openPath) {
                    window.electronAPI.openPath(reportPath);
                }
            } catch(e) { App.toast('Could not open report', 'error'); }
        });

        // Save & Continue shortcut inside Profile Modal
        document.addEventListener('keydown', (e) => {
            const modal = document.getElementById('profileModalOverlay');
            if (modal && modal.classList.contains('active')) {
                if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'Enter')) {
                    e.preventDefault();
                    saveProfile();
                }
            }
        });

        // Modal buttons
        _btn('profileModalSaveBtn', saveProfile);
        _btn('profileModalCloseBtn', closeModal);
        _btn('profileModalCancelBtn', closeModal);
        // Multi-group input in profile modal
        _btn('pmGroupAddBtn', () => {
            const inp = _$('pmGroup');
            const g = (inp ? inp.value : '').trim();
            if (!g) return;
            if (!_pmGroupsState.includes(g)) { _pmGroupsState.push(g); _renderPmGroupTags(); }
            if (inp) inp.value = '';
        });
        const pmGroupInp = _$('pmGroup');
        if (pmGroupInp) pmGroupInp.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); document.getElementById('pmGroupAddBtn').click(); }
        });

        _btn('pmCheckProxy', checkProxy);
        _btn('pmParseProxy', parseProxyString);
        
        _btn('pmTogglePasswordBtn', () => {
            const pwd = _$('pmPassword');
            const btn = _$('pmTogglePasswordBtn');
            if (pwd && btn) {
                if (pwd.type === 'password') {
                    pwd.type = 'text';
                    btn.innerHTML = '<i class="fas fa-eye-slash"></i>';
                } else {
                    pwd.type = 'password';
                    btn.innerHTML = '<i class="fas fa-eye"></i>';
                }
            }
        });

        // TOTP widget: live update on secret change + copy btn
        const pmTotpInp = _$('pmTotp');
        if (pmTotpInp) {
            pmTotpInp.addEventListener('input', () => _startPmTotp());
            pmTotpInp.addEventListener('paste', () => setTimeout(_startPmTotp, 50));
        }
        _btn('pmTotpCopyBtn', () => {
            const code = (_$('pmTotpCode') || {}).innerText;
            if (code && code !== '------') {
                navigator.clipboard.writeText(code);
                const btn = _$('pmTotpCopyBtn');
                if (btn) { btn.innerHTML = '<i class="fas fa-check"></i>'; setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i>'; }, 1500); }
            }
        });

        // Tab switching
        document.querySelectorAll('.pm-tab').forEach(tab => {
            tab.addEventListener('click', () => _switchTab(tab.dataset.tab));
        });

        // Show mobile OS (Android/iOS supported via fingerprint emulation)
        function _toggleMobileOS() {
            const hideM = false;
            document.querySelectorAll('.pm-os-pills input[name="pmOS"]').forEach(r => {
                const pill = r.closest('.pm-os-pill');
                if (!pill) return;
                if (r.value === 'android' || r.value === 'ios') {
                    pill.style.display = hideM ? 'none' : '';
                    if (hideM && r.checked) {
                        const rand = document.querySelector('input[name="pmOS"][value="random"]');
                        if (rand) { rand.checked = true; rand.closest('.pm-os-pill').classList.add('active'); pill.classList.remove('active'); }
                    }
                }
            });
        }
        // Engine tabs
        document.querySelectorAll('.pm-engine-nav .pm-engine-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const nav = tab.closest('.pm-engine-nav');
                nav.querySelectorAll('.pm-engine-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const radio = tab.querySelector('input[type="radio"]');
                if (radio) radio.checked = true;
                _toggleMobileOS();
                _updateSummary();
            });
        });
        // OS pills
        document.querySelectorAll('.pm-os-pills .pm-os-pill').forEach(pill => {
            pill.addEventListener('click', () => {
                const pills = pill.closest('.pm-os-pills');
                pills.querySelectorAll('.pm-os-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                const radio = pill.querySelector('input[type="radio"]');
                if (radio) radio.checked = true;
                _updateSummary();
            });
        });
        _toggleMobileOS(); // initial state

        // OS radio change -> update summary
        document.querySelectorAll('input[name="pmOS"]').forEach(radio => {
            radio.addEventListener('change', _updateSummary);
        });

        // Proxy type change
        const proxyTypeSel = _$('pmProxyType');
        if (proxyTypeSel) proxyTypeSel.addEventListener('change', () => {
            _toggleProxyFields();
            _updateSummary();
        });

        // Show/hide WebGL vendor+renderer fields based on WebGL Meta Mode selection
        document.querySelectorAll('input[name="fpWebGLMeta"]').forEach(r => {
            r.addEventListener('change', () => {
                const show = document.querySelector('input[name="fpWebGLMeta"]:checked')?.value === 'custom';
                document.querySelectorAll('.pm-webgl-meta-fields').forEach(el => {
                    el.style.display = show ? '' : 'none';
                });
            });
        });

        // Show/hide lat/lng fields based on geolocation permission
        document.querySelectorAll('input[name="fpGeoPermission"]').forEach(r => {
            r.addEventListener('change', () => {
                const showGeo = document.querySelector('input[name="fpGeoPermission"]:checked')?.value === 'allow';
                document.querySelectorAll('.pm-geo-coords').forEach(el => {
                    el.style.display = showGeo ? '' : 'none';
                });
            });
        });

        // Auto-fill Hardware tab when OS changes to mobile/desktop
        const MOBILE_DEFAULTS = {
            android: { resolution: '412x915', cpu: '8', ram: '8', vendor: 'Qualcomm', renderer: 'Adreno (TM) 740' },
            ios:     { resolution: '390x844', cpu: '6', ram: '4', vendor: 'Apple',    renderer: 'Apple GPU' },
        };
        const DESKTOP_DEFAULTS = { resolution: '1366x768', cpu: '4', ram: '4', vendor: 'Intel Inc.', renderer: 'Intel(R) Iris(R) Xe Graphics' };
        document.querySelectorAll('input[name="pmOS"]').forEach(r => {
            r.addEventListener('change', () => {
                const os = document.querySelector('input[name="pmOS"]:checked')?.value;
                const d = MOBILE_DEFAULTS[os] || DESKTOP_DEFAULTS;
                const _sv2 = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
                _sv2('pmScreenResolution', d.resolution);
                _sv2('pmCpuThreads',       d.cpu);
                _sv2('pmRamGb',            d.ram);
                _sv2('pmWebGLVendor',      d.vendor);
                _sv2('pmWebGLRenderer',    d.renderer);
            });
        });

        // Update summary on proxy host change
        ['pmProxyHost', 'pmName', 'pmEmail'].forEach(id => {
            const el = _$(id);
            if (el) el.addEventListener('input', _updateSummary);
        });

        // Batch login modal
        _btn('batchLoginStartBtn', startBatchLogin);
        // Fast Mode presets inside Batch Login modal
        _btn('batchLoginPerfMax', () => {
            document.querySelectorAll('.bl-perf-toggle').forEach(cb => { cb.checked = true; });
        });
        _btn('batchLoginPerfReset', () => {
            document.querySelectorAll('.bl-perf-toggle').forEach(cb => { cb.checked = false; });
        });
        _btn('batchLoginCloseBtn', closeBatchLoginModal);
        _btn('batchLoginBrowseBtn', async () => {
            await browseFile('batchLoginFilePath');
            _previewBatchFile();
        });

        // Live Status Check modal
        _btn('profileLiveCheckBtn', openLiveCheckModal);
        _btn('liveCheckStartBtn', startLiveCheck);
        _btn('liveCheckCloseBtn', closeLiveCheckModal);
        _btn('liveCheckBrowseBtn', async () => {
            await browseFile('liveCheckFilePath');
            _previewLiveCheckFile();
        });

        // Status filter chips — multi-select, "All" is mutually exclusive
        // with the specific-status chips. Clicking "All" clears the others;
        // clicking any specific chip turns "All" off so the run is limited.
        const lcChipBox = _$('liveCheckStatusChips');
        if (lcChipBox) {
            const ACTIVE_BG = 'rgba(99,102,241,0.22)';
            const ACTIVE_FG = '#a5b4fc';
            const ACTIVE_BD = 'rgba(99,102,241,0.5)';
            const IDLE_BG   = '#1a233a';
            const IDLE_FG   = '#94a3b8';
            const IDLE_BD   = 'rgba(255,255,255,0.1)';
            const _paintChip = (chip) => {
                const on = chip.classList.contains('active');
                chip.style.background = on ? ACTIVE_BG : IDLE_BG;
                chip.style.color      = on ? ACTIVE_FG : IDLE_FG;
                chip.style.borderColor = on ? ACTIVE_BD : IDLE_BD;
            };
            lcChipBox.querySelectorAll('.lc-status-chip').forEach(chip => {
                chip.addEventListener('click', () => {
                    const isAll = chip.dataset.status === 'all';
                    const chips = lcChipBox.querySelectorAll('.lc-status-chip');
                    if (isAll) {
                        chips.forEach(c => c.classList.remove('active'));
                        chip.classList.add('active');
                    } else {
                        const allChip = lcChipBox.querySelector('.lc-status-chip[data-status="all"]');
                        if (allChip) allChip.classList.remove('active');
                        chip.classList.toggle('active');
                        const anySpecific = Array.from(chips).some(c =>
                            c.dataset.status !== 'all' && c.classList.contains('active'));
                        if (!anySpecific && allChip) allChip.classList.add('active');
                    }
                    chips.forEach(_paintChip);
                    // Recompute the preview text using the cached per-tab
                    // status_counts — no extra Sheets API hit.
                    if (typeof _renderLiveCheckPreviewText === 'function') {
                        _renderLiveCheckPreviewText();
                    }
                });
            });
        }
        const lcFileInp = _$('liveCheckFilePath');
        if (lcFileInp) lcFileInp.addEventListener('input', _previewLiveCheckFile);

        // Source switcher tabs
        _btn('liveCheckSrcExcel', () => _switchLiveCheckSource('excel'));
        _btn('liveCheckSrcSheet', () => _switchLiveCheckSource('sheet'));
        // Sheet picker controls
        _btn('liveCheckSheetAuthBtn', _doSheetAuthorize);
        _btn('liveCheckSheetRefreshBtn', _loadSheetList);
        const sSearch = _$('liveCheckSheetSearch');
        if (sSearch) sSearch.addEventListener('input', () => {
            if (_sheetSearchTimer) clearTimeout(_sheetSearchTimer);
            _sheetSearchTimer = setTimeout(_loadSheetList, 350);
        });
        // Tab All/None buttons for live check
        _btn('liveCheckTabAllBtn', () => _liveCheckToggleAllTabs(true));
        _btn('liveCheckTabNoneBtn', () => _liveCheckToggleAllTabs(false));
        // Reconnect button
        _btn('liveCheckSheetReconnectBtn', async () => {
            const btn = _$('liveCheckSheetReconnectBtn');
            if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin" style="font-size:10px;"></i> Re-authorizing…'; }
            try {
                const r = await App.apiFetch('/api/sheets/authorize', { method: 'POST' });
                const d = await r.json();
                if (d.success) {
                    App.toast('Google Sheets re-connected ✓', 'success');
                    await _refreshSheetAuth();
                } else {
                    App.toast(d.message || 'Re-authorization failed', 'error');
                }
            } catch (e) {
                App.toast('Auth error: ' + e.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-redo-alt" style="font-size:10px;"></i> Reconnect'; }
            }
        });
        const blFileInp = _$('batchLoginFilePath');
        if (blFileInp) blFileInp.addEventListener('input', _previewBatchFile);

        // Batch engine tabs + OS pills
        function _toggleBatchMobileOS() {
            const hideM = false;
            document.querySelectorAll('#batchLoginModal .pm-os-pills input[name="batchOs"]').forEach(r => {
                const pill = r.closest('.pm-os-pill');
                if (!pill) return;
                if (r.value === 'android' || r.value === 'ios') {
                    pill.style.display = hideM ? 'none' : '';
                    if (hideM && r.checked) {
                        const rand = document.querySelector('input[name="batchOs"][value="random"]');
                        if (rand) { rand.checked = true; rand.closest('.pm-os-pill').classList.add('active'); pill.classList.remove('active'); }
                    }
                }
            });
        }
        document.querySelectorAll('#batchLoginModal .pm-engine-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const nav = tab.closest('.pm-engine-nav');
                nav.querySelectorAll('.pm-engine-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const radio = tab.querySelector('input[type="radio"]');
                if (radio) radio.checked = true;
                _toggleBatchMobileOS();
            });
        });
        document.querySelectorAll('#batchLoginModal .pm-os-pill').forEach(pill => {
            pill.addEventListener('click', () => {
                const pills = pill.closest('.pm-os-pills');
                pills.querySelectorAll('.pm-os-pill').forEach(p => p.classList.remove('active'));
                pill.classList.add('active');
                const radio = pill.querySelector('input[type="radio"]');
                if (radio) radio.checked = true;
            });
        });
        _toggleBatchMobileOS();

        // Storage
        _btn('profileSaveStorageBtn', async () => {
            const path = _val('profileStoragePath').trim();
            if (!path) return;
            try {
                const data = await _api('/api/profiles/config', { method: 'POST', body: JSON.stringify({ storage_path: path }) });
                if (data.success) App.toast('Storage path saved', 'success');
            } catch (e) { App.toast('Error', 'error'); }
        });
        _btn('profileSelectStorageBtn', async () => {
            try {
                if (window.electronAPI && window.electronAPI.selectFolder) {
                    const folderPath = await window.electronAPI.selectFolder();
                    if (folderPath) _setVal('profileStoragePath', folderPath);
                }
            } catch (e) { App.toast('Folder picker error', 'error'); }
        });

        // Backup Codes parser — paste all codes at once, auto-fill 10 fields
        const _bcParseBtn = _$('pmBCParseBtn');
        if (_bcParseBtn) {
            _bcParseBtn.addEventListener('click', () => {
                const raw = (_val('pmBCParser') || '').trim();
                if (!raw) return App.toast('Paste your backup codes first', 'warning');
                // Split by newline, comma, tab, or 2+ spaces — then clean each token
                const tokens = raw.split(/[\n\r,\t]+|[ ]{2,}/)
                    .map(t => t.trim().replace(/\s+/g, ' '))
                    .filter(t => t.length > 0);
                // Each code is 8 digits, possibly formatted as "XXXX XXXX"
                // If we got fewer than 10, try splitting further by single space
                let codes = tokens;
                if (codes.length < 10) {
                    // Try pairing consecutive 4-digit groups
                    const allParts = raw.replace(/[,\t\n\r]+/g, ' ').trim().split(/\s+/);
                    if (allParts.length >= 20 && allParts.every(p => /^\d{4}$/.test(p))) {
                        codes = [];
                        for (let i = 0; i < allParts.length - 1; i += 2) {
                            codes.push(allParts[i] + ' ' + allParts[i + 1]);
                        }
                    }
                }
                if (codes.length < 1) return App.toast('Could not parse any codes', 'error');
                const filled = Math.min(codes.length, 10);
                for (let i = 1; i <= 10; i++) {
                    _setVal('pmBC' + i, i <= filled ? codes[i - 1] : '');
                }
                _$('pmBCParser').value = '';
                App.toast(`${filled} backup code${filled > 1 ? 's' : ''} filled`, 'success');
            });
        }

        // Close modals on overlay click
        ['profileModalOverlay', 'batchLoginModalOverlay'].forEach(id => {
            const el = _$(id);
            if (el) el.addEventListener('click', (e) => { if (e.target === el) { if (id === 'profileModalOverlay') closeModal(); else closeBatchLoginModal(); } });
        });
        const _bookmarkOverlay = _$('bookmarkModalOverlay');
        if (_bookmarkOverlay) _bookmarkOverlay.addEventListener('click', (e) => { if (e.target === _bookmarkOverlay) _closeBookmarkModal(); });

        // Context menu actions
        const ctxMenu = _$('pmContextMenu');
        if (ctxMenu) {
            ctxMenu.querySelectorAll('a[data-action]').forEach(a => {
                a.addEventListener('click', (e) => { e.preventDefault(); _handleContextAction(a.dataset.action); });
            });
        }

        // Load storage config — deferred until token is available
        const _loadStorageConfig = async () => {
            try {
                const data = await _api('/api/profiles/config');
                if (data.success && data.config && data.config.storage_path) {
                    _setVal('profileStoragePath', data.config.storage_path);
                }
            } catch (e) { /* silent */ }
        };

        // Load groups and config when token becomes available
        if (App.state.apiToken) {
            _loadStorageConfig();
            _loadGroups();
        } else {
            // Wait for token, then load
            const _waitAndLoad = async () => {
                if (App.fetchApiToken) await App.fetchApiToken();
                _loadStorageConfig();
                _loadGroups();
            };
            _waitAndLoad();
        }
    };

    // ── Extension Manager ────────────────────────────────────────────────

    function _openExtModal() {
        const overlay = _$('extModalOverlay');
        if (overlay) overlay.classList.add('active');
        _loadExtList();
    }

    function _closeExtModal() {
        const overlay = _$('extModalOverlay');
        if (overlay) overlay.classList.remove('active');
    }

    async function _loadExtList() {
        const container = _$('extList');
        if (!container) return;
        container.innerHTML = '<div style="color:#64748b;font-size:12px;padding:8px;">Loading…</div>';
        try {
            const data = await _api('/api/extensions');
            if (!data.success) { container.innerHTML = `<div style="color:#f87171;font-size:12px;">${_esc(data.message||'Error')}</div>`; return; }
            const exts = data.extensions || [];
            if (!exts.length) { container.innerHTML = '<div style="color:#64748b;font-size:12px;padding:8px;">No extensions installed yet.</div>'; return; }
            container.innerHTML = exts.map(e => `
                <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;background:#0f1629;border-radius:6px;margin-bottom:6px;border:1px solid #1e2d52;">
                    <i class="fas fa-puzzle-piece" style="color:#8b5cf6;font-size:14px;flex-shrink:0;"></i>
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:13px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${_esc(e.name)}</div>
                        <div style="font-size:10px;color:#475569;font-family:monospace;">${_esc(e.id)}</div>
                    </div>
                    <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:#94a3b8;cursor:pointer;white-space:nowrap;" title="Apply to all profiles on launch">
                        <input type="checkbox" data-ext-id="${_esc(e.id)}" data-field="apply_to_all" ${e.apply_to_all ? 'checked' : ''}
                            style="accent-color:#8b5cf6;"> All
                    </label>
                    <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:#94a3b8;cursor:pointer;white-space:nowrap;" title="Pin to Chrome toolbar on launch">
                        <input type="checkbox" data-ext-id="${_esc(e.id)}" data-field="pinned" ${e.pinned ? 'checked' : ''}
                            style="accent-color:#f59e0b;"> Pin
                    </label>
                    <button class="btn btn-sm" data-del-ext="${_esc(e.id)}"
                        style="background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.25);padding:4px 8px;"
                        title="Remove extension">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>`).join('');
            // Wire up checkboxes
            container.querySelectorAll('[data-ext-id]').forEach(cb => {
                cb.addEventListener('change', async () => {
                    const body = {}; body[cb.dataset.field] = cb.checked;
                    try { await _api(`/api/extensions/${cb.dataset.extId}`, { method: 'PATCH', body: JSON.stringify(body) }); }
                    catch(e) { App.toast('Update failed', 'error'); }
                });
            });
            // Wire up delete buttons
            container.querySelectorAll('[data-del-ext]').forEach(btn => {
                btn.addEventListener('click', async () => {
                    if (!(await App.confirm('Remove this extension?', 'Remove', 'btn-danger', 'fa-trash-alt'))) return;
                    try {
                        const d = await _api(`/api/extensions/${btn.dataset.delExt}`, { method: 'DELETE' });
                        if (d.success) _loadExtList();
                        else App.toast(d.message || 'Delete failed', 'error');
                    } catch(e) { App.toast('Error: ' + e.message, 'error'); }
                });
            });
        } catch(e) { container.innerHTML = `<div style="color:#f87171;font-size:12px;">Error: ${_esc(e.message)}</div>`; }
    }

    async function _extInstallUrl() {
        const input = _$('extUrlInput');
        const url = (input ? input.value : '').trim();
        if (!url) { App.toast('Enter a Chrome Web Store URL or extension ID', 'warn'); return; }
        const btn = _$('extInstallUrlBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing…'; }
        try {
            const data = await _api('/api/extensions/install-url', { method: 'POST', body: JSON.stringify({ url }) });
            if (data.success) {
                App.toast(`Installed: ${data.name}`, 'success');
                if (input) input.value = '';
                _loadExtList();
            } else {
                App.toast(data.message || 'Install failed', 'error');
            }
        } catch(e) { App.toast('Error: ' + e.message, 'error'); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-download"></i> Install'; } }
    }

    // ═══════════════════════════════════════════════════════════════════
    // DUPLICATE PROFILE CHECK
    // ═══════════════════════════════════════════════════════════════════

    let _dupSelectedIds = new Set();

    function _openDuplicateCheckModal() {
        const modal = _$('duplicateCheckModal');
        if (modal) modal.style.display = 'flex';
        _dupSelectedIds = new Set();
        _renderDupList();
    }

    function _closeDuplicateCheckModal() {
        const modal = _$('duplicateCheckModal');
        if (modal) modal.style.display = 'none';
    }

    async function _renderDupList() {
        const list = _$('duplicateCheckList');
        const summary = _$('duplicateCheckSummary');
        if (!list) return;
        list.innerHTML = '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:30px;"><i class="fas fa-spinner fa-spin"></i></div>';
        if (summary) summary.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning profiles&hellip;';
        try {
            const data = await _api('/api/profiles/duplicates');
            if (!data.success) {
                list.innerHTML = `<div style="color:#f87171;font-size:13px;text-align:center;padding:20px;">${_esc(data.message || 'Error scanning profiles')}</div>`;
                return;
            }
            const groups = data.duplicates || [];
            if (summary) {
                if (!groups.length) {
                    summary.innerHTML = '<i class="fas fa-check-circle" style="color:#4ade80;"></i> No duplicate profiles found — all emails are unique.';
                } else {
                    const totalDups = groups.reduce((s, g) => s + g.count - 1, 0);
                    summary.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:#f59e0b;"></i> <strong style="color:#f59e0b;">${groups.length}</strong> duplicate email groups &nbsp;·&nbsp; <strong style="color:#f87171;">${totalDups}</strong> extra profiles (oldest pre-selected)`;
                }
            }
            if (!groups.length) {
                list.innerHTML = '<div style="color:#4ade80;font-size:13px;text-align:center;padding:30px;"><i class="fas fa-check-circle"></i> All profiles have unique emails.</div>';
                return;
            }
            list.innerHTML = groups.map(g => {
                const rows = g.profiles.map((p, idx) => {
                    const isOldest = idx === g.profiles.length - 1 || (idx > 0);
                    const checked = isOldest ? 'checked' : '';
                    if (isOldest) _dupSelectedIds.add(p.id);
                    const createdLabel = p.created_at ? p.created_at.replace('T', ' ').slice(0, 16) : '—';
                    const badge = idx === 0
                        ? '<span style="font-size:10px;background:rgba(34,197,94,0.15);color:#4ade80;border:1px solid rgba(34,197,94,0.3);border-radius:4px;padding:1px 6px;margin-left:6px;">newest</span>'
                        : '';
                    return `
                        <label style="display:flex;align-items:center;gap:10px;padding:8px 10px;background:#0f1629;border-radius:6px;margin-bottom:4px;border:1px solid #1e2d52;cursor:pointer;">
                            <input type="checkbox" class="dup-row-cb" data-profile-id="${_esc(p.id)}" ${checked}
                                style="width:15px;height:15px;accent-color:#f87171;flex-shrink:0;">
                            <div style="flex:1;min-width:0;">
                                <div style="font-size:13px;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                                    ${_esc(p.name || p.id)}${badge}
                                </div>
                                <div style="font-size:11px;color:#64748b;">
                                    Group: ${_esc(p.group || 'default')} &nbsp;·&nbsp; Created: ${_esc(createdLabel)}
                                </div>
                            </div>
                        </label>`;
                }).join('');
                return `
                    <div style="background:rgba(245,158,11,0.04);border:1px solid rgba(245,158,11,0.18);border-radius:8px;padding:10px 12px;">
                        <div style="font-size:12px;color:#fbbf24;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px;">
                            <i class="fas fa-envelope"></i> ${_esc(g.email)}
                            <span style="font-size:11px;color:#94a3b8;font-weight:400;">${g.count} profiles</span>
                        </div>
                        ${rows}
                    </div>`;
            }).join('');
            _dupUpdateCount();
            // Wire up checkboxes
            list.querySelectorAll('.dup-row-cb').forEach(cb => {
                cb.addEventListener('change', () => {
                    if (cb.checked) _dupSelectedIds.add(cb.dataset.profileId);
                    else _dupSelectedIds.delete(cb.dataset.profileId);
                    _dupUpdateCount();
                });
            });
        } catch(e) {
            list.innerHTML = `<div style="color:#f87171;font-size:13px;text-align:center;padding:20px;">Error: ${_esc(e.message)}</div>`;
        }
    }

    function _dupUpdateCount() {
        const n = _dupSelectedIds.size;
        const countEl = _$('dupSelectedCount');
        const deleteCountEl = _$('dupDeleteCount');
        const deleteBtn = _$('duplicateCheckDeleteBtn');
        if (countEl) countEl.textContent = n;
        if (deleteCountEl) deleteCountEl.textContent = n;
        if (deleteBtn) deleteBtn.disabled = n === 0;
    }

    async function _dupDeleteSelected() {
        const ids = [..._dupSelectedIds];
        if (!ids.length) return;
        const confirmed = await App.confirm(
            `Delete ${ids.length} duplicate profile${ids.length > 1 ? 's' : ''}? This cannot be undone.`,
            'Delete', 'btn-danger', 'fa-trash'
        );
        if (!confirmed) return;
        const btn = _$('duplicateCheckDeleteBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting…'; }
        try {
            const data = await _api('/api/profiles/delete-bulk', {
                method: 'DELETE',
                body: JSON.stringify({ ids })
            });
            if (data.success) {
                App.toast(`Deleting ${ids.length} profiles…`, 'info');
                // Poll until done then re-render
                const poll = setInterval(async () => {
                    try {
                        const s = await _api('/api/profiles/delete-bulk-status');
                        if (s.progress && s.progress.status !== 'processing') {
                            clearInterval(poll);
                            App.toast(`Deleted ${s.progress.deleted || ids.length} duplicate profiles`, 'success');
                            _dupSelectedIds = new Set();
                            _renderDupList();
                            _loadProfiles();
                        }
                    } catch(e) { clearInterval(poll); }
                }, 800);
            } else {
                App.toast(data.message || 'Delete failed', 'error');
                if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fas fa-trash"></i> Delete Selected (<span id="dupDeleteCount">${ids.length}</span>)`; }
            }
        } catch(e) {
            App.toast('Error: ' + e.message, 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fas fa-trash"></i> Delete Selected (<span id="dupDeleteCount">${ids.length}</span>)`; }
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // GMAIL CAMPAIGN
    // ═══════════════════════════════════════════════════════════════════
    let _gmailPollTimer = null;
    let _gmailCampaignName = '';
    let _gmailIdentities = [];

    function _openGmailCampaignModal() {
        const ov = _$('gmailCampaignOverlay');
        if (ov) ov.style.display = 'flex';
        // Attach proxy URL paste listener now that DOM is visible
        setTimeout(_attachProxyUrlListener, 50);
    }
    function _closeGmailCampaignModal() {
        const ov = _$('gmailCampaignOverlay');
        if (ov) ov.style.display = 'none';
        if (_gmailPollTimer) { clearInterval(_gmailPollTimer); _gmailPollTimer = null; }
    }

    // Tab switching
    document.addEventListener('click', e => {
        const tab = e.target.closest('.gmail-tab');
        if (!tab) return;
        const target = tab.dataset.tab;
        document.querySelectorAll('.gmail-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.gmail-tab-content').forEach(c => c.style.display = 'none');
        const panel = _$('gmailTab' + target.charAt(0).toUpperCase() + target.slice(1));
        if (panel) panel.style.display = '';
    });

    // ── Proxy URL Auto-Parser ─────────────────────────────────────────
    // Supports any of these formats:
    //   http://user:pass@host:port
    //   socks5://host:port
    //   host:port
    //   user:pass@host:port
    function _parseProxyUrl(raw) {
        raw = (raw || '').trim();
        if (!raw) return null;

        let proto = 'http', userInfo = '', hostPort = '';

        // Extract protocol
        const protoMatch = raw.match(/^(https?|socks[45]?):\/\//i);
        if (protoMatch) {
            proto = protoMatch[1].toLowerCase().replace('https', 'http');
            raw = raw.slice(protoMatch[0].length);
        }

        // Extract user:pass@host:port
        const atIdx = raw.lastIndexOf('@');
        if (atIdx !== -1) {
            userInfo = raw.slice(0, atIdx);
            hostPort = raw.slice(atIdx + 1);
        } else {
            hostPort = raw;
        }

        let user = '', pass = '';
        if (userInfo) {
            const colonIdx = userInfo.indexOf(':');
            if (colonIdx !== -1) {
                user = userInfo.slice(0, colonIdx);
                pass = userInfo.slice(colonIdx + 1);
            } else {
                user = userInfo;
            }
        }

        return { proto, hostPort: hostPort.trim(), user, pass };
    }

    function _applyProxyParse(raw) {
        const parsed = _parseProxyUrl(raw);
        if (!parsed || !parsed.hostPort) return;

        const setVal = (id, val) => { const el = _$(id); if (el) el.value = val; };
        setVal('gmailProxyServer', parsed.hostPort);
        setVal('gmailProxyUser',   parsed.user);
        setVal('gmailProxyPass',   parsed.pass);

        const typeEl = _$('gmailProxyType');
        if (typeEl) {
            const t = parsed.proto;
            typeEl.value = (t === 'socks5' || t === 'socks4') ? t : 'http';
        }
        App.toast(`✅ Proxy parsed: ${parsed.hostPort}`, 'success');
    }

    // Attach listener when modal opens (elements may not exist on DOMContentLoaded)
    function _attachProxyUrlListener() {
        const el = _$('gmailProxyUrl');
        if (!el || el._proxyBound) return;
        el._proxyBound = true;
        el.addEventListener('paste', e => {
            setTimeout(() => _applyProxyParse(el.value), 10);
        });
        el.addEventListener('change', () => _applyProxyParse(el.value));
    }

    // Generate identity preview
    async function _gmailGenerateIdentities() {
        const count = parseInt((_$('gmailAccountCount') || {}).value || '5');
        try {
            const data = await _api('/api/gmail-campaign/generate-identities', {
                method: 'POST', body: JSON.stringify({ count })
            });
            if (data.ok && data.identities) {
                _gmailIdentities = data.identities;
                const tbody = _$('gmailIdentityTableBody');
                if (tbody) {
                    tbody.innerHTML = data.identities.map((id, i) =>
                        `<tr style="border-top:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:5px 8px;color:#64748b;">${i+1}</td>
                            <td style="padding:5px 8px;">${id.first_name} ${id.last_name}</td>
                            <td style="padding:5px 8px;color:#4ade80;">${id.username}@gmail.com</td>
                            <td style="padding:5px 8px;color:#94a3b8;font-family:monospace;font-size:11px;">${id.password}</td>
                            <td style="padding:5px 8px;color:#64748b;">${id.birth_month}/${id.birth_day}/${id.birth_year}</td>
                        </tr>`
                    ).join('');
                }
                const cnt = _$('gmailIdentityCount');
                if (cnt) cnt.textContent = data.identities.length + ' identities';
            }
        } catch(e) { App.toast('Error generating identities: ' + e.message, 'error'); }
    }

    // Check SMS balance
    async function _gmailCheckSmsBalance() {
        const provider = (_$('gmailSmsProvider') || {}).value;
        const apiKey = (_$('gmailSmsApiKey') || {}).value;
        if (!apiKey) { App.toast('Enter SMS API key first', 'warn'); return; }
        try {
            const data = await _api('/api/gmail-campaign/sms-balance', {
                method: 'POST', body: JSON.stringify({ provider, api_key: apiKey })
            });
            const el = _$('gmailSmsBalance');
            if (el) {
                if (data.ok) {
                    el.textContent = `💰 Balance: $${parseFloat(data.balance).toFixed(2)}`;
                    el.style.color = data.balance > 1 ? '#4ade80' : '#f87171';
                } else {
                    el.textContent = '❌ ' + (data.error || 'Failed');
                    el.style.color = '#f87171';
                }
            }
        } catch(e) { App.toast('Balance check failed', 'error'); }
    }

    // Start campaign
    async function _gmailStartCampaign() {
        const name = (_$('gmailCampaignName') || {}).value || ('Campaign_' + Date.now());

        // Read proxy config
        const proxyServer = ((_$('gmailProxyServer') || {}).value || '').trim();
        const proxyUser   = ((_$('gmailProxyUser')   || {}).value || '').trim();
        const proxyPass   = ((_$('gmailProxyPass')   || {}).value || '').trim();
        const proxyType   = ((_$('gmailProxyType')   || {}).value || 'http');

        let proxyConfig = null;
        if (proxyServer) {
            const prefix = proxyType === 'http' ? 'http' : proxyType;
            proxyConfig = {
                server: `${prefix}://${proxyServer}`,
                username: proxyUser,
                password: proxyPass,
            };
        }

        const config = {
            sms_provider: (_$('gmailSmsProvider') || {}).value,
            sms_api_key: (_$('gmailSmsApiKey') || {}).value,
            sms_country: (_$('gmailSmsCountry') || {}).value || 'india',
            captcha_provider: (_$('gmailCaptchaProvider') || {}).value,
            captcha_api_key: (_$('gmailCaptchaApiKey') || {}).value,
            worker_count: parseInt((_$('gmailWorkerCount') || {}).value || '1'),
            warmup_enabled: (_$('gmailWarmupEnabled') || {}).checked !== false,
            show_browser: (_$('gmailShowBrowser') || {}).checked !== false,
            proxy: proxyConfig,
        };

        if (!config.sms_api_key) {
            App.toast('SMS API key is required for phone verification', 'warn');
            return;
        }

        if (!proxyConfig) {
            // Warn but don't block — user may not have proxy
            App.toast('⚠️ No proxy set — Google may show QR verification', 'warn');
        }

        const count = parseInt((_$('gmailAccountCount') || {}).value || '5');
        try {
            // Create campaign
            const createData = await _api('/api/gmail-campaign/create', {
                method: 'POST',
                body: JSON.stringify({
                    name, config, count,
                    identities: _gmailIdentities.length ? _gmailIdentities : null
                })
            });
            if (!createData.ok) { App.toast(createData.error || 'Create failed', 'error'); return; }

            _gmailCampaignName = name;

            // Start campaign
            const startData = await _api('/api/gmail-campaign/start', {
                method: 'POST', body: JSON.stringify({ name })
            });
            if (!startData.ok) { App.toast(startData.error || 'Start failed', 'error'); return; }

            App.toast(`Campaign "${name}" started with ${count} accounts!`, 'success');

            // Switch to progress tab
            document.querySelectorAll('.gmail-tab').forEach(t => t.classList.remove('active'));
            document.querySelector('.gmail-tab[data-tab="progress"]').classList.add('active');
            document.querySelectorAll('.gmail-tab-content').forEach(c => c.style.display = 'none');
            _$('gmailTabProgress').style.display = '';

            // Show stop, hide start
            _$('gmailStartCampaign').style.display = 'none';
            _$('gmailStopCampaign').style.display = '';

            // Start polling
            _gmailPollTimer = setInterval(_gmailPollStatus, 3000);
            _gmailPollStatus();

        } catch(e) { App.toast('Campaign error: ' + e.message, 'error'); }
    }

    // Stop campaign
    async function _gmailStopCampaign() {
        if (!_gmailCampaignName) return;
        try {
            await _api('/api/gmail-campaign/stop', {
                method: 'POST', body: JSON.stringify({ name: _gmailCampaignName })
            });
            App.toast('Campaign stopping...', 'info');
            _$('gmailStartCampaign').style.display = '';
            _$('gmailStopCampaign').style.display = 'none';
            if (_gmailPollTimer) { clearInterval(_gmailPollTimer); _gmailPollTimer = null; }
        } catch(e) { App.toast('Stop failed: ' + e.message, 'error'); }
    }

    // Poll campaign status
    async function _gmailPollStatus() {
        if (!_gmailCampaignName) return;
        try {
            const data = await _api(`/api/gmail-campaign/status?name=${encodeURIComponent(_gmailCampaignName)}`);
            if (!data.ok || !data.campaign) return;

            const c = data.campaign;
            const total = c.total || 1;
            const done = (c.success || 0) + (c.failed || 0);

            // Update progress bar
            const pct = Math.round((done / total) * 100);
            const fill = _$('gmailProgressFill');
            if (fill) fill.style.width = pct + '%';
            const text = _$('gmailProgressText');
            if (text) text.textContent = `${done}/${total}`;

            // Update stats
            const s = id => _$(id);
            if (s('gmailStatSuccess')) s('gmailStatSuccess').textContent = c.success || 0;
            if (s('gmailStatFailed')) s('gmailStatFailed').textContent = c.failed || 0;
            if (s('gmailStatActive')) s('gmailStatActive').textContent = (c.warming || 0) + (c.creating || 0);
            if (s('gmailStatPending')) s('gmailStatPending').textContent = c.pending || 0;

            // Update log
            const log = _$('gmailProgressLog');
            if (log && c.accounts) {
                log.innerHTML = c.accounts.map(a => {
                    const color = a.status === 'success' ? '#4ade80' :
                                  a.status === 'failed' ? '#f87171' :
                                  a.status === 'creating' || a.status === 'warming' ? '#fbbf24' : '#64748b';
                    const icon = a.status === 'success' ? '✅' :
                                 a.status === 'failed' ? '❌' :
                                 a.status === 'creating' ? '⏳' :
                                 a.status === 'warming' ? '🔥' : '⏸';
                    return `<div style="padding:3px 0;color:${color};border-bottom:1px solid rgba(255,255,255,0.03);">
                        ${icon} <b>${a.username || '?'}@gmail.com</b> — ${a.status}${a.error ? ' (' + a.error + ')' : ''}
                    </div>`;
                }).join('');
            }

            // Auto-stop polling when complete
            if (c.status === 'completed' || done >= total) {
                if (_gmailPollTimer) { clearInterval(_gmailPollTimer); _gmailPollTimer = null; }
                _$('gmailStartCampaign').style.display = '';
                _$('gmailStopCampaign').style.display = 'none';
            }
        } catch(e) { /* silent poll failure */ }
    }

    // Wire up buttons
    _btn('profileCreateGmailBtn', _openGmailCampaignModal);
    _btn('gmailCampaignClose', _closeGmailCampaignModal);
    _btn('gmailCampaignCancel', _closeGmailCampaignModal);
    _btn('gmailGenerateIdentities', _gmailGenerateIdentities);
    _btn('gmailCheckSmsBalance', _gmailCheckSmsBalance);
    _btn('gmailStartCampaign', _gmailStartCampaign);
    _btn('gmailStopCampaign', _gmailStopCampaign);

    // ─────────────────────────────────────────────────────────────
    // Task 13: Review-Stats drill-down modal
    // ─────────────────────────────────────────────────────────────

    let _rsModalState = { profileId: null, full: null, filter: 'all', search: '' };

    async function _openReviewStatsModal(profileId) {
        _rsModalState = { profileId, full: null, filter: 'all', search: '' };
        document.getElementById('pmRsModal').style.display = '';
        document.getElementById('pmRsList').innerHTML =
            '<div style="padding:20px;text-align:center;color:#9ca3af;"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';

        // Reset filter buttons to "all"
        document.querySelectorAll('#pmRsFilters .pm-rs-filter-btn')
            .forEach(b => b.classList.toggle('pm-rs-active', b.getAttribute('data-rs-filter') === 'all'));
        const searchEl = document.getElementById('pmRsSearch');
        if (searchEl) searchEl.value = '';

        try {
            const resp = await App.apiFetch(`/api/profiles/${encodeURIComponent(profileId)}/review-stats`);
            if (resp.status === 404) {
                _rsModalState.full = null;
                document.getElementById('pmRsList').innerHTML =
                    '<div style="padding:20px;text-align:center;color:#9ca3af;">Never scanned. Click Rescan to start.</div>';
                document.getElementById('pmRsSummary').textContent = '';
                document.getElementById('pmRsModalTitle').textContent = profileId;
                return;
            }
            const data = await resp.json();
            if (!data.success) throw new Error(data.message || 'fetch failed');
            _rsModalState.full = data.stats;
            _renderReviewStatsModal();
        } catch (e) {
            document.getElementById('pmRsList').innerHTML =
                `<div style="padding:20px;text-align:center;color:#fca5a5;">Error: ${_esc(e.message)}</div>`;
        }
    }

    function _renderReviewStatsModal() {
        const s = _rsModalState.full;
        if (!s) return;
        document.getElementById('pmRsModalTitle').textContent = `${s.email} — Review Stats`;
        const notPosted = (s.pending || 0) + (s.not_posted || 0);
        const errBanner = (s.scan_status === 'error')
            ? `<div style="margin-top:6px;padding:8px 10px;background:#3b1d1d;border:1px solid #7f1d1d;border-radius:6px;color:#fca5a5;font-size:12px;">` +
              `<b>⚠ Scan failed:</b> ${_esc(_reviewStatsErrorLabel(s.scan_error))}` +
              (s.scan_error ? `<br><span style="font-size:11px;color:#9ca3af;">Details: ${_esc(s.scan_error)}</span>` : '') +
              `</div>`
            : '';
        document.getElementById('pmRsSummary').innerHTML =
            `Total: <b>${s.total||0}</b>  ·  Live: <b style="color:#6ee7b7">${s.live||0}</b>  ·  Not Posted: <b style="color:#fca5a5">${notPosted}</b>` +
            `<br><span style="font-size:11px;color:#9ca3af;">Last scanned: ${_esc(_relativeTime(s.last_scanned))}</span>` +
            errBanner;

        const filter = _rsModalState.filter;
        const search = _rsModalState.search.toLowerCase();

        const filtered = (s.reviews || []).filter(r => {
            if (filter !== 'all' && r.status !== filter) return false;
            if (search && !((r.business || '').toLowerCase().includes(search)
                         || (r.text || '').toLowerCase().includes(search))) return false;
            return true;
        });

        const list = document.getElementById('pmRsList');
        if (!filtered.length) {
            list.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af;">No reviews match.</div>';
            return;
        }

        list.innerHTML = filtered.map(r => {
            const stars = '★'.repeat(r.stars || 0) + '☆'.repeat(Math.max(0, 5 - (r.stars || 0)));
            const statusLabel = r.status === 'not_posted' ? 'NOT POSTED' : (r.status || '').toUpperCase();
            // "visit" — public place link extracted from the review row
            // during scrape. Works without Google login. Falls back to a
            // Maps search of business + address when the scraper couldn't
            // capture a direct link.
            let visitHref = (r.share_link || '').trim();
            if (!visitHref && (r.business || r.address)) {
                const q = ((r.business || '') + ' ' + (r.address || '')).trim();
                visitHref = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
            }
            return `
            <div class="pm-rs-item">
                <div class="pm-rs-item-stars">${_esc(stars)}</div>
                <div>
                    <div class="pm-rs-item-biz">${_esc(r.business || '(unknown)')}</div>
                    ${r.address ? `<div class="pm-rs-item-addr">${_esc(r.address)}</div>` : ''}
                    ${r.text ? `<div class="pm-rs-item-text">"${_esc(r.text)}"</div>` : ''}
                </div>
                <div class="pm-rs-item-meta">
                    <span class="pm-rs-item-status pm-rs-status-${_esc(r.status || 'unknown')}">${_esc(statusLabel)}</span>
                    <div style="margin-top:4px;">${_esc(r.time || '')}</div>
                    ${visitHref ? `<a class="pm-rs-item-visit" href="${visitHref}" target="_blank" rel="noreferrer">visit ↗</a>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    function _initReviewStatsModal() {
        const modal = document.getElementById('pmRsModal');
        if (!modal) return;
        document.getElementById('pmRsCloseBtn').addEventListener('click', () => {
            modal.style.display = 'none';
        });
        modal.querySelector('.pm-modal-backdrop')?.addEventListener('click', () => {
            modal.style.display = 'none';
        });
        document.getElementById('pmRsFilters').addEventListener('click', (e) => {
            const b = e.target.closest('button[data-rs-filter]');
            if (!b) return;
            document.querySelectorAll('#pmRsFilters .pm-rs-filter-btn')
                .forEach(x => x.classList.remove('pm-rs-active'));
            b.classList.add('pm-rs-active');
            _rsModalState.filter = b.getAttribute('data-rs-filter');
            _renderReviewStatsModal();
        });
        document.getElementById('pmRsSearch').addEventListener('input', (e) => {
            _rsModalState.search = e.target.value || '';
            _renderReviewStatsModal();
        });
        document.getElementById('pmRsRescanBtn').addEventListener('click', async () => {
            if (!_rsModalState.profileId) return;
            try {
                const r = await App.apiFetch('/api/profiles/review-stats/scan', {
                    method: 'POST',
                    body: JSON.stringify({ profile_ids: [_rsModalState.profileId], num_workers: 1 }),
                });
                const d = await r.json();
                if (d.success) {
                    App.toast && App.toast('Rescan queued', 'success');
                    _startReviewStatsPoll();
                } else {
                    App.toast && App.toast(d.message || 'Failed', 'error');
                }
            } catch (e) { App.toast && App.toast('Backend unreachable', 'error'); }
        });
    }

    // Delegated click handler: badge → open drill-down modal
    document.addEventListener('click', (e) => {
        const rsBadge = e.target.closest('.pm-rs-badge[data-profile-id]');
        if (rsBadge) {
            e.preventDefault();
            e.stopPropagation();
            _openReviewStatsModal(rsBadge.getAttribute('data-profile-id'));
            return;
        }
    });

})(window.App || (window.App = {}));
