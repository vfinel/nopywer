import sys
# to be able to import qgis, ie, add qgis to PYTHONPATH
sys.path += ['C:/PROGRA~1/QGIS33~1.3/apps/qgis/./python', 'C:/Users/v.finel/AppData/Roaming/QGIS/QGIS3\\profiles\\default/python', 'C:/Users/v.finel/AppData/Roaming/QGIS/QGIS3\\profiles\\default/python/plugins', 'C:/PROGRA~1/QGIS33~1.3/apps/qgis/./python/plugins', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\grass\\grass83\\etc\\python', 'H:\\Mon Drive\\vico\\map\\map2023\\map_20230701_correctionCRS', 'C:\\PROGRA~1\\QGIS33~1.3\\bin\\python39.zip', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\DLLs', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib', 'C:\\PROGRA~1\\QGIS33~1.3\\bin', 'C:\\Users\\v.finel\\AppData\\Roaming\\Python\\Python39\\site-packages', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages\\win32', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages\\win32\\lib', 'C:\\PROGRA~1\\QGIS33~1.3\\apps\\Python39\\lib\\site-packages\\Pythonwin', 'C:/Users/v.finel/AppData/Roaming/QGIS/QGIS3\\profiles\\default/python', 'H:/Mon Drive/vico/map/map2023/map_20230701_correctionCRS'] #from sys.path ran from qgis' python console

import os 
from qgis.core import (QgsApplication,
                       QgsProject, 
                       QgsVectorLayer, 
                       QgsField, 
                       QgsFeature, 
                       QgsGeometry, 
                       QgsPointXY,
                       QgsLineString,
                       edit)

from qgis.utils import iface
from qgis.PyQt.QtCore import QVariant


def draw_point_layer(project: QgsProject):
    # based on https://anitagraser.com/pyqgis-101-introduction-to-qgis-python-programming-for-non-programmers/pyqgis101-creating-editing-a-new-vector-layer/   
    print('running draw_point_layer()...')

    # create a new vector layer 
    vl = QgsVectorLayer("Point", "tdsdsemp", "memory")

    # add some attributes of the fields of the layer 
    pr = vl.dataProvider()
    pr.addAttributes([QgsField("name", QVariant.String),
                    QgsField("age",  QVariant.Int),
                    QgsField("size", QVariant.Double)])
    
    vl.updateFields()

    # add a 'point' feature to the layer
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(-0.13852453255756446, 41.700398388825257)))
    f.setAttributes(["Ada L.", 2, 0.3]) # set its attributes
    pr.addFeature(f)
    vl.updateExtents() 

    # add the layer to the project
    project.addMapLayer(vl)
    
    # print some stats 
    print("\nNo. fields:", len(pr.fields()))
    print("No. features:", pr.featureCount())
    e = vl.extent()
    print("Extent:", e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())
    for f in vl.getFeatures():
        print("Feature:", f.id(), f.attributes(), f.geometry().asPoint())

    # add more attributes
    my_field_name = 'new field'
    my_field_value = 'Hello world!' 

    use_with = 1
    print(f'use_with: {use_with}')
    if not use_with:
        """ using startEditing """
        vl.startEditing() 
        vl.addAttribute(QgsField(my_field_name, QVariant.String))
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
            vl.addAttribute(QgsField(my_field_name, QVariant.String))
            vl.updateFields()
            for f in vl.getFeatures():
                f[my_field_name] = my_field_value
                vl.updateFeature(f)

    # print some stuff
    for f in vl.getFeatures():
        print("Feature:", f.id(), f.attributes(), f.geometry().asPoint())
    
    return None


def draw_cable_layer(project: QgsProject):
    # based on 
    #   https://anitagraser.com/pyqgis-101-introduction-to-qgis-python-programming-for-non-programmers/pyqgis101-creating-editing-a-new-vector-layer/   
    #   https://gis.stackexchange.com/questions/445087/adding-linestring-from-points-using-pyqgis

    # create a new vector layer 
    vl = QgsVectorLayer("linestring", "optim_cable_layer", "memory")

    # add some attributes (=properties of each 'feature' belonging to the layer)
    pr = vl.dataProvider()
    pr.addAttributes([QgsField("name", QVariant.String),
                    QgsField("age",  QVariant.Int),
                    QgsField("size", QVariant.Double)])
    
    vl.updateFields()

    # add a 'line' feature to the layer
    points = [QgsPointXY(-0.13852453255756446, 41.700398388825257), 
              QgsPointXY(-0.13902453255756446, 41.600398388825257)]
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromPolylineXY(points))
    f.setAttributes(["this is my name", 34, 34.3]) # set its attribute
    pr.addFeature(f)
    vl.updateExtents() 

    # add the layer to the project
    project.addMapLayer(vl)

    return None


print(f'hello, my __name__ is {__name__}')


if __name__=='__console__': # ran from pyqgis console 
    project = QgsProject.instance()
    draw_point_layer(project)
    draw_cable_layer(project)


if __name__=='__main__':
    print('running draw_layer as __main__') 
    from get_user_parameters import get_user_parameters
    
    print('initializing QGIS...')
    QgsApplication.setPrefixPath('C:/PROGRA~1/QGIS33~1.3/apps/qgis', True)
    qgs = QgsApplication([], False) # second argument to False disables the GUI.
    qgs.initQgis() # Load providers
    
    print('\nloading project...')
    param = get_user_parameters()
    project = QgsProject.instance() 
    project_file = param['project_file']
    print(f'\nloading project {project_file}...')
    assert os.path.isfile(project_file), f'the project file does not exists: "{project_file}"'
    status = project.read(project_file)
    assert status, f'unable to read project "{project_file}"'

    draw_point_layer(project)
    print('wWARNING: update won''t show when code ran from QGIS')