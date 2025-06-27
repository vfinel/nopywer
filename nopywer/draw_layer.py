import os
from typing import List, Dict
from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    edit,
)

from qgis.utils import iface
from qgis.PyQt.QtCore import QMetaType
from .logger_config import logger


def draw_point_layer(project: QgsProject):
    # based on https://anitagraser.com/pyqgis-101-introduction-to-qgis-python-programming-for-non-programmers/pyqgis101-creating-editing-a-new-vector-layer/
    logger.info("running draw_point_layer()...")

    # create a new vector layer
    vl = QgsVectorLayer("Point", "tdsdsemp", "memory")

    # add some attributes of the fields of the layer
    pr = vl.dataProvider()
    pr.addAttributes(
        [
            QgsField("name", QMetaType.QString),
            QgsField("age", QMetaType.Int),
            QgsField("size", QMetaType.Double),
        ]
    )

    vl.updateFields()

    # add a 'point' feature to the layer
    f = QgsFeature()
    f.setGeometry(
        QgsGeometry.fromPointXY(QgsPointXY(-0.13852453255756446, 41.700398388825257))
    )
    f.setAttributes(["Ada L.", 2, 0.3])  # set its attributes
    pr.addFeature(f)
    vl.updateExtents()

    # add the layer to the project
    project.addMapLayer(vl)

    # log some stats
    logger.info("\nNo. fields:", len(pr.fields()))
    logger.info("No. features:", pr.featureCount())
    e = vl.extent()
    logger.info("Extent:", e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())
    for f in vl.getFeatures():
        logger.info("Feature:", f.id(), f.attributes(), f.geometry().asPoint())

    # add more attributes
    my_field_name = "new field"
    my_field_value = "Hello world!"

    use_with = 1
    logger.info(f"use_with: {use_with}")
    if not use_with:
        """using startEditing"""
        vl.startEditing()
        vl.addAttribute(QgsField(my_field_name, QMetaType.QString))
        vl.updateFields()

        # populate the new attribute field with feature
        for f in vl.getFeatures():
            f[my_field_name] = my_field_value
            vl.updateFeature(f)

        vl.commitChanges()

        # stop the editing session
        iface.vectorLayerTools().stopEditing(vl)

    else:
        "using width edit(vl)"
        with edit(vl):  # replaces startEditing() and (commitChange() or rollBack())
            vl.addAttribute(QgsField(my_field_name, QMetaType.QString))
            vl.updateFields()
            for f in vl.getFeatures():
                f[my_field_name] = my_field_value
                vl.updateFeature(f)

    # print some stuff
    for f in vl.getFeatures():
        logger.info("Feature:", f.id(), f.attributes(), f.geometry().asPoint())

    return None


def draw_cable_layer(project: QgsProject, grid: Dict, optim_edges: List):
    # based on
    #   https://anitagraser.com/pyqgis-101-introduction-to-qgis-python-programming-for-non-programmers/pyqgis101-creating-editing-a-new-vector-layer/
    #   https://gis.stackexchange.com/questions/445087/adding-linestring-from-points-using-pyqgis

    if optim_edges == []:  # demo
        points = [QgsPointXY(738087.4, 4620389.3), QgsPointXY(738136.4, 4620342.7)]

        optim_lines = [{"from": "A", "to": "B", "length": 42, "points": points}]

    else:  # get optimized edges from calling function
        optim_lines = _format_edges(grid, optim_edges)

    # create a new vector layer with current project's crs
    vl = QgsVectorLayer(
        f"linestring?crs={project.crs().authid()}", "optim_cable_layer", "memory"
    )

    # add some attributes (=properties of each 'feature' belonging to the layer)
    pr = vl.dataProvider()
    pr.addAttributes(
        [
            QgsField("from", QMetaType.QString),
            QgsField("to", QMetaType.QString),
            QgsField("length", QMetaType.Double),
        ]
    )

    vl.updateFields()

    # add 'lines' features to the layer
    for line in optim_lines:
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPolylineXY(line["points"]))
        f.setAttributes([line["from"], line["to"], line["length"]])  # set its attribute
        pr.addFeature(f)

    vl.updateExtents()

    # add the layer to the project
    project.addMapLayer(vl)

    return None


def _format_edges(grid: Dict, optim_edges: List):
    optim_lines = []
    for e in optim_edges:
        optim_lines.append(
            {
                "from": e[0],
                "to": e[1],
                "length": e[2],
                "points": [grid[e[0]]["coordinates"], grid[e[1]]["coordinates"]],
            }
        )

    return optim_lines


if __name__ == "__console__":  # ran from pyqgis console
    project = QgsProject.instance()
    draw_point_layer(project)
    grid = {}
    edges = []
    draw_cable_layer(project, grid, edges)


if __name__ == "__main__":
    # WARNING: update won''t show when code ran from QGIS
    logger.info("running draw_layer as __main__")
    from get_user_parameters import get_user_parameters

    logger.info("initializing QGIS...")
    QgsApplication.setPrefixPath("C:/PROGRA~1/QGIS33~1.3/apps/qgis", True)
    qgs = QgsApplication([], False)  # second argument to False disables the GUI.
    qgs.initQgis()  # Load providers

    logger.info("\nloading project...")
    param = get_user_parameters()
    project = QgsProject.instance()
    project_file = param["project_file"]
    logger.info(f"\nloading project {project_file}...")
    assert os.path.isfile(project_file), (
        f'the project file does not exists: "{project_file}"'
    )
    status = project.read(project_file)
    assert status, f'unable to read project "{project_file}"'

    draw_point_layer(project)
    logger.info("WARNING: update wont show when code ran from QGIS")
