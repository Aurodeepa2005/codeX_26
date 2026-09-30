/**
 * StandardMatch AI — Frontend Application
 * Smart India Hackathon 2026
 *
 * Handles: tab navigation, search, tender analysis, browse,
 * dashboard, modals, and data export.
 */

const API = '';  // Same origin

// ─── State ───────────────────────────────────────────────────
let currentTab = 'search';
let lastResults = [];
let allStandards = [];
let currentCategory = 'all';

// ─── Init ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadSampleChips();
    loadDashboard();
    loadBrowse();

    // Enter key triggers search
    const input = document.getElementById('search-input');
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') doSearch();
        });
    }
});

// ─── Tab Navigation ──────────────────────────────────────────
function initTabs() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            switchTab(tab);
        });
    });
}

function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    const navBtn = document.querySelector(`[data-tab="${tab}"]`);
    const panel = document.getElementById(`panel-${tab}`);
    if (navBtn) navBtn.classList.add('active');
    if (panel) panel.classList.add('active');

    if (tab === 'dashboard') loadDashboard();
    if (tab === 'browse') loadBrowse();
}

// ─── Search ──────────────────────────────────────────────────
async function doSearch() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    showLoading('search');
    hideResults();

    try {
        const res = await fetch(`${API}/api/recommend`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: 15 }),
        });
        const data = await res.json();
        lastResults = data.results || [];
        renderResults(data);
    } catch (err) {
        console.error('Search error:', err);
        showError('search');
    } finally {
        hideLoading('search');
    }
}

function renderResults(data) {
    const area = document.getElementById('results-area');
    const grid = document.getElementById('results-grid');
    const title = document.getElementById('results-title');

    if (!data.results || data.results.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <div class="empty-state-text">No matching standards found. Try different keywords or a broader description.</div>
            </div>`;
        area.style.display = 'block';
        return;
    }

    title.textContent = `${data.total_results} Standard${data.total_results > 1 ? 's' : ''} Found`;
    grid.innerHTML = data.results.map((r, i) => renderResultCard(r, i)).join('');
    area.style.display = 'block';
}

function renderResultCard(r, index) {
    const statusClass = getStatusClass(r.status);
    const confClass = r.confidence >= 80 ? 'high' : r.confidence >= 55 ? 'medium' : 'low';

    const badges = [
        `<span class="badge ${statusClass}">${escHtml(r.status || 'Active')}</span>`,
    ];
    if (r.qco_mandatory) {
        badges.push(`<span class="badge badge-qco">⚠ QCO Mandatory</span>`);
    }

    const keywords = (r.matched_keywords || [])
        .map(k => `<span class="kw-tag">${escHtml(k)}</span>`)
        .join('');

    return `
    <div class="result-card" onclick="openStandardModal('${escAttr(r.is_number)}')" style="animation-delay:${index * 0.06}s">
        <div class="card-top">
            <div class="card-top-left">
                <div class="card-is-number">${escHtml(r.is_number)}</div>
                <div class="card-title">${escHtml(r.title)}</div>
            </div>
            <div class="card-badges">${badges.join('')}</div>
        </div>
        <div class="card-confidence">
            <div class="confidence-bar-bg">
                <div class="confidence-bar-fill ${confClass}" style="width:${r.confidence}%"></div>
            </div>
            <div class="confidence-value">${r.confidence}%</div>
        </div>
        <div class="card-evidence">${escHtml(r.scope_evidence || '')}</div>
        ${keywords ? `<div class="card-keywords">${keywords}</div>` : ''}
        <div class="card-meta">
            ${r.year ? `<span class="card-meta-item">📅 ${escHtml(r.year)}</span>` : ''}
            ${r.category ? `<span class="card-meta-item">📁 ${capitalize(r.category)}</span>` : ''}
            ${r.technical_committee ? `<span class="card-meta-item">🏛 ${escHtml(r.technical_committee)}</span>` : ''}
        </div>
    </div>`;
}

// ─── Tender Analysis ─────────────────────────────────────────
async function analyzeTender() {
    const text = document.getElementById('tender-textarea').value.trim();
    if (!text) return;

    showLoading('tender');
    document.getElementById('tender-results').style.display = 'none';

    try {
        const res = await fetch(`${API}/api/analyze-tender`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tender_text: text, top_k_per_item: 3 }),
        });
        const data = await res.json();
        renderTenderResults(data);
    } catch (err) {
        console.error('Tender analysis error:', err);
    } finally {
        hideLoading('tender');
    }
}

function renderTenderResults(data) {
    const container = document.getElementById('tender-results');
    const summary = document.getElementById('tender-summary');
    const items = document.getElementById('tender-items');

    summary.innerHTML = `
        <div class="tender-stat">
            <div class="tender-stat-val">${data.total_items || 0}</div>
            <div class="tender-stat-label">Items Extracted</div>
        </div>
        <div class="tender-stat">
            <div class="tender-stat-val">${data.matched_items || 0}</div>
            <div class="tender-stat-label">Items Matched</div>
        </div>
        <div class="tender-stat">
            <div class="tender-stat-val">${data.unique_standards || 0}</div>
            <div class="tender-stat-label">Standards Identified</div>
        </div>
    `;

    if (!data.items || data.items.length === 0) {
        items.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📄</div>
                <div class="empty-state-text">No procurement items could be matched. Try pasting more detailed specifications.</div>
            </div>`;
    } else {
        items.innerHTML = data.items.map((item, i) => `
            <div class="tender-item" style="animation-delay:${i * 0.08}s">
                <div class="tender-item-header" onclick="this.parentElement.classList.toggle('expanded')">
                    <div class="tender-item-text">${escHtml(item.procurement_item)}</div>
                    <div class="tender-item-count">${item.recommendations.length} standard${item.recommendations.length > 1 ? 's' : ''}</div>
                </div>
                <div class="tender-item-body">
                    ${item.recommendations.map(r => renderMiniCard(r)).join('')}
                </div>
            </div>
        `).join('');
    }

    container.style.display = 'block';
}

