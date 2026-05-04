  // ── WebSocket ─────────────────────────────────────────────────────
  function handlePositionMessage(msg) {
    if (isSamePositionMessage(msg, lastPos)) return;
    updateHeading(msg);
    lastPos = msg;
    if (marker) marker.setLngLat([msg.lng, msg.lat]);
    updateNearbyCircle();
    const mm = window.mapManager && window.mapManager.map;
    if (rotateWithCamera) {
      // camera_heading controla bearing e centro nesse modo.
    } else if (following && !shiftHeld && !nearbySelectionActive && rotateWithPlayer && mm) {
      liveEaseTo(mm, { center: [msg.lng, msg.lat], bearing: lastHeading });
    } else if (following && !shiftHeld && !nearbySelectionActive) {
      pan(msg.lng, msg.lat);
    }
    updatePanel();
  }

  function handleMapMarkerMessage(msg) {
    mapDestLng = msg.lng;
    mapDestLat = msg.lat;
    if (!mapMarker) createMapMarker();
    ensureEdgeIndicator();
    installEdgeIndicatorListener();
    if (mapMarker) {
      mapMarker.setLngLat([msg.lng, msg.lat]);
      mapMarker.getElement().style.display = '';
    }
    updateEdgeIndicator();
  }

  function handleMapMarkerCleared() {
    mapDestLng = null;
    mapDestLat = null;
    if (mapMarker) mapMarker.getElement().style.display = 'none';
    const ei = document.getElementById('cdEdgeIndicator');
    if (ei) ei.style.display = 'none';
  }

  function processRealtimeEvents(events) {
    if (!Array.isArray(events)) return;
    events.forEach(function(ev) {
      if (ev.type === 'position') {
        handlePositionMessage(ev);
      } else if (ev.type === 'camera_heading') {
        onCameraHeading(ev);
      } else if (ev.type === 'map_marker') {
        handleMapMarkerMessage(ev);
      } else if (ev.type === 'map_marker_cleared') {
        handleMapMarkerCleared();
      }
    });
  }

  function connect() {
    if (ws && (ws.readyState === 0 || ws.readyState === 1)) return;
    ws = new WebSocket(WS_URL);
    ws.onopen  = () => {
      sendCmd({
        cmd: 'client_options',
        clientName: 'overlay',
        realtimeBundle: true,
        nativeRealtime: NATIVE_REALTIME
      });
      updatePanel();
    };
    ws.onclose = () => { updatePanel(); setTimeout(connect, RECONNECT_MS); };
    ws.onerror = () => updatePanel();
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);

        if (msg.type === 'realtime' && Array.isArray(msg.events)) {
          processRealtimeEvents(msg.events);

        } else if (msg.type === 'position') {
          handlePositionMessage(msg);

        } else if (msg.type === 'camera_heading') {
          onCameraHeading(msg);

        } else if (msg.type === 'waypoints') {
          waypoints = msg.data || [];
          renderWaypoints();

        } else if (msg.type === 'teleport_marker_result') {
          if (msg.ok) {
            hasPreTeleport = true; updatePanel();
          } else {
            setStatus(msg.err || 'No map marker set', '#e07070', 3000);
          }

        } else if (msg.type === 'teleport_map_result') {
          if (msg.ok) {
            hasPreTeleport = true; updatePanel();
          } else {
            hasPreTeleport = false; updatePanel();
            setStatus(msg.err || 'Map teleport failed', '#e07070', 3000);
          }

        } else if (msg.type === 'location_toggle') {
          if (msg.sourceClientId && msg.sourceClientId === CLIENT_ID) return;
          _onLocationToggle(msg.locationId, msg.found);

        } else if (msg.type === 'open_nearby') {
          if (nearbyControlsEnabled()) openNearbyPopup();

        } else if (msg.type === 'nearby_input') {
          if (nearbyControlsEnabled() && nearbyInputHandler) nearbyInputHandler(msg.action);

        } else if (msg.type === 'pan_location') {
          panToLocationId(msg.locationId);

        } else if (msg.type === 'map_marker') {
          handleMapMarkerMessage(msg);

        } else if (msg.type === 'map_marker_cleared') {
          handleMapMarkerCleared();
        }

        // backward-compat: mensagens sem type são posição
        if (!msg.type && typeof msg.lng === 'number') {
          handlePositionMessage(msg);
        }
      } catch (_) {}
    };
  }

  window.__cdNativeRealtime = function(frame) {
    if (!frame || !Array.isArray(frame.events)) return;
    processRealtimeEvents(frame.events);
  };

