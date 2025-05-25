import numpy as np
from qgis.core import QgsPointXY


class Cable:
    # TODO:
    #   - check attributes values (with properties setter) for each attribute
    #   - add helpers strings

    # ensure that no attribues can de added without being declared here
    __slots__ = (
        "_length",
        "_area",
        "_plugs_and_sockets",
        "_r",
        "_phase",
        "_nodes",
        "_current",
        "_vdrop_volts",
        "_coordinates",
        "_layer_name",
        "_id",
    )

    rho = 1 / 26  # resistivity of copper cables in [ohm/m*mm²] R = rho*L/area

    def __init__(self, length: float, area: float, plugs_and_sockets: str):
        self.length = length
        self.area = area
        self.plugs_and_sockets = plugs_and_sockets
        self.nodes = []
        self.current = []

    @property
    def length(self):
        """This is the documentation for the length property.
        Note that length should be a float() and in meters.
        """
        return self._length

    @length.setter
    def length(self, value):
        assert isinstance(value, float), (
            f"cable length should be a float but is a {type(value)}"
        )
        assert value > 0, f"cable length is equal to 0m. This cable cannot be created."
        self._length = value

    @property
    def area(self):
        """area of the cable, in squared millimeters"""
        return self._area

    @area.setter
    def area(self, value):
        assert isinstance(value, float), (
            f"cable area should be a float but is {value} (which is a {type(value)})"
        )
        self._area = value

    @property
    def plugs_and_sockets(self):
        """rating of plugs and sockets of the cable, in amps"""
        return self._plugs_and_sockets

    @plugs_and_sockets.setter
    def plugs_and_sockets(self, value):
        assert isinstance(value, (float, int)), (
            f"cable plugs_and_sockets should be a float or int but is {value} (which is a {type(value)})"
        )
        self._plugs_and_sockets = value

    @property
    def nodes(self):
        """list of nodes that are connected by this cable."""
        return self._nodes

    @nodes.setter
    def nodes(self, value):
        assert isinstance(value, list), (
            f"cable nodes should be a list but is {value} (which is a {type(value)})"
        )
        self._nodes = value

    @property
    def phase(self):
        """Phase flowing through this cable. Can be 'T' for triphase, or an int for single phases."""
        return self._phase

    @phase.setter
    def phase(self, value):
        assert isinstance(
            value,
            (
                type(None),  # for init
                int,  # if connected to only 1-phase
                str,  # if connected to another grid
                list,  # if connected to multiple phases
            ),
        ), (
            f"phase should be a (int, str, list, or None) but is {value} which is a {type(value)}"
        )
        self._phase = value

    @property
    def current(self):
        """current flowing through this cable, in each phase, in amps"""
        return self._current

    @current.setter
    def current(self, value):
        assert isinstance(value, list), (
            f"cable current should be a list (of floats) but is {value} (which is a {type(value)})"
        )
        self._current = value

    @property
    def r(self):
        """resistance of the cable in Ohms"""
        self._r = self.rho * self.length / self.area
        return self._r

    @r.setter
    def r(self, value):
        assert isinstance(value, float), (
            f"cable resistance should be a float but is {value} (which is a {type(value)})"
        )
        self._r = value

    @property
    def vdrop_volts(self):
        """voltage drop induced in this cable, in volts"""
        return self._vdrop_volts

    @vdrop_volts.setter
    def vdrop_volts(self, value):
        assert isinstance(value, float), (
            f"cable vdrop_volts should be a float but is {value} (which is a {type(value)})"
        )
        self._vdrop_volts = value

    @property
    def coordinates(self):
        """list of QgsPointXY coordinates of each extremities of the cables
        Note that the cable can have more than 2 extremities if doing angles."""
        return self._coordinates

    @coordinates.setter
    def coordinates(self, value):
        assert isinstance(value, list), (
            f"coordinates should be a list of QgsPointXY values but got {value} instead, which is a {type(value)}"
        )
        self._coordinates = value

    @property
    def layer_name(self):
        """str representing in which QGIS layer this cable is stored."""
        return self._layer_name

    @layer_name.setter
    def layer_name(self, value):
        assert isinstance(value, str), (
            f"layer_name should be a str but got {value} instead, which is a {type(value)}"
        )
        self._layer_name = value

    @property
    def id(self):
        """idx of the cable in the list of cables from the QGIS layer this cable is stored."""
        return self._id

    @id.setter
    def id(self, value):
        assert isinstance(value, int), (
            f"id should be a str but got {value} instead, which is a {type(value)}"
        )
        self._id = value


