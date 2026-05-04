  // ── Nearby Locations ─────────────────────────────────────────────
  // Threshold em coordenadas lng/lat do Mapbox — ajustar conforme necessário.
  // O mapa usa valores aprox. entre -1 e 1; 0.005 equivale a uma área pequena.
  const NEARBY_REFRESH_MS = 500;
  let _catCache = null;
  let _locCache = null;
  function _getCategoryName(id) {
    if (!_catCache) {
      _catCache = {};
      try {
        for (const g of window.mapData?.groups || [])
          for (const c of g.categories || [])
            _catCache[String(c.id)] = { title: c.title, icon: c.icon || '' };
      } catch (_) {}
    }
    return _catCache[String(id)] || null;  // { title, icon }
  }
  function _nearbyThreshold() {
    const v = window.__cdSettings && window.__cdSettings.nearbyThreshold;
    return (typeof v === 'number' && v > 0) ? v : 0.005;
  }
  function _nearbyRespectMapVisibility() {
    try {
      const saved = localStorage.getItem(NEARBY_RESPECT_MAP_VISIBILITY_KEY);
      if (saved === '1') return true;
      if (saved === '0') return false;
    } catch (_) {}
    return !(window.__cdSettings && window.__cdSettings.nearbyRespectMapVisibility === false);
  }
  function _setNearbyRespectMapVisibility(value) {
    const enabled = !!value;
    if (!window.__cdSettings) window.__cdSettings = {};
    window.__cdSettings.nearbyRespectMapVisibility = enabled;
    try {
      localStorage.setItem(NEARBY_RESPECT_MAP_VISIBILITY_KEY, enabled ? '1' : '0');
    } catch (_) {}
    return enabled;
  }
  function _nearbyStayInList() {
    try {
      const saved = localStorage.getItem(NEARBY_STAY_IN_LIST_KEY);
      if (saved === '1') return true;
      if (saved === '0') return false;
    } catch (_) {}
    return false;
  }
  function _setNearbyStayInList(value) {
    const enabled = !!value;
    try { localStorage.setItem(NEARBY_STAY_IN_LIST_KEY, enabled ? '1' : '0'); } catch (_) {}
    return enabled;
  }
  function _isMapGenieCategoryVisible(categoryId) {
    if (!_nearbyRespectMapVisibility()) return true;
    const categoriesMap = window.__cdMapGeniePatch?.categories?.categoriesMap;
    if (!categoriesMap || categoryId === undefined || categoryId === null) return true;
    const category = categoriesMap[String(categoryId)];
    return !category || category.visible !== false;
  }
  function _getLocationDetails(id) {
    try {
      if (!_locCache) {
        _locCache = {};
        for (const item of window.mapData?.locations || []) _locCache[String(item.id)] = item;
      }
      return _locCache[String(id)] || null;
    } catch (_) {
      return null;
    }
  }
  function _escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }
  function _renderInlineMarkdown(value) {
    return _escapeHtml(value)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
        (_m, text, url) => {
          const match = url.match(/[?&]locationIds=(\d+)/);
          if (match) return `<a href="#" data-location-id="${match[1]}">${text}</a>`;
          return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`;
        });
  }
  function _renderDescription(value) {
    if (!value) return '';
    return String(value)
      .split(/\n{2,}/)
      .map(part => `<p>${_renderInlineMarkdown(part).replace(/\n/g, '<br>')}</p>`)
      .join('');
  }
  const _NR_SRC   = 'cd-nearby-radius';
  const _NR_FILL  = 'cd-nearby-radius-fill';
  const _NR_LINE  = 'cd-nearby-radius-line';
  const _NS_SRC   = 'cd-nearby-selected';
  const _NS_FILL  = 'cd-nearby-selected-fill';
  const _NS_LINE  = 'cd-nearby-selected-line';
  let _nearbyCircleKey = '';
  let _nearbySelectionKey = '';

  function _buildNearbyCircleGeoJSON(lng, lat) {
    const steps = 64;
    const r = _nearbyThreshold();
    const coords = [];
    for (let i = 0; i <= steps; i++) {
      const a = (i / steps) * 2 * Math.PI;
      coords.push([lng + r * Math.cos(a), lat + r * Math.sin(a)]);
    }
    return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] } };
  }

  function updateNearbyCircle() {
    const m = getMap();
    if (!m) return;
    const show = nearbyControlsEnabled() && !!lastPos;
    const circleKey = show
      ? `${lastPos.lng.toFixed(5)},${lastPos.lat.toFixed(5)},${_nearbyThreshold()}`
      : 'hidden';
    if (circleKey === _nearbyCircleKey) return;
    _nearbyCircleKey = circleKey;
    try {
      if (!m.getSource(_NR_SRC)) {
        if (!show) return;
        m.addSource(_NR_SRC, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        m.addLayer({ id: _NR_FILL, type: 'fill', source: _NR_SRC,
          paint: { 'fill-color': '#ffd060', 'fill-opacity': 0.15 } });
        m.addLayer({ id: _NR_LINE, type: 'line', source: _NR_SRC,
          paint: { 'line-color': '#ffd060', 'line-width': 1.5,
                   'line-opacity': 0.8, 'line-dasharray': [4, 3] } });
      }
      m.getSource(_NR_SRC).setData(
        show ? _buildNearbyCircleGeoJSON(lastPos.lng, lastPos.lat)
             : { type: 'FeatureCollection', features: [] }
      );
    } catch (_) {}
  }

  function _emptyFeatureCollection() {
    return { type: 'FeatureCollection', features: [] };
  }

  function _selectedLocationFeature(lng, lat) {
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: {}
    };
  }

  function updateNearbySelection(item, shouldPan) {
    const m = getMap();
    if (!m || !item || typeof item.lng !== 'number' || typeof item.lat !== 'number') {
      clearNearbySelection(false);
      return;
    }
    const key = `${item.id}:${item.lng.toFixed(6)},${item.lat.toFixed(6)}`;
    nearbySelectionActive = true;
    try {
      if (!m.getSource(_NS_SRC)) {
        m.addSource(_NS_SRC, { type: 'geojson', data: _emptyFeatureCollection() });
        m.addLayer({ id: _NS_FILL, type: 'circle', source: _NS_SRC,
          paint: {
            'circle-radius': 15,
            'circle-color': 'rgba(255,40,40,0.18)',
            'circle-stroke-color': '#ff3838',
            'circle-stroke-width': 3,
            'circle-stroke-opacity': 0.95
          } });
        m.addLayer({ id: _NS_LINE, type: 'circle', source: _NS_SRC,
          paint: {
            'circle-radius': 22,
            'circle-color': 'rgba(255,40,40,0)',
            'circle-stroke-color': '#ff3838',
            'circle-stroke-width': 1.5,
            'circle-stroke-opacity': 0.6
          } });
      }
      if (key !== _nearbySelectionKey) {
        m.getSource(_NS_SRC).setData(_selectedLocationFeature(item.lng, item.lat));
        _nearbySelectionKey = key;
      }
      if (shouldPan) pan(item.lng, item.lat);
    } catch (_) {}
  }

  function clearNearbySelection(restorePlayer) {
    const m = getMap();
    nearbySelectionActive = false;
    _nearbySelectionKey = '';
    try {
      if (m && m.getSource(_NS_SRC)) m.getSource(_NS_SRC).setData(_emptyFeatureCollection());
    } catch (_) {}
    if (restorePlayer && lastPos) pan(lastPos.lng, lastPos.lat);
  }

  function nearbyControlsEnabled() {
    return !!(window.__cdSettings && window.__cdSettings.nearbyControlsEnabled);
  }

  window.__cdUpdateNearbyControls = function() {
    updateNearbyCircle();
    if (nearbyControlsEnabled()) return;
    const popup = nearbyPopup;
    nearbyPopup = null;
    nearbyInputHandler = null;
    clearNearbySelection(true);
    try { if (popup && !popup.closed) popup.close(); } catch (_) {}
  };

  function isNearbyPopupOpen() {
    try {
      return !!(nearbyPopup && !nearbyPopup.closed);
    } catch (_) {
      return false;
    }
  }

  function _sortNearbyItems(a, b) {
    if (a.found !== b.found) return a.found ? 1 : -1;
    return a.dist - b.dist;
  }

  function getNearbyLocations() {
    if (!lastPos || !map) return [];
    try {
      const features = map.getStyle().sources['locations-data']?.data?.features;
      if (!features) return [];
      const t = _nearbyThreshold();
      return features
        .reduce((acc, f) => {
          const categoryId = f.properties.category_id;
          if (!_isMapGenieCategoryVisible(categoryId)) return acc;
          const [lng, lat] = f.geometry.coordinates;
          const dx = lng - lastPos.lng, dy = lat - lastPos.lat;
          const d2 = dx * dx + dy * dy;
          const details = _getLocationDetails(f.properties.locationId);
          const category = details?.category || _getCategoryName(categoryId);
          if (d2 <= t * t) acc.push({
            id: String(f.properties.locationId),
            title: details?.title || f.properties.title || `Location ${f.properties.locationId}`,
            found: !!(window.user?.locations?.[f.properties.locationId]),
            lng,
            lat,
            dist: Math.sqrt(d2),
            category,
            details
          });
          return acc;
        }, [])
        .sort(_sortNearbyItems);
    } catch (_) { return []; }
  }

  // Exposto globalmente para que o popup possa chamar mesmo sem window.opener funcionar
  window.__cdToggleLocation = function(locationId, found) {
    const csrf = document.head.querySelector('meta[name="csrf-token"]')?.content || '';
    fetch(`/api/v1/user/locations/${locationId}`, {
      method: found ? 'PUT' : 'DELETE',
      credentials: 'include',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
        'X-CSRF-TOKEN': csrf,
      }
    }).catch(() => {});
  };

  function openNearbyPopup() {
    if (!nearbyControlsEnabled()) return;
    if (isNearbyPopupOpen()) {
      closeNearbyPopup();
      return;
    }
    nearbyPopup = null;
    nearbyInputHandler = null;

    let items = getNearbyLocations();

    nearbyPopup = window.open('', 'cdNearbyLocations',
      'width=860,height=460,resizable=yes,scrollbars=no');
    if (!nearbyPopup) return;

    let selectedIndex = 0;
    let activeFoundList = items.some(item => !item.found) ? false : items.some(item => item.found);
    let lastDetailsId = null;
    let lastDetailsFound = null;
    const doc = nearbyPopup.document;
    const _iconCssHref = document.head.querySelector('link[href*="crimson-desert-icons"]')?.href || '';
    doc.open();
    doc.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Nearby Locations</title>
  ${_iconCssHref ? `<link rel="stylesheet" href="${_iconCssHref}">` : ''}
  <style>
    html,body{margin:0;width:100%;height:100%;overflow:hidden;
      background:#0f0f1a;color:#e8e8e8;
      font:12px/1.5 'Segoe UI',system-ui,sans-serif}
    *{box-sizing:border-box}
    .wrap{height:100%;display:flex;flex-direction:column;
      background:rgba(12,12,18,.97);border:1px solid rgba(255,208,96,.25)}
    .header{padding:8px 12px;border-bottom:1px solid rgba(255,255,255,.07);
      display:flex;align-items:center;gap:8px;flex-shrink:0}
    .header-title{flex:1;font-size:13px;font-weight:600;color:#ffd060}
    .header-count{font-size:11px;color:#555}
    .header-toggle{height:24px;padding:0 9px;border-radius:4px;border:1px solid rgba(255,208,96,.28);background:rgba(255,208,96,.08);color:#cfc4ad;font:10px 'Segoe UI',sans-serif;cursor:pointer;white-space:nowrap}
    .header-toggle.on{border-color:rgba(96,232,144,.45);background:rgba(96,232,144,.12);color:#60e890}
    .header-toggle.off{border-color:rgba(255,255,255,.12);background:rgba(255,255,255,.04);color:#777}
    .content{flex:1;min-height:0;display:flex}
    .lists{width:430px;flex-shrink:0;display:flex;min-width:0;border-right:1px solid rgba(255,255,255,.07)}
    .list-pane{width:50%;min-width:0;display:flex;flex-direction:column;border-right:1px solid rgba(255,255,255,.06);background:rgba(10,10,15,.72)}
    .list-pane:last-child{border-right:0}
    .list-head{height:30px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 9px;border-bottom:1px solid rgba(255,255,255,.06);font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:#6e7280}
    .list-pane.active .list-head{background:rgba(255,208,96,.08);color:#ffd060}
    .list-count{color:#555}
    .list-pane.active .list-count{color:#a88d40}
    .list{flex:1;min-height:0;overflow-y:auto;padding:4px}
    .details{flex:1;min-width:0;overflow-y:auto;background:rgba(8,8,12,.96)}
    .details-empty{height:100%;display:flex;align-items:center;justify-content:center;color:#555;font-size:12px}
    .detail-media{height:155px;background:#07070a;border-bottom:1px solid rgba(255,208,96,.25);display:flex;align-items:center;justify-content:center;overflow:hidden}
    .detail-media img{width:100%;height:100%;object-fit:cover}
    .detail-body{padding:12px}
    .detail-title{font-size:20px;line-height:1.15;font-weight:700;color:#f4f0e8;margin:0 0 4px}
    .detail-category{font-style:italic;color:#cfc4ad;font-size:12px;margin-bottom:14px}
    .detail-desc{color:#eee;font-size:12px;line-height:1.55}
    .detail-desc p{margin:0 0 10px}
    .detail-desc strong{color:#fff}
    .detail-desc a{color:#2fa7ff;text-decoration:none}
    .detail-found{margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,208,96,.25);display:flex;align-items:center;justify-content:center;gap:8px;text-transform:uppercase;font-weight:700;color:#ddd}
    .detail-box{width:20px;height:20px;border:2px solid rgba(255,208,96,.45);display:flex;align-items:center;justify-content:center;color:#60e890}
    .empty{padding:24px;text-align:center;color:#555;font-size:12px}
    .empty.small{padding:18px 8px;font-size:11px}
    .item{display:flex;align-items:center;gap:8px;
      padding:6px 7px;border-radius:5px;cursor:pointer;
      border:1px solid transparent;margin-bottom:2px}
    .item.selected{background:rgba(255,208,96,.12);border-color:rgba(255,208,96,.4)}
    .item:not(.selected):hover{background:rgba(255,255,255,.04)}
    .check{font-size:14px;width:18px;flex-shrink:0;text-align:center}
    .found .check{color:#60e890}
    .notfound .check{color:#444}
    .item-name{flex:1;overflow:hidden;display:flex;flex-direction:column;gap:2px}
    .item-icon-wrap{position:relative;width:30px;height:32px;flex-shrink:0;align-self:center;display:flex;align-items:center;justify-content:center;overflow:visible}
    .item-icon-wrap .icon{transform:scale(1.55);transform-origin:center}
    .item-badge{position:absolute;bottom:2px;right:1px;width:13px;height:13px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:bold;line-height:1;border:1.5px solid #0f0f1a}
    .found .item-badge{background:rgba(96,232,144,.95);color:#0a1a0a}
    .notfound .item-badge{background:rgba(20,20,30,.9);color:#555;border-color:#333}
    .item-title{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .found .item-title{color:#e8e8e8}
    .notfound .item-title{color:#999}
    .item-cat{font-size:10px;color:#4a5568;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .selected .item-cat{color:#718096}
    .item-dist{font-size:10px;color:#555;flex-shrink:0;min-width:26px;text-align:right;align-self:center}
    .selected .item-dist{color:#888}
    .footer{padding:5px 12px;border-top:1px solid rgba(255,255,255,.07);
      flex-shrink:0;font-size:10px;color:#444;display:flex;gap:14px}
    .footer b{color:#666}
  </style>
</head>
<body tabindex="0">
  <div class="wrap">
    <div class="header">
      <div class="header-title">📍 Nearby</div>
      <div class="header-count" id="hcount"></div>
      <button class="header-toggle" id="mapFilterToggle" title="Respect the categories currently visible on the map">Map filters</button>
      <button class="header-toggle" id="stayInListToggle" title="When enabled, focus stays in the current list after marking/unmarking">Stay in list</button>
    </div>
    <div class="content">
      <div class="lists">
        <div class="list-pane" id="notfoundPane">
          <div class="list-head"><span>Not found</span><span class="list-count" id="notfoundCount"></span></div>
          <div class="list" id="notfoundList"></div>
        </div>
        <div class="list-pane" id="foundPane">
          <div class="list-head"><span>Found</span><span class="list-count" id="foundCount"></span></div>
          <div class="list" id="foundList"></div>
        </div>
      </div>
      <div class="details" id="details"></div>
    </div>
    <div class="footer">
      <span style="margin-right: 5px"><b>Left/Right</b> List</span>
      <span style="margin-right: 5px"><b>Up/Down, W/S, D-pad</b> Navigate</span>
      <span style="margin-right: 5px"><b>Enter, Space, A</b> Mark</span>
      <span style="margin-right: 5px"><b>Select/View</b> Filters</span>
      <span><b>Esc, B</b> Close</span>
    </div>
  </div>
  <script>
    // Foco chamado de dentro da própria janela — Qt honra isso
    window.focus();
    document.body.focus();
  </script>
</body>
</html>`);
    doc.close();

    function syncMapFilterToggle() {
      const btn = doc.getElementById('mapFilterToggle');
      if (!btn) return;
      const enabled = _nearbyRespectMapVisibility();
      btn.className = `header-toggle ${enabled ? 'on' : 'off'}`;
      btn.textContent = enabled ? 'Map filters ON' : 'Map filters OFF';
      btn.title = enabled
        ? 'Nearby follows the categories currently visible on the map'
        : 'Nearby shows all categories, ignoring map category visibility';
    }
    function syncStayInListToggle() {
      const btn = doc.getElementById('stayInListToggle');
      if (!btn) return;
      const enabled = _nearbyStayInList();
      btn.className = `header-toggle ${enabled ? 'on' : 'off'}`;
      btn.textContent = enabled ? 'Stay in list ON' : 'Stay in list OFF';
      btn.title = enabled
        ? 'Focus stays in the current list after marking/unmarking'
        : 'Focus follows the item to the other list after marking/unmarking';
    }

    function toggleMapFilterMode() {
      _setNearbyRespectMapVisibility(!_nearbyRespectMapVisibility());
      syncMapFilterToggle();
      refreshNearbyItems();
    }

    function renderLegacySingleList() {
      const list   = doc.getElementById('list');
      const hcount = doc.getElementById('hcount');
      if (!list) return;
      if (items.length === 0) {
        list.innerHTML = '<div class="empty">No location nearby</div>';
        if (hcount) hcount.textContent = '';
        renderDetails(null);
        clearNearbySelection(false);
        return;
      }
      if (hcount) hcount.textContent = `${items.length} location${items.length !== 1 ? 's' : ''}`;
      syncMapFilterToggle();

      // Fingerprint: skip render se ids, found e seleção não mudaram
      const fp = items.map(it => `${it.id}:${it.found}`).join(',') + '|' + selectedIndex;
      if (fp === list._fp) {
        // Só atualiza distâncias (mudam sem alterar a estrutura)
        items.forEach((item, i) => {
          const el = list.querySelector(`.item[data-id="${item.id}"]`);
          if (el) { const d = el.querySelector('.item-dist'); if (d) d.textContent = (item.dist * 1000).toFixed(1); }
        });
        renderDetails(items[selectedIndex]);
        syncSelectedNearby(false);
        return;
      }
      list._fp = fp;

      // Keyed update: atualiza elementos existentes, cria novos, remove obsoletos
      const existing = {};
      list.querySelectorAll('.item[data-id]').forEach(el => { existing[el.dataset.id] = el; });
      const newIds = new Set(items.map(it => it.id));
      Object.keys(existing).forEach(id => { if (!newIds.has(id)) existing[id].remove(); });

      function buildItemEl(item, i) {
        const cls = item.found ? 'found' : 'notfound';
        const sel = i === selectedIndex ? ' selected' : '';
        const cat = item.category;
        const badge = `<span class="item-badge">${item.found ? '✓' : '○'}</span>`;
        const iconName = String(cat?.icon || '').replace(/[^a-z0-9_-]/gi, '');
        const iconHtml = cat?.icon
          ? `<div class="item-icon-wrap"><span class="icon icon-${iconName}"></span>${badge}</div>` : '';
        const catHtml = cat ? `<div class="item-cat">${_escapeHtml(cat.title)}</div>` : '';
        const el = doc.createElement('div');
        el.className = `item ${cls}${sel}`;
        el.dataset.id = item.id;
        el.innerHTML = `
          ${iconHtml || `<div class="check">${item.found ? '✓' : '○'}</div>`}
          <div class="item-name">
            <div class="item-title" title="${_escapeHtml(item.title)}">${_escapeHtml(item.title)}</div>
            ${catHtml}
          </div>
          <div class="item-dist">${(item.dist * 1000).toFixed(1)}</div>`;
        el.addEventListener('click', () => {
          selectNearbyIndex(items.findIndex(it => it.id === item.id), true);
          render();
          doToggle();
        });
        return el;
      }

      items.forEach((item, i) => {
        const cls = item.found ? 'found' : 'notfound';
        const sel = i === selectedIndex ? ' selected' : '';
        let el = existing[item.id];
        if (!el) {
          el = buildItemEl(item, i);
        } else {
          // Atualiza classe e conteúdo dinâmico sem recriar o elemento
          el.className = `item ${cls}${sel}`;
          const badge = el.querySelector('.item-badge');
          if (badge) badge.textContent = item.found ? '✓' : '○';
          const check = el.querySelector('.check');
          if (check) check.textContent = item.found ? '✓' : '○';
          const d = el.querySelector('.item-dist');
          if (d) d.textContent = (item.dist * 1000).toFixed(1);
        }
        list.appendChild(el); // move para posição correta (ordem por distância)
      });

      const selEl = list.querySelector('.selected');
      if (selEl) selEl.scrollIntoView({ block: 'nearest' });
      renderDetails(items[selectedIndex]);
      syncSelectedNearby(false);
    }

    function selectedNearbyItem() {
      return items[selectedIndex] || null;
    }

    function nearbyGroup(found) {
      return items.filter(item => !!item.found === !!found);
    }

    function selectedGroupIndex() {
      const item = selectedNearbyItem();
      if (!item) return -1;
      return nearbyGroup(!!item.found).findIndex(groupItem => groupItem.id === item.id);
    }

    function selectNearbyGroupIndex(found, groupIndex, shouldPan) {
      const group = nearbyGroup(found);
      if (!group.length) return;
      const nextGroupIndex = Math.max(0, Math.min(groupIndex, group.length - 1));
      const nextItem = group[nextGroupIndex];
      const nextIndex = items.findIndex(item => item.id === nextItem.id);
      const changed = nextIndex !== selectedIndex || activeFoundList !== !!found;
      activeFoundList = !!found;
      selectedIndex = nextIndex >= 0 ? nextIndex : selectedIndex;
      if (changed || shouldPan) syncSelectedNearby(shouldPan);
    }

    function ensureNearbySelection() {
      if (!items.length) {
        selectedIndex = 0;
        activeFoundList = false;
        return;
      }
      if (selectedIndex < 0 || selectedIndex >= items.length) selectedIndex = 0;
      const item = selectedNearbyItem();
      if (item) {
        activeFoundList = !!item.found;
        return;
      }
      activeFoundList = nearbyGroup(false).length ? false : true;
      selectNearbyGroupIndex(activeFoundList, 0, false);
    }

    function moveNearbyVertical(delta) {
      if (!items.length) return;
      const current = Math.max(0, selectedGroupIndex());
      selectNearbyGroupIndex(activeFoundList, current + delta, true);
      render();
    }

    function moveNearbyHorizontal(delta) {
      if (!items.length) return;
      const targetFound = delta > 0;
      if (targetFound === activeFoundList) return;
      const targetGroup = nearbyGroup(targetFound);
      if (!targetGroup.length) return;
      const current = Math.max(0, selectedGroupIndex());
      selectNearbyGroupIndex(targetFound, Math.min(current, targetGroup.length - 1), true);
      render();
    }

    function renderList(list, group) {
      if (!list) return;
      if (!group.length) {
        list.innerHTML = '<div class="empty small">No locations</div>';
        return;
      }

      list.querySelectorAll('.empty').forEach(el => el.remove());
      const existing = {};
      list.querySelectorAll('.item[data-id]').forEach(el => { existing[el.dataset.id] = el; });
      const newIds = new Set(group.map(it => it.id));
      Object.keys(existing).forEach(id => { if (!newIds.has(id)) existing[id].remove(); });

      function buildItemEl(item) {
        const el = doc.createElement('div');
        el.dataset.id = item.id;
        el.addEventListener('click', () => {
          const nextIndex = items.findIndex(it => it.id === item.id);
          if (nextIndex >= 0) selectNearbyIndex(nextIndex, true);
          render();
          doToggle();
        });
        return el;
      }

      group.forEach(item => {
        const i = items.findIndex(it => it.id === item.id);
        const cls = item.found ? 'found' : 'notfound';
        const sel = i === selectedIndex ? ' selected' : '';
        const cat = item.category;
        const badge = `<span class="item-badge">${item.found ? '✓' : '○'}</span>`;
        const iconName = String(cat?.icon || '').replace(/[^a-z0-9_-]/gi, '');
        const iconHtml = cat?.icon
          ? `<div class="item-icon-wrap"><span class="icon icon-${iconName}"></span>${badge}</div>` : '';
        const catHtml = cat ? `<div class="item-cat">${_escapeHtml(cat.title)}</div>` : '';
        const el = existing[item.id] || buildItemEl(item);
        el.className = `item ${cls}${sel}`;
        el.innerHTML = `
          ${iconHtml || `<div class="check">${item.found ? '✓' : '○'}</div>`}
          <div class="item-name">
            <div class="item-title" title="${_escapeHtml(item.title)}">${_escapeHtml(item.title)}</div>
            ${catHtml}
          </div>
          <div class="item-dist">${(item.dist * 1000).toFixed(1)}</div>`;
        list.appendChild(el);
      });
    }

    function render() {
      const notfoundList = doc.getElementById('notfoundList');
      const foundList = doc.getElementById('foundList');
      const notfoundPane = doc.getElementById('notfoundPane');
      const foundPane = doc.getElementById('foundPane');
      const notfoundCount = doc.getElementById('notfoundCount');
      const foundCount = doc.getElementById('foundCount');
      const hcount = doc.getElementById('hcount');
      if (!notfoundList || !foundList) return;

      syncMapFilterToggle();
      syncStayInListToggle();
      ensureNearbySelection();
      const notfoundItems = nearbyGroup(false);
      const foundItems = nearbyGroup(true);
      if (hcount) hcount.textContent = `${items.length} location${items.length !== 1 ? 's' : ''}`;
      if (notfoundCount) notfoundCount.textContent = String(notfoundItems.length);
      if (foundCount) foundCount.textContent = String(foundItems.length);
      if (notfoundPane) notfoundPane.classList.toggle('active', !activeFoundList);
      if (foundPane) foundPane.classList.toggle('active', activeFoundList);

      if (items.length === 0) {
        notfoundList.innerHTML = '<div class="empty small">No location nearby</div>';
        foundList.innerHTML = '<div class="empty small">No location nearby</div>';
        if (hcount) hcount.textContent = '';
        renderDetails(null);
        clearNearbySelection(false);
        return;
      }

      renderList(notfoundList, notfoundItems);
      renderList(foundList, foundItems);
      const selEl = (activeFoundList ? foundList : notfoundList).querySelector('.selected');
      if (selEl) selEl.scrollIntoView({ block: 'nearest' });
      renderDetails(selectedNearbyItem());
      syncSelectedNearby(false);
    }

    function syncSelectedNearby(shouldPan) {
      if (!items.length) {
        clearNearbySelection(false);
        return;
      }
      updateNearbySelection(selectedNearbyItem(), shouldPan);
    }

    function selectNearbyIndex(index, shouldPan) {
      if (!items.length) return;
      const nextIndex = Math.max(0, Math.min(index, items.length - 1));
      const changed = nextIndex !== selectedIndex;
      selectedIndex = nextIndex;
      activeFoundList = !!items[selectedIndex]?.found;
      if (changed || shouldPan) syncSelectedNearby(shouldPan);
    }

    function renderDetails(item) {
      const detailEl = doc.getElementById('details');
      if (!detailEl) return;
      if (!item) {
        lastDetailsId = null;
        lastDetailsFound = null;
        detailEl.innerHTML = '<div class="details-empty">Select a nearby location</div>';
        return;
      }
      if (lastDetailsId === item.id && lastDetailsFound === item.found) return;
      lastDetailsId = item.id;
      lastDetailsFound = item.found;
      const location = item.details || _getLocationDetails(item.id) || {};
      const category = location.category || item.category || {};
      const media = Array.isArray(location.media) ? location.media.find(m => m.type === 'image' && m.url) : null;
      const title = location.title || item.title;
      const categoryTitle = category.title || item.category?.title || '';
      const desc = _renderDescription(location.description || '');
      detailEl.innerHTML = `
        ${media ? `<div class="detail-media"><img src="${_escapeHtml(media.url)}" alt=""></div>` : ''}
        <div class="detail-body">
          <h2 class="detail-title">${_escapeHtml(title)}</h2>
          ${categoryTitle ? `<div class="detail-category">${_escapeHtml(categoryTitle)}</div>` : ''}
          <div class="detail-desc">${desc || '<p>No description available.</p>'}</div>
          <div class="detail-found">Found <span class="detail-box">${item.found ? '✓' : ''}</span></div>
        </div>`;
      detailEl.querySelectorAll('[data-location-id]').forEach(link => {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          sendCmd({ cmd: 'pan_location', locationId: link.dataset.locationId });
        });
      });
    }

    function refreshNearbyItems() {
      const selectedId = selectedNearbyItem()?.id || null;
      const previousGroupIndex = Math.max(0, selectedGroupIndex());
      items = getNearbyLocations();
      if (selectedId) {
        const nextIndex = items.findIndex(item => item.id === selectedId);
        if (nextIndex >= 0) {
          selectedIndex = nextIndex;
          activeFoundList = !!items[selectedIndex].found;
        } else if (nearbyGroup(activeFoundList).length) {
          selectNearbyGroupIndex(activeFoundList, previousGroupIndex, false);
        } else {
          activeFoundList = nearbyGroup(false).length ? false : true;
          selectNearbyGroupIndex(activeFoundList, 0, false);
        }
      } else {
        activeFoundList = nearbyGroup(false).length ? false : true;
        selectNearbyGroupIndex(activeFoundList, 0, false);
      }
      render();
    }

    const mapFilterToggle = doc.getElementById('mapFilterToggle');
    if (mapFilterToggle) {
      mapFilterToggle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleMapFilterMode();
      });
      mapFilterToggle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          toggleMapFilterMode();
        }
      });
    }

    const stayInListToggle = doc.getElementById('stayInListToggle');
    if (stayInListToggle) {
      stayInListToggle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        _setNearbyStayInList(!_nearbyStayInList());
        syncStayInListToggle();
      });
      stayInListToggle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          _setNearbyStayInList(!_nearbyStayInList());
          syncStayInListToggle();
        }
      });
    }

    function doToggle() {
      if (!items.length) return;
      const item = items[selectedIndex];
      const originalList = activeFoundList;
      const originalGroupIndex = Math.max(0, selectedGroupIndex());

      item.found = !item.found;
      setUserLocationFound(item.id, item.found);
      if (typeof window.mapManager?.markLocationAsFound === 'function') {
        window.mapManager.markLocationAsFound(parseInt(item.id, 10), item.found);
      }
      items.sort(_sortNearbyItems);

      if (_nearbyStayInList()) {
        const remaining = nearbyGroup(originalList);
        if (remaining.length > 0) {
          const nextGroupIndex = Math.min(originalGroupIndex, remaining.length - 1);
          selectNearbyGroupIndex(originalList, nextGroupIndex, true);
        } else {
          const otherList = !originalList;
          if (nearbyGroup(otherList).length > 0) {
            selectNearbyGroupIndex(otherList, 0, true);
          }
        }
      } else {
        selectedIndex = items.findIndex(nextItem => nextItem.id === item.id);
        activeFoundList = !!item.found;
      }
      render();
    }

    function closeNearbyPopup() {
      const popup = nearbyPopup;
      nearbyPopup = null;
      nearbyInputHandler = null;
      if (popup) popup.close();
      clearNearbySelection(true);
      updateNearbyCircle();
    }

    nearbyInputHandler = function(action) {
      if (action === 'close') {
        closeNearbyPopup();
      } else if (action === 'down') {
        moveNearbyVertical(1);
      } else if (action === 'up') {
        moveNearbyVertical(-1);
      } else if (action === 'left') {
        moveNearbyHorizontal(-1);
      } else if (action === 'right') {
        moveNearbyHorizontal(1);
      } else if (action === 'toggle') {
        doToggle();
      } else if (action === 'filter') {
        toggleMapFilterMode();
      }
    };

    function keyHandler(e) {
      if (e.key === 'Escape') {
        closeNearbyPopup();
        return;
      }
      if (e.key === 'ArrowDown' || e.key.toLowerCase() === 's') {
        e.preventDefault();
        moveNearbyVertical(1);
      } else if (e.key === 'ArrowUp' || e.key.toLowerCase() === 'w') {
        e.preventDefault();
        moveNearbyVertical(-1);
      } else if (e.key === 'ArrowLeft' || e.key.toLowerCase() === 'a') {
        e.preventDefault();
        moveNearbyHorizontal(-1);
      } else if (e.key === 'ArrowRight' || e.key.toLowerCase() === 'd') {
        e.preventDefault();
        moveNearbyHorizontal(1);
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        doToggle();
      }
    }

    // Listener apenas no window do popup — doc.addEventListener dispara em duplicata
    nearbyPopup.addEventListener('keydown', keyHandler);
    const refreshTimer = setInterval(() => {
      if (!isNearbyPopupOpen()) {
        nearbyPopup = null;
        nearbyInputHandler = null;
        clearNearbySelection(true);
        clearInterval(refreshTimer);
        return;
      }
      refreshNearbyItems();
    }, NEARBY_REFRESH_MS);

    render();
    syncMapFilterToggle();
    syncStayInListToggle();
    syncSelectedNearby(true);
    updateNearbyCircle();
    // Delay para Qt processar a criação da janela antes de focar
    setTimeout(() => {
      try {
        if (nearbyPopup && !nearbyPopup.closed) {
          nearbyPopup.resizeTo(860, 460);
          nearbyPopup.focus();
        }
      } catch (_) {}
    }, 150);
  }