function renderMiniCard(r) {
    const statusClass = getStatusClass(r.status);
    return `
    <div class="result-card" onclick="openStandardModal('${escAttr(r.is_number)}')" style="margin-top:10px;padding:14px 16px;">
        <div class="card-top">
            <div class="card-top-left">
                <div class="card-is-number">${escHtml(r.is_number)}</div>
                <div class="card-title" style="font-size:0.88rem">${escHtml(r.title)}</div>
            </div>
            <div class="card-badges">
                <span class="badge ${statusClass}">${escHtml(r.status || 'Active')}</span>
                ${r.qco_mandatory ? '<span class="badge badge-qco">QCO</span>' : ''}
                <span class="confidence-value" style="font-size:0.82rem">${r.confidence}%</span>
            </div>
        </div>
    </div>`;
}

async function loadSampleTender() {
    try {
        const res = await fetch(`${API}/api/sample-tender`);
        const data = await res.json();
        document.getElementById('tender-textarea').value = data.text || '';
    } catch (err) {
        console.error('Failed to load sample tender:', err);
    }
}

// ─── Browse ──────────────────────────────────────────────────
async function loadBrowse() {
    try {
        const [stdRes, catRes] = await Promise.all([
            fetch(`${API}/api/standards`),
            fetch(`${API}/api/categories`),
        ]);
        allStandards = await stdRes.json();
        const categories = await catRes.json();

        // Populate category pills
        const pills = document.getElementById('category-pills');
        let pillsHtml = '<button class="cat-pill active" data-cat="all" onclick="filterCategory(\'all\', this)">All</button>';
        categories.forEach(c => {
            pillsHtml += `<button class="cat-pill" data-cat="${escAttr(c.name)}" onclick="filterCategory('${escAttr(c.name)}', this)">${capitalize(c.name)} (${c.count})</button>`;
        });
        pills.innerHTML = pillsHtml;

        renderBrowse(allStandards);
    } catch (err) {
        console.error('Browse load error:', err);
    }
}

