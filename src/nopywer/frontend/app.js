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

    let nodesGeojson = null;
    let defaultBounds = null;

    function setMessage(text, isError) {
        messageEl.textContent = text;
        messageEl.style.color = isError ? "#fca5a5" : "#cbd5e1";
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

            L.circleMarker(latlng, {
                radius: generator ? 8 : 6,
                weight: generator ? 3 : 2,
                color: generator ? "#ef4444" : "#a16207",
                fillColor: generator ? "#f87171" : "#facc15",
                fillOpacity: 0.95,
            })
                .bindPopup(
                    "<strong>" +
                        name +
                        "</strong><br />" +
                        "Power: " +
                        power.toFixed(2) +
                        " kW",
                )
                .addTo(nodesLayer);

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
            return { color: "#dc2626", weight: 6 };
        }
        if (plugs >= 32) {
            return { color: "#ea580c", weight: 5 };
        }
        return { color: "#f59e0b", weight: 4 };
    }

    function renderOptimizedCables(cablesGeojson) {
        optimizedCablesLayer.clearLayers();

        const cableLayer = L.geoJSON(cablesGeojson, {
            filter: function (feature) {
                return feature.geometry && feature.geometry.type === "LineString";
            },
            style: function (feature) {
                const style = cableStyle(feature);
                return {
                    color: style.color,
                    weight: style.weight,
                    opacity: 0.95,
                };
            },
            onEachFeature: function (feature, layer) {
                const props = feature.properties || {};
                const details =
                    "<strong>" +
                    (props.from || "?") +
                    " → " +
                    (props.to || "?") +
                    "</strong><br />" +
                    "Length: " +
                    String(props.length_m ?? "?") +
                    " m<br />" +
                    "Cable: " +
                    String(props.cable_type || "?") +
                    "<br />" +
                    "Current: " +
                    String(props.current_a ?? "?") +
                    " A<br />" +
                    "Load: " +
                    String(props.cum_power_kw ?? "?") +
                    " kW";

                layer.bindPopup(details);
                layer.bindTooltip(details, {
                    sticky: true,
                    direction: "top",
                    className: "cable-tooltip",
                });
            },
        });

        cableLayer.addTo(optimizedCablesLayer);
        if (cableLayer.getLayers().length > 0) {
            map.fitBounds(cableLayer.getBounds().pad(0.08));
        }
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
            setOptimizerStatus("done");
            setMessage(
                "Computed and drew " +
                    payload.num_cables +
                    " cables for " +
                    Math.round(payload.total_cable_length_m) +
                    " m total.",
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
