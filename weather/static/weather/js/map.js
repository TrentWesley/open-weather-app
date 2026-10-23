// FR-12: interactive weather map. The server passes everything in the "map-config"
// json_script: the center, the markers (selected location and favorites, with weather
// already formatted in the user's unit), the base map, and the URL template of our own
// tile proxy. The browser never contacts OpenWeather; overlay tiles come from
// /weather/tiles/... and the server adds the key.
//
// Wrapped in a function so its names don't collide with the other classic scripts,
// which share one global scope.

(() => {
  const SLOW_NOTICE_MS = 300;
  const WORLD_VIEW = { center: [20, 0], zoom: 2 };
  const FIT_PADDING = [32, 32];
  const OVERLAY_OPACITY = 0.7;
  const MESSAGES = {
    mapFailed: "The map couldn't load. The places it would show are listed below.",
    baseFailed: "Some of the background map couldn't load. Weather layers and markers still work.",
    overlayFailed: (label) => `The ${label.toLowerCase()} layer is unavailable right now. The base map still works.`,
    layerShown: (label) => `${label} layer shown on the map.`,
    noWeather: "Current weather unavailable",
  };

  // ---- Pure helpers (no DOM access) ----

  function overlayUrl(template, layer) {
    return template.replace("{layer}", encodeURIComponent(layer));
  }

  // Center on the selected location, else fit the favorites, else show the world.
  function initialView(config) {
    if (config.center) {
      return { center: config.center, zoom: config.zoom };
    }
    if (config.markers.length) {
      return { bounds: config.markers.map((marker) => [marker.lat, marker.lon]), zoom: config.zoom };
    }
    return WORLD_VIEW;
  }

  function markerLabel(marker) {
    const role = marker.kind === "selected" ? "selected location" : "favorite";
    return `${marker.name} (${role}): ${marker.weather || MESSAGES.noWeather}`;
  }

  function prefersReducedMotion(win) {
    return Boolean(win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // ---- DOM wiring ----

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  // FR-12 AC-5: name, current temperature and a link to the dashboard.
  function popupContent(marker) {
    const box = element("div", "map-popup");
    box.append(element("strong", "", marker.name));
    box.append(element("p", "", marker.weather || MESSAGES.noWeather));
    const link = element("a", "", "Open the forecast");
    link.href = marker.url;
    box.append(link);
    return box;
  }

  function announce(message) {
    const region = document.getElementById("live-region");
    if (region) {
      region.textContent = message;
    }
  }

  function addMarkers(map, markers) {
    // Favorites get a star so they differ from the selected location by shape, not colour.
    const favoriteIcon = L.divIcon({
      className: "map-marker-favorite",
      html: "",
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14],
    });
    markers.forEach((marker) => {
      const options = { title: marker.name, alt: markerLabel(marker), keyboard: true };
      if (marker.kind === "favorite") {
        options.icon = favoriteIcon;
      }
      const layer = L.marker([marker.lat, marker.lon], options)
        .bindPopup(popupContent(marker))
        .addTo(map);
      const node = layer.getElement();
      if (node) {
        node.setAttribute("aria-label", markerLabel(marker));
      }
    });
  }

  function setUpLayers(map, config, controls, status) {
    const radios = controls.querySelectorAll('input[name="map-layer"]');
    const legends = controls.querySelectorAll("[data-legend]");
    let overlay = null;

    function labelFor(slug) {
      const radio = controls.querySelector(`#map-layer-${slug}`);
      const label = radio && controls.querySelector(`label[for="${radio.id}"]`);
      return label ? label.textContent.trim() : slug;
    }

    function show(slug, announceChange) {
      if (overlay) {
        map.removeLayer(overlay);
      }
      status.textContent = "";
      const label = labelFor(slug);
      let reported = false;
      overlay = L.tileLayer(overlayUrl(config.tileUrl, slug), {
        opacity: OVERLAY_OPACITY,
        maxZoom: config.base.maxZoom,
      });
      // FR-12 AC-7: the base map keeps working; say the overlay is unavailable.
      overlay.on("tileerror", () => {
        if (!reported) {
          reported = true;
          status.textContent = MESSAGES.overlayFailed(label);
        }
      });
      overlay.addTo(map);
      legends.forEach((legend) => {
        legend.hidden = legend.dataset.legend !== slug;
      });
      if (announceChange) {
        announce(MESSAGES.layerShown(label));
      }
    }

    radios.forEach((radio) => {
      radio.addEventListener("change", () => {
        if (radio.checked) {
          show(radio.value, true);
        }
      });
    });
    const checked = controls.querySelector('input[name="map-layer"]:checked');
    show(checked ? checked.value : config.defaultLayer, false);
  }

  function setUpMap() {
    const container = document.querySelector("[data-map]");
    const configElement = document.getElementById("map-config");
    if (!container || !configElement) {
      return;
    }
    const fallback = document.querySelector("[data-map-fallback]");
    if (typeof L === "undefined") {
      // NFR-FT-6: Leaflet didn't load; keep a visible notice and the text alternative.
      if (fallback) {
        fallback.textContent = MESSAGES.mapFailed;
      }
      return;
    }
    const config = JSON.parse(configElement.textContent);
    const controls = document.querySelector("[data-map-controls]");
    const status = document.querySelector("[data-map-status]");
    const loading = document.querySelector("[data-map-loading]");

    // NFR-USE-4: only show "Loading map…" if the first tiles take over 300 ms.
    let loaded = false;
    const slowNotice = setTimeout(() => {
      if (!loaded && loading) {
        loading.hidden = false;
      }
    }, SLOW_NOTICE_MS);
    function finishLoading() {
      loaded = true;
      clearTimeout(slowNotice);
      if (loading) {
        loading.hidden = true;
      }
    }

    // Leaflet needs a visible, sized container; it stays hidden until now so there is
    // no empty, focusable box without JavaScript or Leaflet.
    container.hidden = false;
    const help = document.getElementById("map-keyboard-help");
    if (help) {
      help.hidden = false;
    }

    const reduced = prefersReducedMotion(window);
    const map = L.map(container, {
      keyboard: true,
      zoomAnimation: !reduced,
      fadeAnimation: !reduced,
      markerZoomAnimation: !reduced,
      inertia: !reduced,
    });
    if (reduced) {
      // Leaflet animates keyboard and programmatic panning regardless of the
      // options above; jump instead (NFR-AC-10).
      const panBy = map.panBy.bind(map);
      map.panBy = (offset, options) => panBy(offset, { ...options, animate: false });
    }

    // The tile server needs a Referer (OpenStreetMap blocks tiles without one), but the
    // page's Referrer-Policy sends none cross-origin; this layer sends the origin only.
    const base = L.tileLayer(config.base.url, {
      maxZoom: config.base.maxZoom,
      attribution: config.base.attribution,
      referrerPolicy: config.base.referrerPolicy,
    });
    let baseReported = false;
    base.on("load", finishLoading);
    base.on("tileerror", () => {
      finishLoading();
      if (!baseReported && status && !status.textContent) {
        baseReported = true;
        status.textContent = MESSAGES.baseFailed;
      }
    });
    base.addTo(map);

    const view = initialView(config);
    if (view.bounds) {
      map.fitBounds(view.bounds, { padding: FIT_PADDING, maxZoom: view.zoom });
    } else {
      map.setView(view.center, view.zoom);
    }

    addMarkers(map, config.markers);
    // Leaflet only closes popups on Escape while the map itself has focus; also do it
    // when a marker has focus, so a popup opened with Enter can be dismissed.
    container.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        map.closePopup();
      }
    });
    if (controls && status) {
      setUpLayers(map, config, controls, status);
      controls.hidden = false;
    }
    if (fallback) {
      fallback.hidden = true;
    }
  }

  setUpMap();
})();