function filterCategory(cat, el) {
    currentCategory = cat;
    document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
    if (el) el.classList.add('active');
    filterBrowse();
}

function filterBrowse() {
    const search = (document.getElementById('browse-search-input').value || '').toLowerCase();
    let filtered = allStandards;

    if (currentCategory !== 'all') {
        filtered = filtered.filter(s => (s.category || '').toLowerCase() === currentCategory);
    }
    if (search) {
        filtered = filtered.filter(s =>
            (s.is_number || '').toLowerCase().includes(search) ||
            (s.title || '').toLowerCase().includes(search) ||
            (s.scope || '').toLowerCase().includes(search)
        );
    }
    renderBrowse(filtered);
}

function renderBrowse(standards) {
    const grid = document.getElementById('browse-grid');
    if (!standards || standards.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1">
                <div class="empty-state-icon">📋</div>
                <div class="empty-state-text">No standards in database yet. Run the data pipeline to collect standards.</div>
            </div>`;
        return;
    }

    grid.innerHTML = standards.map((s, i) => {
        const statusClass = getStatusClass(s.status);
        const isQco = s.qco_mandatory === true || s.qco_mandatory === 'True';
        return `
        <div class="browse-card" onclick="openStandardModal('${escAttr(s.is_number)}')" style="animation-delay:${Math.min(i * 0.03, 0.5)}s">
            <div class="browse-card-is">${escHtml(s.is_number)}</div>
            <div class="browse-card-title">${escHtml(s.title)}</div>
            <div class="browse-card-meta">
                <span class="badge ${statusClass}">${escHtml(s.status || 'Active')}</span>
                ${isQco ? '<span class="badge badge-qco">QCO</span>' : ''}
                ${s.year ? `<span class="badge" style="background:rgba(255,255,255,0.05);color:var(--text-muted);border:1px solid var(--glass-border)">${escHtml(s.year)}</span>` : ''}
            </div>
        </div>`;
    }).join('');
}

// ─── Dashboard ───────────────────────────────────────────────
async function loadDashboard() {
    try {
        const res = await fetch(`${API}/api/stats`);
        const stats = await res.json();

        animateCounter('stat-total', stats.total_standards || 0);
        animateCounter('stat-active', stats.active_count || 0);
        animateCounter('stat-qco', stats.qco_count || 0);
        animateCounter('stat-cats', (stats.categories || []).length);

        // Category distribution
        const catDiv = document.getElementById('dash-categories');
        const maxCat = Math.max(...(stats.categories || []).map(c => c.count), 1);
        catDiv.innerHTML = (stats.categories || []).map((c, i) => {
            const colors = ['var(--grad-blue)', 'var(--grad-green)', 'var(--grad-saffron)', 'var(--grad-primary)'];
            return `
            <div class="dash-bar-row">
                <span class="dash-bar-label">${capitalize(c.name)}</span>
                <div class="dash-bar-bg">
                    <div class="dash-bar-fill" style="width:${(c.count / maxCat * 100)}%;background:${colors[i % colors.length]}"></div>
                </div>
                <span class="dash-bar-count">${c.count}</span>
            </div>`;
        }).join('') || '<p style="color:var(--text-muted);font-size:0.88rem">No data yet</p>';

        // Status distribution
        const statusDiv = document.getElementById('dash-status');
        const statusDist = stats.status_distribution || {};
        const maxStatus = Math.max(...Object.values(statusDist), 1);
        statusDiv.innerHTML = Object.entries(statusDist).map(([status, count]) => {
            const color = status === 'Active' ? 'var(--grad-green)' :
                          status === 'Revised' ? 'var(--grad-saffron)' :
                          status === 'Withdrawn' ? 'linear-gradient(135deg,#ef4444,#dc2626)' :
                          'var(--grad-blue)';
            return `
            <div class="dash-bar-row">
                <span class="dash-bar-label">${status}</span>
                <div class="dash-bar-bg">
                    <div class="dash-bar-fill" style="width:${(count / maxStatus * 100)}%;background:${color}"></div>
                </div>
                <span class="dash-bar-count">${count}</span>
            </div>`;
        }).join('') || '<p style="color:var(--text-muted);font-size:0.88rem">No data yet</p>';

        // QCO standards
        const qcoDiv = document.getElementById('dash-qco');
        const qcoStandards = allStandards.filter(s => s.qco_mandatory === true || s.qco_mandatory === 'True');
        if (qcoStandards.length > 0) {
            qcoDiv.innerHTML = qcoStandards.map(s => `
                <div class="qco-item">
                    <div class="qco-is">${escHtml(s.is_number)} — ${escHtml(s.title || '').substring(0, 60)}</div>
                    <div class="qco-order">${escHtml(s.qco_order || 'Quality Control Order applies')}</div>
                </div>
            `).join('');
        } else {
            qcoDiv.innerHTML = '<p style="color:var(--text-muted);font-size:0.88rem">QCO standards will appear after data collection</p>';
        }

    } catch (err) {
        console.error('Dashboard load error:', err);
    }
}

// ─── Modal ───────────────────────────────────────────────────
async function openStandardModal(isNumber) {
    try {
        const res = await fetch(`${API}/api/standards/${encodeURIComponent(isNumber)}`);
        const data = await res.json();
        if (data.error) return;

        const modal = document.getElementById('modal-overlay');
        const body = document.getElementById('modal-body');

        const statusClass = getStatusClass(data.status);
        const isQco = data.qco_mandatory === true || data.qco_mandatory === 'True';

        let badges = `<span class="badge ${statusClass}">${escHtml(data.status || 'Active')}</span>`;
        if (isQco) badges += `<span class="badge badge-qco">⚠ QCO Mandatory</span>`;
        if (data.category) badges += `<span class="badge" style="background:rgba(99,102,241,0.1);color:var(--accent-indigo);border:1px solid rgba(99,102,241,0.2)">${capitalize(data.category)}</span>`;

        let relatedHtml = '';
        if (data.related_standards && data.related_standards.length > 0) {
            relatedHtml = `
            <div class="modal-related">
                <div class="modal-section-title">Related Standards</div>
                ${data.related_standards.map(r => `
                    <div class="modal-related-item" onclick="openStandardModal('${escAttr(r.is_number)}')">
                        <span class="modal-related-is">${escHtml(r.is_number)}</span>
                        <span class="modal-related-title">${escHtml((r.title || '').substring(0, 80))}</span>
                    </div>
                `).join('')}
            </div>`;
        }

        body.innerHTML = `
            <div class="modal-is-number">${escHtml(data.is_number)}</div>
            <div class="modal-title">${escHtml(data.title)}</div>
            <div class="modal-badges">${badges}</div>

            <div class="modal-meta-grid">
                <div class="modal-meta-item">
                    <div class="modal-meta-label">Year</div>
                    <div class="modal-meta-value">${escHtml(data.year || 'N/A')}</div>
                </div>
                <div class="modal-meta-item">
                    <div class="modal-meta-label">Technical Committee</div>
                    <div class="modal-meta-value">${escHtml(data.technical_committee || 'N/A')}</div>
                </div>
                <div class="modal-meta-item">
                    <div class="modal-meta-label">ICS Code</div>
                    <div class="modal-meta-value">${escHtml(data.ics_code || 'N/A')}</div>
                </div>
                <div class="modal-meta-item">
                    <div class="modal-meta-label">Category</div>
                    <div class="modal-meta-value">${capitalize(data.category || 'N/A')}</div>
                </div>
            </div>

            ${data.scope ? `
            <div class="modal-section">
                <div class="modal-section-title">Scope</div>
                <div class="modal-section-content">${escHtml(data.scope)}</div>
            </div>` : ''}

            ${isQco ? `
            <div class="modal-section">
                <div class="modal-section-title">Quality Control Order</div>
                <div class="modal-section-content" style="color:var(--accent-saffron)">
                    ⚠ This standard is mandatory under ${escHtml(data.qco_order || 'DPIIT Quality Control Order')}.
                    Products must comply before sale in India.
                </div>
            </div>` : ''}

            ${relatedHtml}

            ${data.source_url ? `<a href="${escAttr(data.source_url)}" target="_blank" rel="noopener" class="modal-link">
                View on BIS Portal
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </a>` : ''}
        `;

        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    } catch (err) {
        console.error('Modal error:', err);
    }
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
    document.body.style.overflow = '';
}

// Close modal on Escape
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
});

// ─── Sample Chips ────────────────────────────────────────────
async function loadSampleChips() {
    try {
        const res = await fetch(`${API}/api/sample-queries`);
        const queries = await res.json();
        const chips = document.getElementById('hint-chips');
        chips.innerHTML = queries.slice(0, 5).map(q =>
            `<button class="hint-chip" onclick="setSearchAndGo('${escAttr(q.query)}')">${escHtml(q.query.substring(0, 50))}${q.query.length > 50 ? '...' : ''}</button>`
        ).join('');
    } catch (err) {
        // Use fallback chips
        const chips = document.getElementById('hint-chips');
        chips.innerHTML = [
            'GI pipes for drinking water',
            'HDPE pipes PN 6',
            'structural steel IS 2062',
            'PVC borewell casing pipes',
        ].map(q => `<button class="hint-chip" onclick="setSearchAndGo('${escAttr(q)}')">${q}</button>`).join('');
    }
}

function setSearchAndGo(query) {
    document.getElementById('search-input').value = query;
    doSearch();
}

// ─── Export ──────────────────────────────────────────────────
function exportResults(format) {
    if (!lastResults || lastResults.length === 0) return;

    if (format === 'csv') {
        const headers = ['IS Number', 'Title', 'Year', 'Status', 'Category', 'Confidence', 'QCO Mandatory', 'Scope Evidence'];
        const rows = lastResults.map(r => [
            r.is_number,
            `"${(r.title || '').replace(/"/g, '""')}"`,
            r.year || '',
            r.status || '',
            r.category || '',
            r.confidence + '%',
            r.qco_mandatory ? 'Yes' : 'No',
            `"${(r.scope_evidence || '').replace(/"/g, '""')}"`,
        ]);

        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        downloadFile(csv, 'standardmatch_results.csv', 'text/csv');
    }
}

function downloadFile(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ─── Utilities ───────────────────────────────────────────────
function showLoading(section) {
    const el = document.getElementById(`loading-${section}`);
    if (el) el.style.display = 'flex';
}
function hideLoading(section) {
    const el = document.getElementById(`loading-${section}`);
    if (el) el.style.display = 'none';
}
function hideResults() {
    const el = document.getElementById('results-area');
    if (el) el.style.display = 'none';
}
function showError(section) {
    const grid = document.getElementById('results-grid');
    if (grid) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">⚠️</div>
                <div class="empty-state-text">Something went wrong. Please check the server and try again.</div>
            </div>`;
        document.getElementById('results-area').style.display = 'block';
    }
}

function getStatusClass(status) {
    if (!status) return 'badge-active';
    const s = status.toLowerCase();
    if (s === 'active')    return 'badge-active';
    if (s === 'revised')   return 'badge-revised';
    if (s === 'withdrawn') return 'badge-withdrawn';
    return 'badge-review';
}

function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function escAttr(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function animateCounter(id, target) {
    const el = document.getElementById(id);
    if (!el) return;
    const duration = 1200;
    const start = performance.now();
    const from = 0;

    function update(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(from + (target - from) * eased);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}
