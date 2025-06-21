from main import main
from qgis.core import QgsApplication, QgsProject, QgsFeatureRequest
import nopywer as npw

if (__name__ == "__main__") or (QgsApplication.instance() is not None):
    grid, qgs_project, qgs, running_in_qgis = main()

    # tests on 2024 map
    assert len(grid["barrio del sol"].power) == 3, (
        "power should be of len 3, one for each phase"
    )

    assert grid["barrio del sol"].power[0] == 3680, (
        "barrio del sol should have power on phase 0 for tests"
    )

    assert sum(grid["rosace"].power) == 3680, (
        "rosace power should be egal to its own power only"
    )

    assert sum(grid["rosace"].cum_power) == 2 * 3680, (
        "rosace power is barrio del sol + rosace"
    )

    """ check that power and cum_power values are successfully updated on AGIS data"""
    # layer = npw.get_layer(qgs_project, "norg_nodes_2024")
    # mapLayersByName ? mapByLayersName ?
    layer = qgs_project.mapLayersByName("norg_nodes_2024")[0]

    # request = QgsFeatureRequest().setFilter("rosace")
    # features = layer.getFeatures(request)
    # feature = features[0]
    features = [feature for feature in layer.getFeatures()]
    # features[0].attribute('name')
    feature_test = [
        feature for feature in features if feature.attribute("name") == "Rosace"
    ]
    feature_test[0].attribute("cumPower")

    assert sum(grid["rosace"].cum_power) == 1e3 * feature_test[0].attribute(
        "cumPower"
    ), "value has not been correctly updated on the map"

    assert sum(grid["rosace"].power) == 1e3 * feature_test[0].attribute("power"), (
        "value has not been correctly updated on the map"
    )
    # load  = get feature ('rosace')
    # load.attribute("name")

    print("all tests are successfull :)")

    qgs.exitQgis()
