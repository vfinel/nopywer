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

    // function setMessage(text, isError) {
    //     messageEl.textContent = text;
    //     messageEl.style.color = isError ? "#fca5a5" : "#cbd5e1";
    // }
    function setMessage(html, isError) {
    messageEl.innerHTML = html;  // ✅ allows <br /> and <code>
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
            const radius = Math.max(4, Math.min(30, 4 + power * 1));
            const markerOptions = {
                radius: generator ? Math.max(radius, 8) : radius,
                weight: generator ? 3 : 2,
                color: "#eecb6b",
                fillColor: generator ? "#f87171" : phaseCol,
                // fillColor: generator ? "#f87171" : "#facc15",
                fillOpacity: 0.95,
                opacity: 1,
            };

            const marker = L.circleMarker(latlng, markerOptions)
                .bindPopup(`
                    <strong>${capitalizeName(name)}</strong><br />
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
        const phase = feature.properties?.phase ?? null;
        const phaseCol = phaseColor(phase);

        if (plugs >= 63) {
            return {color: phaseCol, weight: 10 };
        }
        if (plugs >= 32) {
            return { color: phaseCol, weight: 7 };
        }
        return { color: phaseCol, weight: 3 };
    }
    
    function getCableWeight(plugs) {
        if (plugs >= 63) return 8;
        if (plugs >= 32) return 6;
        return 4;
    }
    // function getCableColor(plugs) {
    // if (plugs >= 63) return "#dc2626";
    // if (plugs >= 32) return "#ea580c";
    // return "#f59e0b";
    // }

    function phaseColor(phase) {
        const p = phase !== null && phase !== "" ? parseInt(phase, 10) : null;
        const colors = { 0: "#000000dc", 1: "#77261c", 2: "#7a7a7a", 3: "#ff00a6" };
        return p !== null && !isNaN(p) ? (colors[p] ?? "#f8f7f7") : "#facc15";
    }

    function renderOptimizedCables(cablesGeojson) {
    console.log(cablesGeojson.features[0].properties);

    optimizedCablesLayer.clearLayers();

    const filter = function (feature) {
        return feature.geometry && feature.geometry.type === "LineString";
    };

    const cableLayer = L.geoJSON(cablesGeojson, {
        filter,
        style: function (feature) {
            const style = cableStyle(feature);
                return {
                    color: style.color,
                    weight: style.weight,
                    opacity: 1,
                };
        },
    onEachFeature: function (feature, layer) {
        const props = feature.properties || {};
        const phaseRaw = props.phase ?? null;
        const phase = phaseRaw !== null && phaseRaw !== "" ? parseInt(phaseRaw, 10) : null;
        const plugs = props.plugs_and_sockets_a ?? 16;

        const vdropStr = props.vdrop_pct !== null && props.vdrop_pct !== undefined
            ? (() => {
                const vdrop = props.vdrop_pct;
                const vdropColor = vdrop > 5 ? "#e74c3c" : vdrop > 3 ? "#f39c12" : "#2ecc71";
                return `<span style="color:${vdropColor}">▼ ${vdrop.toFixed(1)}%</span>`;
            })()
            : "";


        const phaseLabel =
            phase === null || isNaN(phase) ? "?"
            : phase === 3 ? "Triphasic"
            : "L" + (phase + 1);

        layer.bindPopup(
            `<strong>${capitalizeName(props.from || "?")} → ${capitalizeName(props.to || "?")}</strong><br />
            Phase: <strong>${phaseLabel}</strong><br />
            Cable: <strong>${plugs}A</strong><br />
            Length: ${props.length_m ?? "?"} m<br />
            Current: ${props.current_a ?? "?"} A<br />
            Load: ${props.cum_power_kw ?? "?"} kW`
        );
    },
});

cableLayer.addTo(optimizedCablesLayer);
    bringNodesToFront();
}
function updateNodePhasesFromResponse(nodeFeatures) {
    nodesLayer.clearLayers();
    nodeMarkers.length = 0;
    const seen = new Set();

    nodeFeatures.forEach((feature) => {
        if (!feature.geometry || feature.geometry.type !== "Point") return;

        const coords = feature.geometry.coordinates;
        const latlng = [coords[1], coords[0]];

        const name = feature.properties?.name ?? "unnamed";
        if (seen.has(name)) {
                    console.warn("Duplicate node skipped:", name);
                    return;
                }
        seen.add(name);

        const phase = feature.properties?.phase ?? null;
        const power = (feature.properties?.power_watts ?? 0) / 1000;
        const nodeColor = phaseColor(phase);

        const phaseLabel = phase !== null && !isNaN(phase) ? `L${phase + 1}` : "No phase";
        const generator = name.toLowerCase().includes("generator");
        const radius = Math.max(4, Math.min(20, 4 + power));

        const markerOptions = {
            radius: generator ? Math.max(radius, 8) : radius,
            weight: 3,
            color: "#eecb6b",
            fillColor: nodeColor,
            fillOpacity: 0.95,
            opacity: 1,
        };

        const marker = L.circleMarker(latlng, markerOptions)
            .bindPopup(`<strong>${capitalizeName(name)}</strong><br />Power: ${power.toFixed(2)} kW<br />Phase: ${phaseLabel}`)
            .addTo(nodesLayer);

        marker._originalStyle = markerOptions;
        nodeMarkers.push({ name, layer: marker });
    });

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

    async function loadNodes(file = null) {
        if (file) {
            const text = await file.text();
            nodesGeojson = JSON.parse(text);
            setMessage("Loaded custom dataset.", false);
        } else {
            const response = await fetch(DATASET_URL);
            if (!response.ok) {
                throw new Error("Bundled power nodes dataset is unavailable");
            }
            nodesGeojson = await response.json();
            setMessage("Loaded the minimal power-only dataset bundled with nopywer.", false);
        }
        const features = Array.isArray(nodesGeojson.features) ? nodesGeojson.features : [];
        nodeCountEl.textContent = String(features.length);
        addNodes(features);
    }
    const uploadButton = document.getElementById("upload-button");
    const uploadInput = document.getElementById("upload-input");

    uploadButton.addEventListener("click", () => uploadInput.click());

    uploadInput.addEventListener("change", function () {
        const file = this.files?.[0];
        if (!file) return;

        // Reset state before loading new nodes
        optimizedCablesLayer.clearLayers();
        nodesLayer.clearLayers();
        nodeMarkers.length = 0;
        setOptimizerStatus("idle");

        loadNodes(file).catch((error) => {
            nodeCountEl.textContent = "0";
            setOptimizerStatus("error");
            setMessage(escapeHtml(error.message) || "Failed to load file", true);
        });

        this.value = ""; // ✅ allows re-uploading the same file
    });
    async function runOptimization() {
        optimizeButton.disabled = true;
        setOptimizerStatus("running");
        setMessage("Optimizing the current bundled power nodes dataset...", false);
        const hubDiscount = parseFloat(document.getElementById("hub-discount").value);
        const radialityFactor = parseFloat(document.getElementById("radiality-factor").value);

        try {
            const response = await fetch(OPTIMIZE_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    nodes_geojson: buildNodesGeojson(),
                    extra_cable_m: 10,
                    hub_discount: hubDiscount,
                    radiality_factor: radialityFactor,
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
            bringNodesToFront();
            setMessage(
                `Computed and drew ${payload.num_cables} cables for ${Math.round(payload.total_cable_length_m)} m total — ` +
                `Phase loads: L1=${Math.round(payload.phase_loads[0])} kW, ` +
                `L2=${Math.round(payload.phase_loads[1])} kW, ` +
                `L3=${Math.round(payload.phase_loads[2])} kW`,
                false
            );

        }  catch (error) {
            setOptimizerStatus("error");
            const line = error.stack
                ? `<br /><code style="font-size:11px;opacity:0.7">${escapeHtml(error.stack.split("\n")[1]?.trim() ?? "")}</code>`
                : "";
            setMessage((escapeHtml(error.message) || "Optimization failed") + line, true);
        }
 finally {
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
