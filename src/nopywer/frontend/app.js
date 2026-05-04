"use strict";

(function () {
    const DATASET_URL = "./data/power-nodes.geojson";
    const OPTIMIZE_URL = "/api/v1/optimize";

    const nodeCountEl = document.getElementById("node-count");
    const optimizerStatusEl = document.getElementById("optimizer-status");
    const messageEl = document.getElementById("message");
    const optimizeButton = document.getElementById("optimize-button");
    const resetButton = document.getElementById("reset-button");

    const map = L.map("map", {
        zoomControl: true,
        attributionControl: true,
    });

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 20,
        attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    const nodesLayer = L.layerGroup().addTo(map);
    const optimizedCablesLayer = L.layerGroup().addTo(map);

    const nodeMarkers = [];
    let highlightedMarkers = [];

    let nodesGeojson = null;
    let defaultBounds = null;

    function setMessage(text, isError) {
        messageEl.textContent = text;
        messageEl.style.color = isError ? "#fca5a5" : "#cbd5e1";
    }
    function capitalizeName(name) {
    return name.replace(/\b\w/g, c => c.toUpperCase());
    }
    
    function setOptimizerStatus(text) {
        optimizerStatusEl.textContent = text;
    }

    function bringNodesToFront() {
        nodesLayer.eachLayer(function (layer) {
            if (typeof layer.bringToFront === "function") {
                layer.bringToFront();
            }
        });
    }

    function clearNodeHighlight() {
        highlightedMarkers.forEach((marker) => {
            if (marker._originalStyle) {
                marker.setStyle(marker._originalStyle);
            }
        });
        highlightedMarkers = [];
    }

    function highlightNodeMarkers(markers) {
        clearNodeHighlight();
        if (!markers.length) {
            return;
        }

        const bounds = L.latLngBounds(markers.map((marker) => marker.getLatLng()));
        markers.forEach((marker) => {
            marker.setStyle({
                radius: Math.max(marker.options.radius, marker.options.radius * 1.5),
                weight: Math.max(marker.options.weight, 4),
                color: "#2563eb",
                fillColor: "#60a5fa",
                fillOpacity: 1,
                opacity: 1,
            });
            highlightedMarkers.push(marker);
        });

        map.fitBounds(bounds.pad(0.15));
        markers[0].openPopup();
    }

    function searchNodeByName() {
        const input = document.getElementById("node-search-input");
        if (!input) {
            return;
        }

        const query = input.value.trim().toLowerCase();
        clearNodeHighlight();

        if (!query) {
            setMessage("Enter a node name to find it on the map.", false);
            return;
        }

        const matches = nodeMarkers
            .filter((entry) => entry.name.toLowerCase().includes(query))
            .map((entry) => entry.layer);

        if (!matches.length) {
            setMessage('No nodes found matching "' + input.value + '".', true);
            return;
        }

        setMessage('Found ' + matches.length + ' node' + (matches.length === 1 ? '' : 's') + '.', false);
        highlightNodeMarkers(matches);
    }

    const SearchControl = L.Control.extend({
        onAdd: function () {
            const container = L.DomUtil.create("div", "leaflet-bar leaflet-control leaflet-control-custom");
            container.style.background = "#ffffffee";
            container.style.padding = "6px 8px";
            container.style.borderRadius = "4px";
            container.style.boxShadow = "0 1px 4px rgba(0,0,0,0.3)";
            container.style.minWidth = "220px";
            container.style.fontFamily = "sans-serif";
            container.style.fontSize = "13px";

            const input = L.DomUtil.create("input", "", container);
            input.type = "search";
            input.placeholder = "Search node name...";
            input.style.width = "100%";
            input.style.marginBottom = "5px";
            input.style.padding = "4px 6px";
            input.style.border = "1px solid #ccc";
            input.style.borderRadius = "3px";
            input.id = "node-search-input";

            const button = L.DomUtil.create("button", "", container);
            button.type = "button";
            button.textContent = "Find";
            button.style.width = "100%";
            button.style.padding = "4px 6px";
            button.style.border = "1px solid #666";
            button.style.borderRadius = "3px";
            button.style.background = "#374151";
            button.style.color = "#f8fafc";
            button.style.cursor = "pointer";
            button.id = "node-search-button";

            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.on(button, "click", searchNodeByName);
            L.DomEvent.on(input, "keydown", function (evt) {
                if (evt.key === "Enter") {
                    evt.preventDefault();
                    searchNodeByName();
                }
            });

            return container;
        },
    });

    map.addControl(new SearchControl({ position: "topright" }));

    function isGenerator(feature) {
        const name = String(feature.properties && feature.properties.name ? feature.properties.name : "");
        return name.toLowerCase().includes("generator");
    }

    function addNodes(features) {
        const bounds = [];

        features.forEach((feature) => {
            if (!feature.geometry || feature.geometry.type !== "Point") {
                return;
            }

            const coordinates = feature.geometry.coordinates || [];
            if (coordinates.length < 2) {
                return;
            }

            const latlng = [coordinates[1], coordinates[0]];
            const generator = isGenerator(feature);
            const name = feature.properties && feature.properties.name ? feature.properties.name : "unnamed";
            const power = feature.properties && typeof feature.properties.power === "number"
            ? feature.properties.power / 1000
            : 0;

            const phaseRaw = feature.properties?.phase;
            const phase = phaseRaw != null && phaseRaw !== "" 
                ? parseInt(phaseRaw, 10) 
                : null;

            const phaseLabel = phase !== null && !isNaN(phase) ? `L${phase + 1}` : "No phase assigned";
            const phaseCol = phaseColor(phase);
            // Scale radius proportionally to power (min 4, max 20)
            const radius = Math.max(4, Math.min(20, 4 + power * 1));
            const markerOptions = {
                radius: generator ? Math.max(radius, 8) : radius,
                weight: generator ? 3 : 2,
                color: generator ? "#ef4444" : "#a16207",
                fillColor: generator ? "#f87171" : phaseCol,
                // fillColor: generator ? "#f87171" : "#facc15",
                fillOpacity: 0.95,
                opacity: 1,
            };

            const marker = L.circleMarker(latlng, markerOptions)
                .bindPopup(`
                    <strong>${name}</strong><br />
                    Power: ${power.toFixed(2)} kW<br />
                    Phase: ${phaseLabel}
                `)
                .addTo(nodesLayer);
            marker._originalStyle = markerOptions;
            marker._nodeName = name;
            nodeMarkers.push({ name, layer: marker });

            bounds.push(latlng);
        });

        if (bounds.length > 0) {
            defaultBounds = L.latLngBounds(bounds);
            map.fitBounds(defaultBounds.pad(0.12));
        } else {
            map.setView([41.7008, -0.1379], 17);
        }
    }


    function cableStyle(feature) {
        const plugs = feature.properties && feature.properties.plugs_and_sockets_a
            ? feature.properties.plugs_and_sockets_a
            : 16;

        if (plugs >= 63) {
            return { color: "#dc2626", weight: 10 };
        }
        if (plugs >= 32) {
            return { color: "#ea580c", weight: 7 };
        }
        return { color: "#f59e0b", weight: 3 };
    }
    function getCableWeight(plugs) {
        if (plugs >= 63) return 8;
        if (plugs >= 32) return 6;
        return 4;
    }
    function getCableColor(plugs) {
    if (plugs >= 63) return "#dc2626";
    if (plugs >= 32) return "#ea580c";
    return "#f59e0b";
    }

    function phaseColor(phase) {
        const p = phase !== null && phase !== "" ? parseInt(phase, 10) : null;
        const colors = { 0: "#000000dc", 1: "#77261c", 2: "#7a7a7a", 3: "#ff00a6" };
        return p !== null && !isNaN(p) ? (colors[p] ?? "#f8f7f7") : "#facc15";
    }

    function renderOptimizedCables(cablesGeojson) {
    console.log(cablesGeojson.features[0].properties);

    optimizedCablesLayer.clearLayers();

    const nodeFeatures = cablesGeojson.features.filter(f => f.geometry.type === "Point");
    console.log("Node features:", nodeFeatures.length, nodeFeatures[0]?.properties);


    const filter = function (feature) {
        return feature.geometry && feature.geometry.type === "LineString";
    };

    // Capa base: tipo de cable (gruesa, semitransparente)
    const baseLayer = L.geoJSON(cablesGeojson, {
        filter,
        style: function (feature) {
            const style = cableStyle(feature);
            return {
                color: style.color,
                weight: style.weight * 2,
                opacity: 0.5,
            };
        },
    });

    // Capa superior: fase (fina, sólida) + popups
    const phaseLayer = L.geoJSON(cablesGeojson, {
        filter,
        style: function (feature) {
            const plugs = feature.properties?.plugs_and_sockets_a ?? 16;
            const phase = feature.properties?.phase ?? null;
            const baseWeight = cableStyle(feature).weight;
            return {
                color: phaseColor(phase),
                weight: baseWeight,
                opacity: 1,
            };
        },
        onEachFeature: function (feature, layer) {
            const props = feature.properties || {};
            const phaseRaw = props.phase ?? null;
            const phase = phaseRaw !== null && phaseRaw !== "" ? parseInt(phaseRaw, 10) : null;

            const plugs = props.plugs_and_sockets_a ?? 16;

            const phaseLabel =
                phase === null || isNaN(phase)
                    ? "?"
                    : phase === 3
                    ? "Triphasic"
                    : "L" + (phase + 1);

            const details =
                "<strong>" + (props.from || "?") + " → " + (props.to || "?") + "</strong><br />" +
                "Phase: <span style='color:" + phaseColor(phase) + "'><strong>" + phaseLabel + "</strong></span><br />" +
                "Cable: <span style='color:" + cableStyle(feature).color + "'><strong>" + plugs + "A</strong></span><br />" +
                "Length: " + String(props.length_m ?? "?") + " m<br />" +
                "Current: " + String(props.current_a ?? "?") + " A<br />" +
                "Load: " + String(props.cum_power_kw ?? "?") + " kW";

            layer.bindPopup(details);
        },
    });

    baseLayer.addTo(optimizedCablesLayer);
    phaseLayer.addTo(optimizedCablesLayer);

    if (phaseLayer.getLayers().length > 0) {
        map.fitBounds(phaseLayer.getBounds().pad(0.08));
    }
    bringNodesToFront();
}
function updateNodePhasesFromResponse(nodeFeatures) {
    nodesLayer.clearLayers();      // ✅ wipe original markers
    nodeMarkers.length = 0;        // ✅ clear the reference array

    nodeFeatures.forEach((feature) => {
        if (!feature.geometry || feature.geometry.type !== "Point") return;

        const coords = feature.geometry.coordinates;
        const latlng = [coords[1], coords[0]];
        const name = feature.properties?.name ?? "unnamed";
        const phase = feature.properties?.phase ?? null;
        const power = (feature.properties?.power_watts ?? 0) / 1000;
        const phaseLabel = phase !== null && !isNaN(phase) ? `L${phase + 1}` : "?";

        const generator = name.toLowerCase().includes("generator");
        const radius = Math.max(4, Math.min(20, 4 + power));
        const markerOptions = {
            radius: generator ? Math.max(radius, 8) : radius,
            weight: generator ? 3 : 2,
            color: generator ? "#ef4444" : "#a16207",
            fillColor: generator ? "#f87171" : "#facc15",
            fillOpacity: 0.95,
            opacity: 1,
        };

        const marker = L.circleMarker(latlng, markerOptions)
            .bindPopup(`
                <strong>${name}</strong><br />
                Power: ${power.toFixed(2)} kW<br />
                Phase: ${phaseLabel}
            `)
            .addTo(nodesLayer);

        marker._originalStyle = markerOptions;
        nodeMarkers.push({ name, layer: marker });
    });

    bringNodesToFront();
}

    function buildNodesGeojson() {
        if (!nodesGeojson || !Array.isArray(nodesGeojson.features)) {
            return { type: "FeatureCollection", features: [] };
        }

        return {
            type: "FeatureCollection",
            features: nodesGeojson.features.map((feature) => ({
                type: "Feature",
                geometry: feature.geometry,
                properties: {
                    name: feature.properties.name,
                    power: feature.properties.power,
                    phase: feature.properties.phase ?? null,
                },
            })),
        };
    }

    async function loadNodes() {
        const response = await fetch(DATASET_URL);
        if (!response.ok) {
            throw new Error("Bundled power nodes dataset is unavailable");
        }

        nodesGeojson = await response.json();
        const features = Array.isArray(nodesGeojson.features) ? nodesGeojson.features : [];
        nodeCountEl.textContent = String(features.length);
        addNodes(features);
        setMessage("Loaded the minimal power-only dataset bundled with nopywer.", false);
    }

    async function runOptimization() {
        optimizeButton.disabled = true;
        setOptimizerStatus("running");
        setMessage("Optimizing the current bundled power nodes dataset...", false);

        try {
            const response = await fetch(OPTIMIZE_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    nodes_geojson: buildNodesGeojson(),
                    extra_cable_m: 10,
                }),
            });

            const payload = await response.json();
            if (!response.ok) {
                throw new Error(payload.detail || "Optimization failed");
            }

            renderOptimizedCables(payload.cables_geojson);
            updateNodePhasesFromResponse(
            payload.cables_geojson.features.filter(f => f.geometry.type === "Point"));

            setOptimizerStatus("done");
            setMessage(
                "Computed and drew " +
                    payload.num_cables +
                    " cables for " +
                    Math.round(payload.total_cable_length_m) +
                    " m total" +
                    " Phase loads: L1=" +
                          Math.round(payload.phase_loads[0]) +
                          " kW, L2=" +
                          Math.round(payload.phase_loads[1]) +
                          " kW, L3=" +  
                          Math.round(payload.phase_loads[2]),
                "\n" +
                    "Phase loads: L1=" +
                    Math.round(payload.phase_loads[0]) +
                    " kW, L2=" +
                    Math.round(payload.phase_loads[1]) +
                    " kW, L3=" +
                    Math.round(payload.phase_loads[2]),
                false,
            );
        } catch (error) {
            setOptimizerStatus("error");
            setMessage(error.message || "Optimization failed", true);
        } finally {
            optimizeButton.disabled = false;
        }
    }

    optimizeButton.addEventListener("click", runOptimization);
    resetButton.addEventListener("click", function () {
        optimizedCablesLayer.clearLayers();
        setOptimizerStatus("idle");
        setMessage("Reset to the bundled power nodes view.", false);
        if (defaultBounds) {
            map.fitBounds(defaultBounds.pad(0.12));
            bringNodesToFront();
            return;
        }
        map.setView([41.7008, -0.1379], 17);
        bringNodesToFront();
    });

    loadNodes().catch((error) => {
        nodeCountEl.textContent = "0";
        setOptimizerStatus("error");
        setMessage(error.message || "Failed to load bundled power nodes", true);
        map.setView([41.7008, -0.1379], 17);
    });
})();