class Node:
    __slots__ = (
        "_name",
        "_parent",
        "_children",
        "_deepness",
        "_cable",
        "_cables",
        "_power",
        "_phase",
        "_cum_power",
        "_distro",
        "_coordinates",
        "_voltage",
        "_vdrop_percent",
    )

    def __init__(
        self,
        name: str,
    ):
        self.name = name
        self.parent = None
        self.children = {}
        self.deepness = None
        self.cable = {}
        self.cables = []
        self.power = np.array([0.0] * 3)
        self.phase = None
        # self.date = None
        self.cum_power = np.array([0.0] * 3)
        self.distro = dict.fromkeys(["in", "out"])
        self.coordinates = None

    @property
    def name(self):
        """name of that node"""
        return self._name

    @name.setter
    def name(self, value):
        assert isinstance(value, str), f"Node name must be a string, got {type(value)}"
        self._name = value

    @property
    def coordinates(self):
        """coordinates of the Node, has a QgsPointXY"""
        return self._coordinates

    @coordinates.setter
    def coordinates(self, value):
        assert isinstance(value, QgsPointXY) or value is None, (
            "coordinates should be a QgsPointXY"
        )
        self._coordinates = value

    @property
    def parent(self):
        """name of this node's parent"""
        return self._parent

    @parent.setter
    def parent(self, value):
        assert isinstance(value, str) or value is None, (
            "Parent must be a string or None"
        )
        self._parent = value

    @property
    def children(self):
        """ " dict containing Node's children. Each key is the name of one children, the value is the cable going to that children (cf cable attribute)"""
        return self._children

    @children.setter
    def children(self, value):
        assert isinstance(value, dict), "Children must be a dict"
        self._children = value

    @property
    def deepness(self):
        """deepness of that node wrt the generator"""
        return self._deepness

    @deepness.setter
    def deepness(self, value):
        assert isinstance(value, int) or value is None, "Deepness must be int or None"
        self._deepness = value

    @property
    def cable(self):
        """dict containing information about the cable to parent
        The dictionnary contains the keys
            - 'layer' : str : name of the qgis layer containing the cable
            - 'idx': int: index of the cable in that layer
        """
        return self._cable

    @cable.setter
    def cable(self, value):
        assert isinstance(value, dict), "'cable' must be dict"
        self._cable = value

    @property
    def cables(self):
        """list of cables connected to that Node. Cables are described as dictionnaries, cf cable attribute."""
        return self._cables

    @cables.setter
    def cables(self, value):
        assert isinstance(value, list), "'cables' must be list"
        self._cables = value

    @property
    def phase(self):
        return self._phase

    @phase.setter
    def phase(self, value):
        assert isinstance(
            value,
            (
                type(None),  # for init
                int,  # if connected to only 1-phase
                str,  # if connected to another grid
                list,  # if connected to multiple phases
            ),
        ), (
            f"phase should be a (int, str, list, or None) but is {value} which is a {type(value)}"
        )
        self._phase = value

    @property
    def power(self):
        return self._power

    @power.setter
    def power(self, value):
        assert isinstance(value, np.ndarray), "'power' must be a np.ndarray"
        self._power = value

    @property
    def cum_power(self):
        return self._cum_power

    @cum_power.setter
    def cum_power(self, value):
        assert isinstance(value, np.ndarray), "'power' must be a np.ndarray"
        self._cum_power = value

    @property
    def distro(self):
        """a dict with 'in' and 'out' keys describing the necessary inputs and ouputs for that node"""
        return self._distro

    @distro.setter
    def distro(self, value):
        assert isinstance(value, dict), "'distro' must be a dict"
        self._distro = value

    @property
    def voltage(self):
        """voltage at the load, in Volts"""
        return self._voltage

    @voltage.setter
    def voltage(self, value):
        if isinstance(value, int):
            value = float(value)

        assert isinstance(value, float), (
            f"voltage should be a int or float, got {type(value)}"
        )
        self._voltage = value

    @property
    def vdrop_percent(self):
        """voltage drop at the load, in percents"""
        return self._vdrop_percent

    @vdrop_percent.setter
    def vdrop_percent(self, value):
        assert isinstance(value, float), (
            f"voltage drop should be float, got {type(value)}"
        )
        self._vdrop_percent = value
